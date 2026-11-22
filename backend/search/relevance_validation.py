"""
Phase 2C + Retrieval Improvement Stage 1: Evidence-Based & Domain-Aware
Relevance Validation Layer (`RelevanceValidationService`).

Determines whether individual retrieved evidence documents and aggregated
professor bundles genuinely support relevance to the *original* research query:
- Word-boundary & multi-word concept matching (eliminating raw substring leaks)
- Domain-aware homonym disambiguation (e.g. AI neural Transformer vs Electrical Power Transformer)
- Document-level relevance filtering *before* professor aggregation
- Original-query semantic grounding (preventing sparse-only lexical matches from establishing relevance)
- Strict separation of verified vs provisional (`candidate_publication`, `biography`) evidence.
"""
from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from backend.database.models import EvidenceType
from backend.search.ranking import ProfessorEvidenceBundle
from backend.search.retrieval import RetrievedEvidenceItem

# Conversational & syntactic stopwords excluded from concept overlap counts.
# Meaningful technical terms (e.g. "architecture", "attention", "neural", "transformer",
# "network", "fault", "diagnosis", "power", "vision") are intentionally preserved.
QUERY_STOPWORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "based", "by", "for", "from", "in", "into",
    "is", "of", "on", "or", "the", "to", "using", "via", "with", "applications", "analysis",
    "system", "systems", "prediction", "study", "model", "models", "method", "methods",
    "work", "working", "interested", "looking", "research", "field", "area", "related",
    "professors", "faculty", "want", "would", "like", "topic", "topics",
}

# Multi-word technical phrases preserved as atomic concepts during overlap scoring
KNOWN_MULTIWORD_CONCEPTS: Tuple[str, ...] = (
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "transformer architecture",
    "vision transformer",
    "vision transformers",
    "self-attention",
    "multi-head attention",
    "transformer encoder",
    "transformer decoder",
    "large language model",
    "large language models",
    "natural language processing",
    "computer vision",
    "power transformer",
    "power transformers",
    "distribution transformer",
    "fault diagnosis",
    "dissolved gas analysis",
    "powder bed fusion",
    "laser powder bed fusion",
    "3d printing",
    "titanium alloys",
    "speech recognition",
    "mineral processing",
    "geotechnical engineering",
    "monetary policy",
    "central banking",
)

AI_TRANSFORMER_SIGNALS: Tuple[str, ...] = (
    "artificial intelligence",
    "deep learning",
    "machine learning",
    "neural network",
    "neural networks",
    "self-attention",
    "multi-head attention",
    "attention mechanism",
    "vision transformer",
    "vision transformers",
    "vit",
    "llm",
    "llms",
    "large language model",
    "large language models",
    "natural language processing",
    "nlp",
    "bert",
    "gpt",
    "encoder-decoder",
    "transformer encoder",
    "transformer decoder",
    "foundation model",
    "generative ai",
    "computer vision",
    "language model",
    "language modeling",
    "text generation",
    "question answering",
    "neural machine translation",
)

# Specific Transformer neural-network architecture signals (narrower than broad AI/ML;
# deliberately excludes generic "attention" alone so non-Transformer attention models
# are not misclassified as Transformer architecture).
SPECIFIC_TRANSFORMER_SIGNALS: Tuple[str, ...] = (
    "transformer architecture",
    "transformer architectures",
    "transformer neural network",
    "transformer encoder",
    "transformer decoder",
    "self-attention",
    "multi-head attention",
    "vision transformer",
    "vision transformers",
    "swin transformer",
    "deit",
    "detr",
    "bert",
    "roberta",
    "distilbert",
    "gpt",
    "t5",
    "llama",
    "pretrained transformer",
    "pre-trained transformer",
    "transformer model",
    "transformer models",
    "transformer-based",
    "transformer network",
    "transformer networks",
    "masked language model",
    "encoder-decoder transformer",
)

