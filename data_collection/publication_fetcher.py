import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.database.models import (
    Professor,
    Publication,
    ProfessorPublication,
    DataSource,
    VerificationStatus
)
from data_collection.openalex_client import OpenAlexClient
from data_collection.crossref_client import CrossrefClient
from data_collection.author_disambiguation import AuthorDisambiguator
from data_processing.deduplication import find_existing_publication
from data_processing.topic_extraction import get_or_create_topic

logger = logging.getLogger(__name__)

RAW_OPENALEX_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "openalex"
RAW_OPENALEX_DIR.mkdir(parents=True, exist_ok=True)
RAW_CROSSREF_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "crossref"
RAW_CROSSREF_DIR.mkdir(parents=True, exist_ok=True)


class PublicationFetcher:
    def __init__(
        self,
        openalex_client: Optional[OpenAlexClient] = None,
        crossref_client: Optional[CrossrefClient] = None,
        disambiguator: Optional[AuthorDisambiguator] = None,
        max_works_per_author: int = 10
    ):
        self.openalex = openalex_client or OpenAlexClient()
        self.crossref = crossref_client or CrossrefClient()
        self.disambiguator = disambiguator or AuthorDisambiguator()
        self.max_works = int(os.getenv("MAX_PUBLICATIONS_PER_PROFESSOR", max_works_per_author))
        self._coauthor_candidates_by_id: Dict[str, Dict] = {}
        self._coauthor_works_by_id: Dict[str, List[Dict]] = {}
        self._build_openalex_coauthor_index()

    def _build_openalex_coauthor_index(self):
        """
        Builds an index of IIT Kharagpur (I145894827) co-authors and their works
        from all cached OpenAlex works JSON files in data/raw/openalex/.
        """
        for wf in RAW_OPENALEX_DIR.glob("works_*.json"):
            try:
                works = json.loads(wf.read_text(encoding="utf-8"))
                for w in works:
                    for auth in w.get("authorships") or []:
                        author_obj = auth.get("author") or {}
                        aid = author_obj.get("id")
                        dname = author_obj.get("display_name")
                        if not aid or not dname:
                            continue
                        insts = auth.get("institutions") or []
                        raw_affs = auth.get("raw_affiliation_strings") or []
                        is_kgp = any(
                            "145894827" in (inst.get("id") or "")
                            or "kharagpur" in (inst.get("display_name") or "").lower()
                            for inst in insts
                        ) or any("kharagpur" in s.lower() for s in raw_affs)
                        if not is_kgp:
                            continue
                        if aid not in self._coauthor_candidates_by_id:
                            self._coauthor_candidates_by_id[aid] = {
                                "openalex_id": aid,
                                "display_name": dname,
                                "orcid": author_obj.get("orcid"),
                                "institutions": ["Indian Institute of Technology Kharagpur"],
                                "affiliations": [{"institution": {"display_name": "Indian Institute of Technology Kharagpur"}}],
                                "summary_stats": {"top_concepts": w.get("topics") or []}
                            }
                        w_list = self._coauthor_works_by_id.setdefault(aid, [])
                        if not any(existing.get("openalex_id") == w.get("openalex_id") for existing in w_list):
                            w_list.append(w)
            except Exception:
                pass

    def _get_cached_author_candidates(self, name: str, use_cache: bool = True) -> List[Dict]:
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.lower()).strip("_")[:80]
        cache_file = RAW_OPENALEX_DIR / f"author_{slug}.json"
        if use_cache and cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Search with IIT Kharagpur affiliation filter (I145894827 covers both current and historical affiliations).
        # Do not fall back to unfiltered name-only search, so we never match authors by name similarity alone.
        candidates = self.openalex.search_authors_by_name(name, allow_unfiltered_fallback=False)
        if not getattr(self.openalex, "daily_budget_exhausted", False):
            try:
                cache_file.write_text(json.dumps(candidates), encoding="utf-8")
            except Exception:
                pass

        # Also check cached IIT Kharagpur OpenAlex co-author index
        if not candidates and self._coauthor_candidates_by_id:
            co_matches = []
            for aid, cand in self._coauthor_candidates_by_id.items():
                if self.disambiguator.calculate_name_similarity(name, cand["display_name"]) >= 0.70:
                    co_matches.append(cand)
            if co_matches:
                return co_matches
        return candidates

    def _get_cached_works(self, openalex_author_id: str, limit: int, use_cache: bool = True) -> List[Dict]:
        clean_id = openalex_author_id.split("/")[-1]
        cache_file = RAW_OPENALEX_DIR / f"works_{clean_id}_{limit}.json"
        if use_cache and cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        works = self.openalex.get_works_by_author(openalex_author_id, limit=limit)
        if works and not getattr(self.openalex, "daily_budget_exhausted", False):
            try:
                cache_file.write_text(json.dumps(works), encoding="utf-8")
            except Exception:
                pass
        if not works and openalex_author_id in self._coauthor_works_by_id:
            return self._coauthor_works_by_id[openalex_author_id][:limit]
        return works

    def _get_cached_crossref_works(self, name: str, limit: int = 8, use_cache: bool = True) -> List[Dict]:
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.lower()).strip("_")[:80]
        cache_file = RAW_CROSSREF_DIR / f"works_{slug}.json"
        if use_cache and cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        raw_works = self.crossref.search_works_by_author(
            author_name=name,
            affiliation="Indian Institute of Technology Kharagpur",
            rows=limit
        )
        if raw_works is not None:
            try:
                cache_file.write_text(json.dumps(raw_works), encoding="utf-8")
            except Exception:
                pass
            return raw_works
        return []

    def _fetch_network_data_for_professor(
        self,
        prof_id: int,
        prof_name: str,
        prof_topics: List[str],
        known_orcid: Optional[str],
        known_openalex_id: Optional[str]
    ) -> Dict:
        """
        Thread-safe network/cache worker that performs OpenAlex author search,
        disambiguation, and works retrieval without touching the SQLAlchemy session.
        """
        author_match_status = VerificationStatus.PENDING.value
        author_match_score = 0.90
        author_match_evidence = "Confirmed OpenAlex Author ID"
        openalex_author_id = known_openalex_id
        matched_orcid = None

        if not openalex_author_id:
            candidates = self._get_cached_author_candidates(prof_name)
            best_candidate = None
            best_score = 0.0
            best_status = "rejected"
            best_evidence = ""

            for cand in candidates:
                score, status, evidence = self.disambiguator.match_author_candidate(
                    professor_name=prof_name,
                    professor_topics=prof_topics,
                    candidate=cand,
                    known_orcid=known_orcid,
                    known_openalex_id=known_openalex_id
                )
                if score > best_score:
                    best_score = score
                    best_candidate = cand
                    best_status = status
                    best_evidence = evidence

            if best_candidate and best_status != "rejected":
                author_match_status = best_status
                author_match_score = best_score
                author_match_evidence = best_evidence
                openalex_author_id = best_candidate.get("openalex_id")
                matched_orcid = best_candidate.get("orcid")
            else:
                author_match_status = "rejected"
                author_match_score = best_score
                author_match_evidence = best_evidence

        fetch_limit = 2 if author_match_status == "needs_review" else self.max_works
        works = self._get_cached_works(openalex_author_id, limit=fetch_limit) if openalex_author_id else []

        # Enrich up to 1 non-DataCite DOI work per professor via Crossref in the worker thread if venue/year/authors missing
        crossref_calls = 0
        for w in works:
            if crossref_calls >= 1:
                break
            doi_val = (w.get("doi") or "").lower()
            if doi_val and "10.48550/" not in doi_val and "zenodo" not in doi_val and (
                not w.get("journal_or_conference") or not w.get("authors_list") or not w.get("publication_year")
            ):
                if "_crossref_enriched" not in w:
                    try:
                        cr_data = self.crossref.get_work_by_doi(w["doi"])
                        crossref_calls += 1
                        if cr_data:
                            w["_crossref_enriched"] = True
                            if not w.get("journal_or_conference") and cr_data.get("container_title"):
                                w["journal_or_conference"] = cr_data["container_title"]
                            if not w.get("authors_list") and cr_data.get("authors"):
                                w["authors_list"] = ", ".join(a["name"] for a in cr_data["authors"] if a.get("name"))
                            if not w.get("publication_year") and cr_data.get("publication_year"):
                                w["publication_year"] = cr_data["publication_year"]
                    except Exception:
                        pass

        # Do not assume a professor has no publications simply because OpenAlex returns no matching author:
        # fall back to Crossref author + IIT Kharagpur affiliation search when OpenAlex works are empty.
        crossref_searched = False
        if not works:
            crossref_searched = True
            cr_candidates = self._get_cached_crossref_works(prof_name, limit=8)
            valid_cr_works = []
            best_cr_score = 0.0
            for cw in cr_candidates:
                # Verify at least one authorship on the paper has IIT Kharagpur affiliation
                paper_has_kgp = any(
                    any(
                        kw in (inst.get("display_name") or "").lower()
                        for kw in ["kharagpur", "iit kgp", "iit-kgp", "iitkgp"]
                    )
                    for auth in (cw.get("authorships") or [])
                    for inst in (auth.get("institutions") or [])
                )
                if not paper_has_kgp:
                    continue
                a_score, a_ev, a_pos = self.disambiguator.evaluate_publication_authorship(prof_name, cw)
                if a_score >= 0.50:
                    valid_cr_works.append(cw)
                    if a_score > best_cr_score:
                        best_cr_score = a_score
                    # Extract ORCID if present on high-confidence authorship
                    if a_score >= 0.85 and not matched_orcid:
                        for auth in cw.get("authorships") or []:
                            a_obj = auth.get("author") or {}
                            if self.disambiguator.calculate_name_similarity(prof_name, a_obj.get("display_name", "")) >= 0.95:
                                if a_obj.get("orcid"):
                                    matched_orcid = a_obj["orcid"]
                                    break

            if valid_cr_works:
                works = valid_cr_works[:self.max_works]
                if not openalex_author_id:
                    author_match_score = best_cr_score
                    author_match_status = (
                        VerificationStatus.PENDING.value
                        if best_cr_score >= 0.85
                        else VerificationStatus.NEEDS_REVIEW.value
                    )
                    author_match_evidence = "Crossref DOI & IIT Kharagpur affiliation match"

        return {
            "prof_id": prof_id,
            "status": author_match_status,
            "score": author_match_score,
            "evidence": author_match_evidence,
            "openalex_author_id": openalex_author_id,
            "orcid": matched_orcid,
            "works": works,
            "crossref_searched": crossref_searched
        }

    def _persist_fetched_result(
        self,
        db: Session,
        professor: Professor,
        result: Dict,
        verify_with_crossref: bool = False
    ) -> Dict[str, int]:
        stats = {
            "publications_added": 0,
            "publications_linked": 0,
            "ambiguous_candidates": 0,
            "skipped_existing": 0
        }

        author_match_status = result["status"]
        author_match_score = result["score"]
        author_match_evidence = result["evidence"]
        openalex_author_id = result["openalex_author_id"]
        matched_orcid = result["orcid"]
        works = result["works"]
        crossref_searched = result.get("crossref_searched", False)

        # Record OpenAlex author lookup provenance when OpenAlex ID matched or OpenAlex was directly queried
        if openalex_author_id or not getattr(self.openalex, "daily_budget_exhausted", False):
            existing_lookup = db.query(DataSource).filter(
                DataSource.entity_type == "professor",
                DataSource.entity_id == professor.id,
                DataSource.source_name == "openalex_author_lookup"
            ).first()
            if not existing_lookup:
                db.add(DataSource(
                    entity_type="professor",
                    entity_id=professor.id,
                    source_name="openalex_author_lookup",
                    source_url=openalex_author_id or "https://api.openalex.org/authors",
                    http_status=200,
                    error_message=None if openalex_author_id else "No confident OpenAlex author match",
                    verification_status=(
                        VerificationStatus.NEEDS_REVIEW.value
                        if author_match_status == "needs_review"
                        else VerificationStatus.PENDING.value
                    )
                ))

        if crossref_searched:
            existing_cr_lookup = db.query(DataSource).filter(
                DataSource.entity_type == "professor",
                DataSource.entity_id == professor.id,
                DataSource.source_name == "crossref_author_lookup"
            ).first()
            if not existing_cr_lookup:
                db.add(DataSource(
                    entity_type="professor",
                    entity_id=professor.id,
                    source_name="crossref_author_lookup",
                    source_url=f"https://api.crossref.org/works?query.author={professor.name}",
                    http_status=200,
                    error_message=None if works else "No IIT Kharagpur-affiliated Crossref works matched",
                    verification_status=(
                        VerificationStatus.NEEDS_REVIEW.value
                        if author_match_status == "needs_review"
                        else VerificationStatus.PENDING.value
                    )
                ))

        if author_match_status == "rejected" or (not openalex_author_id and not works):
            return stats

        if author_match_status == "needs_review":
            stats["ambiguous_candidates"] += 1
        else:
            if openalex_author_id and not professor.openalex_author_id:
                professor.openalex_author_id = openalex_author_id
            if matched_orcid and not professor.orcid:
                professor.orcid = matched_orcid

        for work in works:
            if not work.get("title"):
                continue

            auth_score, auth_evidence, auth_pos = self.disambiguator.evaluate_publication_authorship(
                professor_name=professor.name,
                work=work
            )

            if author_match_status == "needs_review":
                combined_score = min(author_match_score, auth_score if auth_score > 0 else author_match_score)
                combined_status = VerificationStatus.NEEDS_REVIEW.value
            else:
                combined_score = max(auth_score, 0.85) if auth_score >= 0.70 else auth_score
                combined_status = (
                    VerificationStatus.PENDING.value
                    if combined_score >= 0.80
                    else VerificationStatus.NEEDS_REVIEW.value
                )

            evidence_parts = [p for p in [author_match_evidence, auth_evidence] if p]
            full_evidence = "; ".join(evidence_parts) or "OpenAlex author match"

            journal_or_conf = work.get("journal_or_conference")
            authors_str = work.get("authors_list")
            crossref_verified = bool(work.get("_crossref_enriched"))
            if crossref_verified:
                full_evidence += "; DOI metadata enriched via Crossref"

            existing_pub = find_existing_publication(
                db=db,
                openalex_id=work.get("openalex_id"),
                doi=work.get("doi")
            )

            pub_source_name = work.get("source_name") or "openalex"
            if not existing_pub:
                pub = Publication(
                    openalex_id=work.get("openalex_id"),
                    doi=work.get("doi"),
                    title=work["title"],
                    abstract=work.get("abstract"),
                    publication_year=work.get("publication_year"),
                    journal_or_conference=journal_or_conf,
                    authors_list=authors_str,
                    paper_url=work.get("paper_url"),
                    source_url=work.get("source_url") or work.get("openalex_id"),
                    source_name=pub_source_name,
                    verification_status=combined_status,
                    citation_count=work.get("citation_count", 0)
                )
                db.add(pub)
                db.flush()
                stats["publications_added"] += 1

                if pub_source_name == "openalex":
                    db.add(DataSource(
                        entity_type="publication",
                        entity_id=pub.id,
                        source_name="openalex",
                        source_url=work.get("openalex_id") or work.get("paper_url") or "",
                        http_status=200,
                        verification_status=combined_status
                    ))
                if crossref_verified and work.get("doi"):
                    db.add(DataSource(
                        entity_type="publication",
                        entity_id=pub.id,
                        source_name="crossref",
                        source_url=f"https://api.crossref.org/works/{work['doi']}",
                        http_status=200,
                        verification_status=combined_status
                    ))
            else:
                pub = existing_pub
                if work.get("abstract") and not pub.abstract:
                    pub.abstract = work.get("abstract")
                if journal_or_conf and not pub.journal_or_conference:
                    pub.journal_or_conference = journal_or_conf
                if authors_str and not pub.authors_list:
                    pub.authors_list = authors_str
                if work.get("source_url") and not pub.source_url:
                    pub.source_url = work.get("source_url")
                if work.get("citation_count", 0) > pub.citation_count:
                    pub.citation_count = work.get("citation_count", 0)
                stats["skipped_existing"] += 1

            for topic_name in work.get("topics", []):
                topic = get_or_create_topic(db, topic_name)
                if topic and topic not in pub.topics:
                    pub.topics.append(topic)

            link = db.query(ProfessorPublication).filter(
                ProfessorPublication.professor_id == professor.id,
                ProfessorPublication.publication_id == pub.id
            ).first()

            if not link:
                link = ProfessorPublication(
                    professor_id=professor.id,
                    publication_id=pub.id,
                    author_position=auth_pos or work.get("author_position"),
                    openalex_author_id=openalex_author_id,
                    affiliation_evidence=full_evidence,
                    confidence_score=combined_score,
                    verification_status=combined_status
                )
                db.add(link)
                stats["publications_linked"] += 1
            else:
                link.confidence_score = max(link.confidence_score, combined_score)
                if not link.openalex_author_id and openalex_author_id:
                    link.openalex_author_id = openalex_author_id

            if combined_status == VerificationStatus.VERIFIED.value:
                professor.has_publications = True

        return stats

    def fetch_for_professor(
        self,
        db: Session,
        professor: Professor,
        verify_with_crossref: bool = False
    ) -> Dict[str, int]:
        """Single-professor OpenAlex + Crossref fetch and persistence."""
        prof_topics = [t.topic_name for t in professor.topics]
        result = self._fetch_network_data_for_professor(
            prof_id=professor.id,
            prof_name=professor.name,
            prof_topics=prof_topics,
            known_orcid=professor.orcid,
            known_openalex_id=professor.openalex_author_id
        )
        stats = self._persist_fetched_result(db, professor, result, verify_with_crossref=verify_with_crossref)
        db.commit()
        return stats

    def fetch_for_professors_batch(
        self,
        db: Session,
        professors: List[Professor],
        verify_with_crossref: bool = True,
        max_workers: int = 5,
        batch_size: int = 40
    ) -> Dict[str, int]:
        """
        Incrementally fetches and persists OpenAlex publications across a list of professors
        in parallel batches with automatic resume support.
        """
        totals = {
            "publications_added": 0,
            "publications_linked": 0,
            "ambiguous_candidates": 0,
            "skipped_existing": 0
        }
        total_profs = len(professors)

        for start_idx in range(0, total_profs, batch_size):
            batch = professors[start_idx:start_idx + batch_size]
            prof_map = {p.id: p for p in batch}
            results_by_id: Dict[int, Dict] = {}

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_pid = {
                    executor.submit(
                        self._fetch_network_data_for_professor,
                        p.id,
                        p.name,
                        [t.topic_name for t in p.topics],
                        p.orcid,
                        p.openalex_author_id
                    ): p.id
                    for p in batch
                }
                for future in as_completed(future_to_pid):
                    pid = future_to_pid[future]
                    try:
                        results_by_id[pid] = future.result()
                    except Exception as e:
                        logger.error(f"Error in OpenAlex worker for professor_id={pid}: {e}")

            for p in batch:
                res = results_by_id.get(p.id)
                if not res:
                    continue
                try:
                    st = self._persist_fetched_result(
                        db=db,
                        professor=p,
                        result=res,
                        verify_with_crossref=verify_with_crossref
                    )
                    for k, v in st.items():
                        totals[k] += v
                except Exception as e:
                    logger.error(f"Error persisting publications for {p.name}: {e}")

            db.commit()
            logger.info(
                f"Publication batch progress: {min(start_idx + batch_size, total_profs)}/{total_profs} professors "
                f"(added={totals['publications_added']}, linked={totals['publications_linked']}, "
                f"ambiguous={totals['ambiguous_candidates']})"
            )

        return totals
