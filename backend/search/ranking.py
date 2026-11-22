"""
Phase 2A Step 8 (Stages 5-6): ProfessorAggregationService, ProfessorRankingService,
MatchExplanationService, and end-to-end SearchService.

Implements:
- Deduplication across evidence (content_hash, same publication verified vs candidate,
  project role weighting PI=1.0 vs Co-PI=0.8)
- Diminishing returns within each evidence type (r1 + 0.5*r2 + 0.25*r3)
- Independent evidence diversity bonus
- Explicit generic-root and noisy-topic penalties
- Match tiers: strong, related, limited, insufficient
- Strictly grounded explanations citing actual DB/payload IDs and verification statuses.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from backend.database.models import Department, EvidenceType, Professor, University
from backend.search.cancellation import CancellationToken
from backend.search.document_builder import CANDIDATE_DISCLOSURE_LABEL
from backend.search.query_understanding import QueryExpansionResult, QueryExpansionService
from backend.search.retrieval import HybridRetrievalService, RetrievedEvidenceItem


DEFAULT_EVIDENCE_WEIGHTS: Dict[str, float] = {
    EvidenceType.VERIFIED_PUBLICATION.value: 1.00,
    EvidenceType.RESEARCH_INTEREST.value: 0.90,
    EvidenceType.RESEARCH_PROJECT.value: 0.70,
    EvidenceType.BIOGRAPHY.value: 0.50,
    EvidenceType.CANDIDATE_PUBLICATION.value: 0.40,
    EvidenceType.DEPARTMENT_CONTEXT.value: 0.15,
}

PROJECT_CATEGORY_MULTIPLIER: Dict[str, float] = {
    "sponsored_research": 1.00,
    "industrial_consultancy": 0.85,
    "routine_testing_vetting": 0.55,
    "administrative_or_grant": 0.00,
}


@dataclass
class RankingConfig:
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_EVIDENCE_WEIGHTS))
    diversity_bonus_per_type: float = 0.18
    generic_root_penalty: float = 0.55
    noisy_topic_penalty: float = 0.75
    strong_threshold: float = 1.15
    related_threshold: float = 0.55
    limited_threshold: float = 0.25


@dataclass
class ProfessorEvidenceBundle:
    professor_id: int
    department_id: int
    items_by_type: Dict[str, List[RetrievedEvidenceItem]] = field(default_factory=dict)
    matched_queries: List[str] = field(default_factory=list)


@dataclass
class RankedProfessorMatch:
    professor_id: int
    professor_name: str
    department_code: str
    department_name: str
    profile_url: Optional[str]
    score: float
    match_category: str  # "strong" | "related" | "limited" | "insufficient"
    evidence_counts: Dict[str, int]
    matched_topics: List[str]
    matched_queries: List[str]
    supporting_evidence: List[Dict[str, Any]]
    explanation: str
    designation: Optional[str] = None
    email: Optional[str] = None
    research_interests: Optional[str] = None
    biography: Optional[str] = None


class ProfessorAggregationService:
    """Groups retrieved evidence by professor_id and deduplicates overlapping evidence."""

    def aggregate(
        self,
        retrieved_items: Sequence[RetrievedEvidenceItem],
    ) -> Dict[int, ProfessorEvidenceBundle]:
        bundles: Dict[int, ProfessorEvidenceBundle] = {}
        seen_hashes_per_prof: Dict[int, set] = {}
        verified_pub_ids_per_prof: Dict[int, set] = {}

        # First pass: track verified publication source_ids so candidate versions don't double-count
        for item in retrieved_items:
            if item.professor_id is None:
                continue
            if item.evidence_type == EvidenceType.VERIFIED_PUBLICATION.value:
                pub_id = item.payload.get("source_id")
                if pub_id is not None:
                    verified_pub_ids_per_prof.setdefault(item.professor_id, set()).add(pub_id)

        for item in retrieved_items:
            pid = item.professor_id
            if pid is None:
                continue

            if (
                item.evidence_type == EvidenceType.CANDIDATE_PUBLICATION.value
                and item.payload.get("source_id") in verified_pub_ids_per_prof.get(pid, set())
            ):
                continue

            chash = item.payload.get("content_hash")
            seen_h = seen_hashes_per_prof.setdefault(pid, set())
            if chash and chash in seen_h:
                continue
            if chash:
                seen_h.add(chash)

            bundle = bundles.get(pid)
            if bundle is None:
                bundle = ProfessorEvidenceBundle(professor_id=pid, department_id=item.department_id)
                bundles[pid] = bundle

            bundle.items_by_type.setdefault(item.evidence_type, []).append(item)
            if item.originating_query not in bundle.matched_queries:
                bundle.matched_queries.append(item.originating_query)

        # Sort items within each type descending by score
        for bundle in bundles.values():
            for ev_type, lst in bundle.items_by_type.items():
                lst.sort(key=lambda x: x.score, reverse=True)

        return bundles


class ProfessorRankingService:
    """Scores aggregated professor bundles and classifies match categories."""

    def __init__(self, config: Optional[RankingConfig] = None):
        self.config = config or RankingConfig()

    def _effective_item_score(self, item: RetrievedEvidenceItem) -> float:
        s = item.score
        meta = item.payload.get("metadata") or {}

        if meta.get("has_generic_root_only"):
            s *= self.config.generic_root_penalty
        if meta.get("has_noisy_topics"):
            s *= self.config.noisy_topic_penalty

        if item.evidence_type == EvidenceType.RESEARCH_PROJECT.value:
            cat = meta.get("project_category", "sponsored_research")
            s *= PROJECT_CATEGORY_MULTIPLIER.get(cat, 1.0)
            if meta.get("role") == "Co-Principal Investigator":
                s *= 0.80
        elif item.evidence_type == EvidenceType.CANDIDATE_PUBLICATION.value:
            conf = float(item.payload.get("confidence_score") or 0.5)
            s *= max(0.3, min(1.0, conf))

        return s

    def score_bundle(self, bundle: ProfessorEvidenceBundle) -> Tuple[float, str, Dict[str, int]]:
        total_score = 0.0
        evidence_counts: Dict[str, int] = {}
        independent_types_above_floor = 0

        for ev_type, items in bundle.items_by_type.items():
            eff_scores = sorted((self._effective_item_score(it) for it in items), reverse=True)
            evidence_counts[ev_type] = len(eff_scores)
            # Diminishing returns: top-3 only (r1 + 0.5*r2 + 0.25*r3)
            decayed = 0.0
            for idx, val in enumerate(eff_scores[:3]):
                decayed += val * (0.5 ** idx)
            w = self.config.weights.get(ev_type, 0.3)
            total_score += w * decayed
            if eff_scores and eff_scores[0] >= 0.20 and ev_type != EvidenceType.DEPARTMENT_CONTEXT.value:
                independent_types_above_floor += 1

        if independent_types_above_floor > 1:
            total_score += (independent_types_above_floor - 1) * self.config.diversity_bonus_per_type

        # Exact-topic specificity bonus: elevates bundles containing Stage 2 exact-topic
        # evidence above broad-domain-only bundles without reducing any broad-domain score
        # or excluding any qualifying professor.
        all_tiers = [
            (it.payload or {}).get("_topic_relevance_tier")
            for lst in bundle.items_by_type.values()
            for it in lst
            if (it.payload or {}).get("_topic_relevance_tier") is not None
        ]
        if all_tiers and any(t == "exact_topic" for t in all_tiers):
            total_score += 0.35

        has_strong_tier_source = bool(
            bundle.items_by_type.get(EvidenceType.VERIFIED_PUBLICATION.value)
            or bundle.items_by_type.get(EvidenceType.RESEARCH_INTEREST.value)
            or bundle.items_by_type.get(EvidenceType.RESEARCH_PROJECT.value)
        )
        has_only_candidate_or_dept = not (
            bundle.items_by_type.get(EvidenceType.VERIFIED_PUBLICATION.value)
            or bundle.items_by_type.get(EvidenceType.RESEARCH_INTEREST.value)
            or bundle.items_by_type.get(EvidenceType.RESEARCH_PROJECT.value)
            or bundle.items_by_type.get(EvidenceType.BIOGRAPHY.value)
        )

        # Guardrails:
        # 1. Candidate publications alone or department context alone can NEVER produce a strong match.
        # 2. Strong match requires tier 1-3 evidence + corroboration (>=2 independent evidence types).
        if (
            total_score >= self.config.strong_threshold
            and has_strong_tier_source
            and independent_types_above_floor >= 2
            and not has_only_candidate_or_dept
        ):
            category = "strong"
        elif total_score >= self.config.related_threshold and not has_only_candidate_or_dept:
            category = "related"
        elif total_score >= self.config.limited_threshold:
            category = "limited"
        else:
            category = "insufficient"

        return round(total_score, 4), category, evidence_counts


class MatchExplanationService:
    """Builds grounded explanations from retrieved evidence without inventing any facts."""

    def build_explanation(
        self,
        prof: Professor,
        dept: Optional[Department],
        bundle: ProfessorEvidenceBundle,
        score: float,
        match_category: str,
        evidence_counts: Dict[str, int],
    ) -> RankedProfessorMatch:
        supporting: List[Dict[str, Any]] = []
        topic_set = set()

        priority_order = [
            EvidenceType.VERIFIED_PUBLICATION.value,
            EvidenceType.RESEARCH_INTEREST.value,
            EvidenceType.RESEARCH_PROJECT.value,
            EvidenceType.BIOGRAPHY.value,
            EvidenceType.CANDIDATE_PUBLICATION.value,
        ]
        for ev_type in priority_order:
            items_for_type = list(bundle.items_by_type.get(ev_type, []))
            if ev_type == EvidenceType.VERIFIED_PUBLICATION.value:
                tier_rank = {"exact_topic": 0, "uncertain_topic": 1, "broad_domain": 2}
                items_for_type.sort(
                    key=lambda it: (
                        tier_rank.get((it.payload or {}).get("_topic_relevance_tier", "exact_topic"), 2),
                        -it.score,
                    )
                )
            for item in items_for_type[:3]:
                pl = item.payload
                meta = pl.get("metadata") or {}
                for t in pl.get("canonical_topics") or []:
                    topic_set.add(t)

                topic_tier = pl.get("_topic_relevance_tier")
                if ev_type == EvidenceType.VERIFIED_PUBLICATION.value:
                    rel_group = (
                        "other_domain_publication"
                        if topic_tier == "broad_domain"
                        else "exact_topic_publication"
                    )
                elif ev_type == EvidenceType.CANDIDATE_PUBLICATION.value:
                    rel_group = "candidate_publication"
                elif ev_type == EvidenceType.RESEARCH_INTEREST.value:
                    rel_group = "research_interest"
                elif ev_type == EvidenceType.RESEARCH_PROJECT.value:
                    rel_group = "research_project"
                else:
                    rel_group = "biography"

                entry: Dict[str, Any] = {
                    "evidence_id": item.document_id,
                    "evidence_type": ev_type,
                    "relevance_group": rel_group,
                    "topic_relevance_note": pl.get("_topic_relevance_note"),
                    "title": pl.get("title"),
                    "snippet": pl.get("text_snippet"),
                    "source_url": pl.get("source_url"),
                    "verification_status": pl.get("verification_status"),
                    "matched_by_query": item.originating_query,
                    "score": round(item.score, 4),
                }
                if ev_type == EvidenceType.CANDIDATE_PUBLICATION.value:
                    entry["authorship_note"] = CANDIDATE_DISCLOSURE_LABEL
                elif ev_type == EvidenceType.RESEARCH_PROJECT.value:
                    entry["role"] = meta.get("role")
                    entry["sponsor"] = meta.get("sponsor")
                    entry["project_category"] = meta.get("project_category")
                supporting.append(entry)

        parts = []
        if evidence_counts.get(EvidenceType.VERIFIED_PUBLICATION.value):
            parts.append(f"{evidence_counts[EvidenceType.VERIFIED_PUBLICATION.value]} verified publication(s)")
        if evidence_counts.get(EvidenceType.RESEARCH_INTEREST.value):
            parts.append("official profile research interests")
        if evidence_counts.get(EvidenceType.RESEARCH_PROJECT.value):
            parts.append(f"{evidence_counts[EvidenceType.RESEARCH_PROJECT.value]} research project(s)")
        if evidence_counts.get(EvidenceType.BIOGRAPHY.value):
            parts.append("faculty biography")
        if evidence_counts.get(EvidenceType.CANDIDATE_PUBLICATION.value):
            parts.append(
                f"{evidence_counts[EvidenceType.CANDIDATE_PUBLICATION.value]} candidate publication(s) (authorship not yet verified)"
            )

        all_tiers = [
            (it.payload or {}).get("_topic_relevance_tier")
            for lst in bundle.items_by_type.values()
            for it in lst
            if (it.payload or {}).get("_topic_relevance_tier") is not None
        ]
        is_broad_domain_only = bool(all_tiers) and all(t == "broad_domain" for t in all_tiers)

        if parts:
            if is_broad_domain_only:
                explanation = (
                    "Broader AI/domain match (no specific query-topic publication confirmed) supported by: "
                    + ", ".join(parts)
                    + "."
                )
            else:
                explanation = f"{match_category.title()} match supported by: " + ", ".join(parts) + "."
        else:
            explanation = "Insufficient evidence in indexed profile records."

        return RankedProfessorMatch(
            professor_id=prof.id,
            professor_name=prof.name,
            department_code=dept.code if dept and dept.code else "",
            department_name=dept.name if dept else "",
            profile_url=prof.profile_url,
            score=score,
            match_category=match_category,
            evidence_counts=evidence_counts,
            matched_topics=sorted(topic_set)[:10],
            matched_queries=bundle.matched_queries,
            supporting_evidence=supporting,
            explanation=explanation,
            designation=prof.designation,
            email=prof.email,
            research_interests=prof.research_interests,
            biography=prof.biography,
        )


class SearchService:
    """Orchestrates QueryUnderstanding/Expansion -> HybridRetrieval -> Aggregation -> Validation -> Ranking -> Explanations."""

    def __init__(
        self,
        expansion_service: QueryExpansionService,
        retrieval_service: HybridRetrievalService,
        aggregation_service: Optional[ProfessorAggregationService] = None,
        ranking_service: Optional[ProfessorRankingService] = None,
        explanation_service: Optional[MatchExplanationService] = None,
        relevance_validator: Optional[Any] = None,
    ):
        self.expansion_service = expansion_service
        self.retrieval_service = retrieval_service
        self.aggregation_service = aggregation_service or ProfessorAggregationService()
        self.ranking_service = ranking_service or ProfessorRankingService()
        self.explanation_service = explanation_service or MatchExplanationService()
        self.relevance_validator = relevance_validator

    @staticmethod
    def _cap_category(cat: str, max_allowed: str) -> str:
        order = {"insufficient": 0, "limited": 1, "related": 2, "strong": 3}
        return cat if order.get(cat, 0) <= order.get(max_allowed, 3) else max_allowed

    @staticmethod
    def _calibrate_score_to_category(score: float, cat: str, config: RankingConfig) -> float:
        """
        Aligns a professor's match score with its validated match category when
        RelevanceValidationService caps the category below the raw bundle score's tier.
        Strictly monotonic: higher raw evidence scores always retain higher calibrated
        scores within the same tier, while guaranteeing strong >= strong_threshold >
        related >= related_threshold > limited >= limited_threshold.
        """
        if cat == "related" and score >= config.strong_threshold:
            span = max(0.01, config.strong_threshold - config.related_threshold - 0.0001)
            return round(config.related_threshold + span * (score / (score + 1.0)), 4)
        if cat == "limited" and score >= config.related_threshold:
            span = max(0.01, config.related_threshold - config.limited_threshold - 0.0001)
            return round(config.limited_threshold + span * (score / (score + 1.0)), 4)
        return round(score, 4)

    @staticmethod
    def _build_no_results_message(db: Session, query: str, university_id: Optional[int]) -> str:
        if university_id is not None:
            univ = db.query(University).filter(University.id == university_id).first()
            univ_name = univ.name if univ and univ.name else f"university #{university_id}"
            return f"No faculty members with relevant research evidence were found for {query} at {univ_name}."
        return "No sufficiently relevant professors found."

    def search(
        self,
        db: Session,
        query: str,
        top_k: Optional[int] = 20,
        offset: int = 0,
        use_expansion: bool = True,
        university_id: Optional[int] = None,
        department_ids: Optional[Sequence[int]] = None,
        include_candidate_publications: bool = True,
        cancel_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        safe_offset = max(0, int(offset or 0))
        if cancel_token is not None:
            cancel_token.check("query_processing")
        exp_result: QueryExpansionResult = self.expansion_service.expand(query)
        active_queries = exp_result.queries if use_expansion else [exp_result.queries[0]]

        # 1. Retrieve eligible evidence
        if cancel_token is not None:
            cancel_token.check("retrieval")
        retrieve_kwargs: Dict[str, Any] = {
            "expanded_queries": active_queries,
            "university_id": university_id,
            "department_ids": department_ids,
            "include_candidate_publications": include_candidate_publications,
        }
        if cancel_token is not None:
            retrieve_kwargs["cancel_token"] = cancel_token
        retrieved = self.retrieval_service.retrieve(**retrieve_kwargs)

        # 2. Apply document-level domain & relevance validation before aggregation
        if cancel_token is not None:
            cancel_token.check("result_merging")
        matched_domains = getattr(exp_result.understanding, "matched_domains", None)
        if self.relevance_validator is not None and hasattr(self.relevance_validator, "filter_evidence_items"):
            retrieved = self.relevance_validator.filter_evidence_items(
                query,
                retrieved,
                matched_domains=matched_domains,
                retrieval_mode="hybrid",
            )

        # 3 & 4. Preserve publication authorship verification and aggregate/deduplicate by professor
        bundles = self.aggregation_service.aggregate(retrieved)

        if not bundles:
            return {
                "query": query,
                "expansion": exp_result,
                "status": "insufficient_evidence",
                "message": self._build_no_results_message(db, query, university_id),
                "total_qualifying_results": 0,
                "offset": safe_offset,
                "limit": top_k,
                "has_more": False,
                "results": [],
            }

        # 5. Determine all qualifying professors (strictly enforcing university_id if provided)
        if cancel_token is not None:
            cancel_token.check("response_preparation")
        prof_ids = list(bundles.keys())
        profs = {p.id: p for p in db.query(Professor).filter(Professor.id.in_(prof_ids)).all()}
        dept_ids = {p.department_id for p in profs.values()}
        depts = {d.id: d for d in db.query(Department).filter(Department.id.in_(dept_ids)).all()}

        qualifying: List[RankedProfessorMatch] = []
        for pid, bundle in bundles.items():
            if cancel_token is not None:
                cancel_token.check("response_preparation")
            prof = profs.get(pid)
            if not prof or prof.verification_status == "rejected":
                continue
            dept = depts.get(prof.department_id)
            if university_id is not None and (dept is None or dept.university_id != university_id):
                continue
            score, cat, counts = self.ranking_service.score_bundle(bundle)
            if self.relevance_validator is not None:
                try:
                    decision = self.relevance_validator.validate_bundle(
                        query,
                        bundle,
                        retrieval_mode="hybrid",
                        matched_domains=matched_domains,
                    )
                except TypeError:
                    decision = self.relevance_validator.validate_bundle(query, bundle, retrieval_mode="hybrid")
                if not decision.is_valid:
                    continue
                cat = self._cap_category(cat, decision.max_allowed_category)
                score = self._calibrate_score_to_category(score, cat, self.ranking_service.config)
            if cat == "insufficient":
                continue
            qualifying.append(
                self.explanation_service.build_explanation(
                    prof=prof,
                    dept=dept,
                    bundle=bundle,
                    score=score,
                    match_category=cat,
                    evidence_counts=counts,
                )
            )

        # 6. Calculate total qualifying professor count
        total_qualifying = len(qualifying)

        # 7. Sort the complete qualifying collection by research match score descending,
        # with deterministic tie-breaking: department name -> professor name -> professor_id.
        qualifying.sort(
            key=lambda r: (
                -round(r.score, 6),
                (r.department_name or r.department_code or "").lower(),
                (r.professor_name or "").lower(),
                r.professor_id,
            )
        )

        # 8. Apply pagination AFTER aggregation, validation, counting, and sorting
        if top_k is not None:
            page_results = qualifying[safe_offset : safe_offset + top_k]
        else:
            page_results = qualifying[safe_offset:]
        has_more = (safe_offset + len(page_results)) < total_qualifying

        # 9. Return requested page with total_qualifying_results and pagination metadata
        return {
            "query": query,
            "expansion": exp_result,
            "status": "ok" if total_qualifying > 0 else "insufficient_evidence",
            "message": None if total_qualifying > 0 else self._build_no_results_message(db, query, university_id),
            "total_qualifying_results": total_qualifying,
            "offset": safe_offset,
            "limit": top_k,
            "has_more": has_more,
            "results": page_results,
        }