ABSTRACT_UNAVAILABLE_NOTE = (
    "Abstract unavailable; topic relevance is uncertain and inferred from title/metadata only."
)

POWER_TRANSFORMER_SIGNALS: Tuple[str, ...] = (
    "power transformer",
    "power transformers",
    "distribution transformer",
    "current transformer",
    "potential transformer",
    "instrument transformer",
    "transformer winding",
    "winding",
    "transformer oil",
    "dissolved gas",
    "dga",
    "bushing",
    "bushings",
    "high voltage",
    "substation",
    "power grid",
    "power system",
    "power systems",
    "lvac",
    "hvdc",
    "arc fault",
    "switchgear",
    "insulation",
    "tap changer",
    "ferroresonance",
    "core loss",
    "short circuit",
    "electrical machine",
    "electrical machines",
    "induction motor",
    "synchronous generator",
    "fault diagnosis",
)


@dataclass
class RelevanceValidationConfig:
    """
    Configurable relevance validation thresholds.
    - Bundle thresholds (`min_original_dense_score=0.54`, `strong_min_original_dense_score=0.58`)
      are provisional from the Phase 2B score audit and should be calibrated with labelled data.
    - `sparse_fallback_min_dense_score=0.48` ensures sparse lexical matches alone cannot
      establish relevance when dense semantic similarity is very low.
    - Document-level thresholds (`min_item_dense_score=0.45`, `min_item_sparse_score=0.06`,
      `min_item_sparse_dense_floor=0.40`) filter off-topic documents *before* professor
      aggregation so noise items cannot inflate diversity bonuses or explanations.
    """
    min_original_dense_score: float = 0.54
    min_original_sparse_score: float = 0.08
    strong_min_original_dense_score: float = 0.58
    single_term_guard_dense_floor: float = 0.60
    min_query_terms_for_concept_guard: int = 3
    sparse_fallback_min_dense_score: float = 0.48
    min_item_dense_score: float = 0.45
    min_item_sparse_score: float = 0.06
    min_item_sparse_dense_floor: float = 0.40


@dataclass
class ValidationDecision:
    is_valid: bool
    max_allowed_category: str  # "strong" | "related" | "limited" | "insufficient"
    reason_codes: List[str] = field(default_factory=list)
    max_original_dense: float = 0.0
    max_original_sparse: float = 0.0
    max_expanded_dense: float = 0.0
    max_concept_overlap: int = 0
    query_concept_count: int = 0


def _term_in_text(term: str, text: str) -> bool:
    """Word-boundary match (supports hyphenated tokens and multi-word phrases)."""
    if not term or not text:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text, re.IGNORECASE))


def _any_signal_in_text(signals: Sequence[str], text: str) -> bool:
    return any(_term_in_text(sig, text) for sig in signals)


def _item_haystack(item: RetrievedEvidenceItem) -> str:
    pl = item.payload or {}
    topics_str = " ".join(pl.get("canonical_topics") or [])
    domains_str = " ".join(pl.get("topic_domains") or [])
    areas_str = " ".join(pl.get("topic_areas") or [])
    return f"{pl.get('title') or ''} {pl.get('text_snippet') or ''} {topics_str} {domains_str} {areas_str}".lower()


def extract_query_concept_terms(query: str) -> List[str]:
    """Extracts meaningful technical concept tokens (preserving hyphenated and domain terms)."""
    tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", (query or "").lower())
    seen = set()
    terms: List[str] = []
    for t in tokens:
        if len(t) >= 2 and t not in QUERY_STOPWORDS and t not in seen:
            seen.add(t)
            terms.append(t)
    return terms


def extract_query_multiword_phrases(query: str) -> List[str]:
    q_low = (query or "").lower()
    return [phrase for phrase in KNOWN_MULTIWORD_CONCEPTS if _term_in_text(phrase, q_low)]


def count_concept_overlap(
    query_terms: Sequence[str],
    item: RetrievedEvidenceItem,
    query_phrases: Sequence[str] = (),
) -> int:
    """
    Counts word-boundary concept matches between query terms/phrases and an evidence item.
    Avoids false substring matches (e.g. 'work' inside 'network').
    """
    if not query_terms and not query_phrases:
        return 0
    haystack = _item_haystack(item)
    token_hits = sum(1 for term in query_terms if _term_in_text(term, haystack))
    phrase_bonus = sum(1 for ph in query_phrases if _term_in_text(ph, haystack))
    return token_hits + phrase_bonus


def detect_transformer_query_intent(
    original_query: str,
    matched_domains: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """
    Disambiguates polysemous 'transformer' queries:
    - Returns 'ai_transformer' for neural/AI Transformer queries.
    - Returns 'power_transformer' for electrical power-transformer queries.
    - Returns None for non-transformer or explicitly hybrid queries.
    """
    q_low = (original_query or "").lower()
    if not _term_in_text("transformer", q_low) and not _term_in_text("transformers", q_low):
        return None

    has_ai = _any_signal_in_text(AI_TRANSFORMER_SIGNALS, q_low) or _any_signal_in_text(
        SPECIFIC_TRANSFORMER_SIGNALS, q_low
    )
    has_power = _any_signal_in_text(POWER_TRANSFORMER_SIGNALS, q_low)
    if matched_domains:
        dom_text = " ".join(matched_domains).lower()
        if "computer science" in dom_text or "artificial intelligence" in dom_text:
            has_ai = True
        if "electrical" in dom_text and not has_ai:
            has_power = True

    if has_ai and not has_power:
        return "ai_transformer"
    if has_power and not has_ai:
        return "power_transformer"
    return None


def is_publication_abstract_available(item: RetrievedEvidenceItem) -> bool:
    """
    Checks whether a publication document actually includes abstract text beyond its title.
    Never fabricates or assumes abstract content when missing.
    """
    if item.evidence_type not in (
        EvidenceType.VERIFIED_PUBLICATION.value,
        EvidenceType.CANDIDATE_PUBLICATION.value,
    ):
        return True
    pl = item.payload or {}
    title = (pl.get("title") or "").strip()
    snippet = (pl.get("text_snippet") or "").strip()
    if not snippet:
        return False
    if not title:
        return len(snippet) > 40
    # DocumentBuilder stores `f"{title}. {abstract}"` when abstract exists, else `title`
    return len(snippet) > len(title) + 20


def classify_evidence_topic_relevance(
    original_query: str,
    item: RetrievedEvidenceItem,
    matched_domains: Optional[Sequence[str]] = None,
) -> Tuple[str, Optional[str]]:
    """
    Separates broad domain relevance from specific query-topic relevance per evidence item.
    Returns `(tier, note)` where `tier` is one of:
    - "exact_topic": document content supports the exact requested topic
    - "uncertain_topic": title/metadata suggests topic match, but publication abstract is unavailable
    - "broad_domain": document supports broad AI/ML domain context, not the specific topic
    - "irrelevant": domain-mismatched or unrelated to the query scope
    """
    intent = detect_transformer_query_intent(original_query, matched_domains=matched_domains)
    haystack = _item_haystack(item)
    is_pub = item.evidence_type in (
        EvidenceType.VERIFIED_PUBLICATION.value,
        EvidenceType.CANDIDATE_PUBLICATION.value,
    )
    has_abstract = is_publication_abstract_available(item)

    if intent == "ai_transformer":
        has_power = _any_signal_in_text(POWER_TRANSFORMER_SIGNALS, haystack)
        has_specific = _any_signal_in_text(SPECIFIC_TRANSFORMER_SIGNALS, haystack)
        has_transformer_word = _term_in_text("transformer", haystack) or _term_in_text("transformers", haystack)
        has_broad_ai = _any_signal_in_text(AI_TRANSFORMER_SIGNALS, haystack)

        # Exclude electrical power-transformer docs lacking Transformer-NN evidence
        if has_power and not has_specific:
            return "irrelevant", None

        # Explicit neural Transformer architecture evidence
        if has_specific or (has_transformer_word and has_broad_ai and not has_power):
            if is_pub and not has_abstract:
                return "uncertain_topic", ABSTRACT_UNAVAILABLE_NOTE
            return "exact_topic", None

        # General AI/ML publication or profile (broad domain, NOT specific Transformer topic)
        if has_broad_ai:
            return "broad_domain", None

        return "irrelevant", None

    if intent == "power_transformer":
        has_power = _any_signal_in_text(POWER_TRANSFORMER_SIGNALS, haystack)
        has_specific_ai = _any_signal_in_text(SPECIFIC_TRANSFORMER_SIGNALS, haystack)
        if has_specific_ai and not has_power:
            return "irrelevant", None
        if has_power:
            if is_pub and not has_abstract:
                return "uncertain_topic", ABSTRACT_UNAVAILABLE_NOTE
            return "exact_topic", None
        return "irrelevant", None

    # Broad AI or general research queries
    if is_pub and not has_abstract:
        return "uncertain_topic", ABSTRACT_UNAVAILABLE_NOTE
    return "exact_topic", None


class RelevanceValidationService:
    """Validates individual evidence items and aggregated professor bundles against the original query."""

    def __init__(self, config: Optional[RelevanceValidationConfig] = None):
        self.config = config or RelevanceValidationConfig()

    def is_item_domain_compatible(
        self,
        original_query: str,
        item: RetrievedEvidenceItem,
        matched_domains: Optional[Sequence[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks domain compatibility for polysemous technical terms without hard-blocking
        interdisciplinary professors who have genuine target-domain evidence.
        """
        intent = detect_transformer_query_intent(original_query, matched_domains=matched_domains)
        if intent is None:
            return True, None

        haystack = _item_haystack(item)
        has_ai_doc = _any_signal_in_text(AI_TRANSFORMER_SIGNALS, haystack)
        has_power_doc = _any_signal_in_text(POWER_TRANSFORMER_SIGNALS, haystack)

        if intent == "ai_transformer":
            # Reject electrical power-transformer documents that lack any AI/neural evidence
            if has_power_doc and not has_ai_doc:
                return False, "domain_mismatch_power_transformer"
            return True, None

        if intent == "power_transformer":
            # Reject pure neural/NLP transformer documents that lack electrical power signals
            if has_ai_doc and not has_power_doc:
                return False, "domain_mismatch_ai_transformer"
            return True, None

        return True, None

    def filter_evidence_items(
        self,
        original_query: str,
        items: Sequence[RetrievedEvidenceItem],
        matched_domains: Optional[Sequence[str]] = None,
        retrieval_mode: str = "hybrid",
    ) -> List[RetrievedEvidenceItem]:
        """
        Filters weak, off-topic, or domain-mismatched evidence documents *before*
        ProfessorAggregationService so noise items cannot enter bundles, inflate
        diversity bonuses, or appear in explanations.
        """
        if not items:
            return []

        query_terms = extract_query_concept_terms(original_query)
        query_phrases = extract_query_multiword_phrases(original_query)
        kept: List[RetrievedEvidenceItem] = []

        for item in items:
            if item.evidence_type == EvidenceType.DEPARTMENT_CONTEXT.value:
                continue

            compatible, _ = self.is_item_domain_compatible(
                original_query, item, matched_domains=matched_domains
            )
            if not compatible:
                continue

            topic_tier, topic_note = classify_evidence_topic_relevance(
                original_query, item, matched_domains=matched_domains
            )
            if topic_tier == "irrelevant":
                continue

            # Annotate payload copy with non-destructive topic-relevance classification
            # so MatchExplanationService can present exact-topic vs broad-domain evidence separately.
            item.payload["_topic_relevance_tier"] = topic_tier
            if topic_note:
                item.payload["_topic_relevance_note"] = topic_note

            best_dense = max(item.original_dense_score, item.expanded_dense_score)
            best_sparse = max(item.original_sparse_score, item.expanded_sparse_score)
            overlap = count_concept_overlap(query_terms, item, query_phrases=query_phrases)

            if retrieval_mode == "sparse":
                if best_sparse >= self.config.min_item_sparse_score:
                    kept.append(item)
                continue

            passes_dense = best_dense >= self.config.min_item_dense_score
            passes_sparse_assisted = (
                best_sparse >= self.config.min_item_sparse_score
                and overlap >= 1
                and best_dense >= self.config.min_item_sparse_dense_floor
            )
            if passes_dense or passes_sparse_assisted:
                kept.append(item)

        return kept

    def validate_bundle(
        self,
        original_query: str,
        bundle: ProfessorEvidenceBundle,
        retrieval_mode: str = "hybrid",  # "dense" | "sparse" | "hybrid"
        matched_domains: Optional[Sequence[str]] = None,
    ) -> ValidationDecision:
        non_dept_items: List[RetrievedEvidenceItem] = [
            it
            for ev_type, lst in bundle.items_by_type.items()
            if ev_type != EvidenceType.DEPARTMENT_CONTEXT.value
            for it in lst
        ]

        if not non_dept_items:
            return ValidationDecision(
                is_valid=False,
                max_allowed_category="insufficient",
                reason_codes=["department_only_or_empty"],
            )

        # Enforce domain compatibility at bundle level as well (in case called directly)
        domain_compatible_items = [
            it
            for it in non_dept_items
            if self.is_item_domain_compatible(original_query, it, matched_domains=matched_domains)[0]
        ]
        if not domain_compatible_items:
            return ValidationDecision(
                is_valid=False,
                max_allowed_category="insufficient",
                reason_codes=["domain_mismatch_all_evidence"],
            )

        # For Transformer queries, classify whether the professor has exact-topic,
        # uncertain-topic, or broader-domain evidence.
        # - For `ai_transformer` queries, retain the UNION of exact-topic Transformer
        #   professors AND credible broader AI/ML professors (never rejecting broad AI
        #   faculty), while still excluding electrical power-transformer-only evidence.
        # - Broad-AI-only professors are capped at 'related' and explicitly tagged so
        #   explanations never claim Transformer-specific expertise.
        transformer_intent = detect_transformer_query_intent(original_query, matched_domains=matched_domains)
        only_uncertain_topic = False
        broad_domain_only = False
        if transformer_intent in ("ai_transformer", "power_transformer"):
            item_tiers = [
                classify_evidence_topic_relevance(original_query, it, matched_domains=matched_domains)[0]
                for it in domain_compatible_items
            ]
            has_exact_topic = any(t == "exact_topic" for t in item_tiers)
            has_uncertain_topic = any(t == "uncertain_topic" for t in item_tiers)
            has_broad_domain = any(t == "broad_domain" for t in item_tiers)

            if not has_exact_topic and not has_uncertain_topic and not has_broad_domain:
                return ValidationDecision(
                    is_valid=False,
                    max_allowed_category="insufficient",
                    reason_codes=["no_compatible_topic_or_domain_evidence"],
                )
            only_uncertain_topic = (not has_exact_topic) and has_uncertain_topic and (not has_broad_domain)
            broad_domain_only = (not has_exact_topic) and (not has_uncertain_topic) and has_broad_domain

        query_terms = extract_query_concept_terms(original_query)
        query_phrases = extract_query_multiword_phrases(original_query)
        q_term_count = len(query_terms)

        max_orig_dense = max(it.original_dense_score for it in domain_compatible_items)
        max_orig_sparse = max(it.original_sparse_score for it in domain_compatible_items)
        max_exp_dense = max(it.expanded_dense_score for it in domain_compatible_items)
        max_overlap = max(
            count_concept_overlap(query_terms, it, query_phrases=query_phrases)
            for it in domain_compatible_items
        )

        reasons: List[str] = []

        # 1. Original-query relevance gate (sparse lexical match alone cannot establish relevance)
        has_orig_dense = max_orig_dense >= self.config.min_original_dense_score
        has_orig_sparse = max_orig_sparse >= self.config.min_original_sparse_score

        if retrieval_mode == "dense":
            passes_raw_gate = has_orig_dense
        elif retrieval_mode == "sparse":
            passes_raw_gate = has_orig_sparse
        else:
            passes_raw_gate = has_orig_dense or (
                has_orig_sparse
                and max_overlap >= 2
                and max_orig_dense >= self.config.sparse_fallback_min_dense_score
            )

        if not passes_raw_gate:
            reasons.append("below_original_query_relevance_floor")
            if max_exp_dense >= self.config.min_original_dense_score and max_orig_dense < self.config.min_original_dense_score:
                reasons.append("expanded_only_without_original_support")
            return ValidationDecision(
                is_valid=False,
                max_allowed_category="insufficient",
                reason_codes=reasons,
                max_original_dense=round(max_orig_dense, 4),
                max_original_sparse=round(max_orig_sparse, 4),
                max_expanded_dense=round(max_exp_dense, 4),
                max_concept_overlap=max_overlap,
                query_concept_count=q_term_count,
            )

        # 2. Single-term / isolated keyword overlap guard for multi-concept technical queries
        if q_term_count >= self.config.min_query_terms_for_concept_guard and max_overlap <= 1:
            if max_orig_dense < self.config.single_term_guard_dense_floor:
                reasons.append("single_term_overlap_below_concept_guard")
                return ValidationDecision(
                    is_valid=False,
                    max_allowed_category="insufficient",
                    reason_codes=reasons,
                    max_original_dense=round(max_orig_dense, 4),
                    max_original_sparse=round(max_orig_sparse, 4),
                    max_expanded_dense=round(max_exp_dense, 4),
                    max_concept_overlap=max_overlap,
                    query_concept_count=q_term_count,
                )

        # 3. Evidence-confidence separation:
        # Candidate publications alone or biography alone cannot establish strong/related status.
        has_verified_or_profile = any(
            ev_type in bundle.items_by_type
            for ev_type in (
                EvidenceType.VERIFIED_PUBLICATION.value,
                EvidenceType.RESEARCH_INTEREST.value,
                EvidenceType.RESEARCH_PROJECT.value,
            )
        )

        if not has_verified_or_profile:
            max_cat = "limited"
            if EvidenceType.CANDIDATE_PUBLICATION.value in bundle.items_by_type:
                reasons.append("candidate_publications_only_capped_limited")
            else:
                reasons.append("biography_only_capped_limited")
        elif only_uncertain_topic:
            max_cat = "limited"
            reasons.append("topic_relevance_uncertain_missing_abstract")
        elif broad_domain_only:
            max_cat = "related"
            reasons.append("broad_ai_domain_match_without_specific_topic")
        elif retrieval_mode != "sparse" and max_orig_dense < self.config.strong_min_original_dense_score:
            max_cat = "related"
            reasons.append("moderate_original_dense_capped_related")
        else:
            max_cat = "strong"
            reasons.append("validated_original_query_evidence")

        return ValidationDecision(
            is_valid=True,
            max_allowed_category=max_cat,
            reason_codes=reasons,
            max_original_dense=round(max_orig_dense, 4),
            max_original_sparse=round(max_orig_sparse, 4),
            max_expanded_dense=round(max_exp_dense, 4),
            max_concept_overlap=max_overlap,
            query_concept_count=q_term_count,
        )
