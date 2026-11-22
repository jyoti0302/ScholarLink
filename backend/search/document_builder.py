"""
Phase 2A Step 3: Deterministic Multi-Evidence DocumentBuilder.

Reads the relational source-of-truth tables (`professors`, `departments`, `publications`,
`professor_publications`, `research_projects`, `professor_projects`, `research_topics`)
and materializes unified `SearchDocument` records without modifying any source table.
"""
import hashlib
import json
import re
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from datetime import datetime
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.database.models import (
    Department,
    EvidenceType,
    Professor,
    ProfessorProject,
    ProfessorPublication,
    Publication,
    ResearchTopic,
    SearchDocument,
    VerificationStatus,
)

DOCUMENT_ID_NAMESPACE = uuid.UUID("8f5c7e90-6c44-4b2e-9b1f-3a2d4e5f6a7b")
CANDIDATE_DISCLOSURE_LABEL = "Possible publication — authorship not yet verified"

_KNOWN_RESEARCH_TYPOS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bNatural\s+Language\s+Pocessing\b", re.IGNORECASE), "Natural Language Processing"),
)


def normalize_known_research_typos(text: str) -> str:
    """Normalizes specific verified typos in scraped research text without altering DB records."""
    if not text:
        return text
    result = text
    for pattern, replacement in _KNOWN_RESEARCH_TYPOS:
        result = pattern.sub(replacement, result)
    return result


def resolve_project_source_url(
    proj_source_url: Optional[str],
    prof_source_url: Optional[str],
) -> Optional[str]:
    """
    Selects the project evidence source_url for a specific professor.
    Preserves genuine project-specific URLs, rejects another professor's `/faculty/`
    profile URL, and falls back to the current professor's own profile URL.
    """
    cleaned_proj = (proj_source_url or "").strip()
    cleaned_prof = (prof_source_url or "").strip() or None
    if not cleaned_proj:
        return cleaned_prof
    if "/faculty/" in cleaned_proj.lower() and cleaned_prof:
        if cleaned_proj.rstrip("/").lower() != cleaned_prof.rstrip("/").lower():
            return cleaned_prof
    return cleaned_proj


def make_deterministic_document_id(
    evidence_type: str,
    source_table: str,
    source_id: int,
    professor_id: Optional[int],
    chunk_index: int = 0,
) -> str:
    """Generates a deterministic UUIDv5 string for an evidence document."""
    prof_part = professor_id if professor_id is not None else 0
    key = f"{evidence_type}:{source_table}:{source_id}:{prof_part}:{chunk_index}"
    return str(uuid.uuid5(DOCUMENT_ID_NAMESPACE, key))


def compute_sha256(text_value: str) -> str:
    return hashlib.sha256((text_value or "").encode("utf-8")).hexdigest()


def chunk_biography_text(text: str, max_chars: int = 900, overlap_chars: int = 180) -> List[str]:
    """
    Splits a biography into sentence-boundary chunks of roughly ~180-220 tokens (~900 chars)
    with sentence overlap so long biographies do not dilute single-vector representations.
    """
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    if not sentences:
        return [cleaned[:max_chars]]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sent in sentences:
        if current and current_len + len(sent) + 1 > max_chars:
            chunks.append(" ".join(current))
            # Retain trailing sentences up to overlap_chars
            overlap: List[str] = []
            ov_len = 0
            for prev_sent in reversed(current):
                if ov_len + len(prev_sent) + 1 <= overlap_chars or not overlap:
                    overlap.insert(0, prev_sent)
                    ov_len += len(prev_sent) + 1
                else:
                    break
            current = overlap
            current_len = sum(len(s) for s in current) + max(0, len(current) - 1)

        current.append(sent)
        current_len += len(sent) + (1 if len(current) > 1 else 0)

    if current:
        last_chunk = " ".join(current)
        if not chunks or last_chunk != chunks[-1]:
            chunks.append(last_chunk)

    return chunks


def split_interest_phrases(raw_interests: Optional[str]) -> List[str]:
    """Splits a professor's research_interests text into distinct, clean phrases."""
    if not raw_interests:
        return []
    parts = re.split(r"[,;\n|•]+", raw_interests)
    seen = set()
    phrases: List[str] = []
    for p in parts:
        cl = re.sub(r"\s+", " ", p).strip(" .-\t")
        if len(cl) >= 3 and cl.lower() not in seen:
            seen.add(cl.lower())
            phrases.append(cl)
    return phrases


def _summarize_topics(topics: Iterable[ResearchTopic]) -> Tuple[List[str], List[str], List[str], bool, bool]:
    """
    Extracts sorted unique (canonical_topics, domains, areas, has_generic_root_only, has_noisy_topics).
    Noisy artifact topics (`is_noisy_artifact=True`) are excluded from `canonical_topics`.
    """
    canonical_set = set()
    domain_set = set()
    area_set = set()
    non_generic_count = 0
    generic_count = 0
    noisy_count = 0

    for t in topics:
        if getattr(t, "is_noisy_artifact", False):
            noisy_count += 1
            continue
        cname = (getattr(t, "canonical_topic_name", None) or t.topic_name or "").strip()
        if cname:
            canonical_set.add(cname)
        if getattr(t, "domain_name", None):
            domain_set.add(t.domain_name)
        if getattr(t, "area_name", None):
            area_set.add(t.area_name)
        if getattr(t, "is_generic_root", False):
            generic_count += 1
        else:
            non_generic_count += 1

    has_generic_root_only = bool(generic_count > 0 and non_generic_count == 0)
    has_noisy_topics = noisy_count > 0
    return (
        sorted(canonical_set),
        sorted(domain_set),
        sorted(area_set),
        has_generic_root_only,
        has_noisy_topics,
    )


class DocumentBuilder:
    """Builds and synchronizes `SearchDocument` rows from relational source tables."""

    def build_candidate_documents(
        self,
        db: Session,
        department_codes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generates candidate document dicts in memory from the relational source of truth.
        Does not modify any source tables.
        """
        dept_query = db.query(Department)
        if department_codes:
            dept_query = dept_query.filter(Department.code.in_(department_codes))
        departments = dept_query.order_by(Department.id.asc()).all()
        dept_ids = {d.id for d in departments}

        docs: List[Dict[str, Any]] = []

        # 1. Department contextual documents (Tier 5 weak contextual evidence)
        for dept in departments:
            text_content = f"Department: {dept.name}" + (
                f" ({dept.academic_unit})" if dept.academic_unit else ""
            )
            doc_id = make_deterministic_document_id(
                EvidenceType.DEPARTMENT_CONTEXT.value,
                "departments",
                dept.id,
                professor_id=None,
                chunk_index=0,
            )
            docs.append({
                "document_id": doc_id,
                "professor_id": None,
                "university_id": dept.university_id,
                "department_id": dept.id,
                "evidence_type": EvidenceType.DEPARTMENT_CONTEXT.value,
                "source_table": "departments",
                "source_id": dept.id,
                "link_id": None,
                "chunk_index": 0,
                "chunk_count": 1,
                "title": f"Department of {dept.name}",
                "text_content": text_content,
                "canonical_topics_json": "[]",
                "topic_domains_json": "[]",
                "topic_areas_json": "[]",
                "metadata_json": json.dumps(
                    {
                        "department_code": dept.code,
                        "academic_unit": dept.academic_unit,
                    },
                    sort_keys=True,
                ),
                "source_url": dept.official_url,
                "verification_status": VerificationStatus.VERIFIED.value,
                "confidence_score": 0.5,
                "content_hash": compute_sha256(text_content),
            })

        # Load active (non-rejected) professors in target departments using selectinload to avoid Cartesian join explosion
        prof_query = (
            db.query(Professor)
            .options(
                selectinload(Professor.topics),
                selectinload(Professor.professor_projects).joinedload(ProfessorProject.project),
                selectinload(Professor.professor_publications)
                .joinedload(ProfessorPublication.publication)
                .selectinload(Publication.topics),
                joinedload(Professor.department),
            )
            .filter(Professor.verification_status != VerificationStatus.REJECTED.value)
        )
        if department_codes:
            prof_query = prof_query.filter(Professor.department_id.in_(dept_ids))

        professors = prof_query.order_by(Professor.id.asc()).all()

        for prof in professors:
            univ_id = prof.department.university_id if prof.department else 1
            dept_id = prof.department_id
            prof_source_url = prof.profile_url or prof.source_url
            c_topics, t_domains, t_areas, gen_only, has_noisy = _summarize_topics(prof.topics)
            c_topics_json = json.dumps(c_topics)
            t_domains_json = json.dumps(t_domains)
            t_areas_json = json.dumps(t_areas)

            # 2. Official Research Interests (Tier 2 evidence: summary + phrase-level docs)
            interests_raw = normalize_known_research_typos((prof.research_interests or "").strip())
            group_raw = (prof.research_group or "").strip()
            if len(interests_raw) > 2 or len(group_raw) > 2:
                phrases = split_interest_phrases(interests_raw)
                parts = []
                if interests_raw:
                    parts.append(f"Research interests: {interests_raw}")
                if group_raw:
                    parts.append(f"Research group: {group_raw}")
                if c_topics:
                    parts.append(f"Canonical topics: {', '.join(c_topics)}")
                text_content = ". ".join(parts)
                doc_id = make_deterministic_document_id(
                    EvidenceType.RESEARCH_INTEREST.value,
                    "professors",
                    prof.id,
                    professor_id=prof.id,
                    chunk_index=0,
                )
                docs.append({
                    "document_id": doc_id,
                    "professor_id": prof.id,
                    "university_id": univ_id,
                    "department_id": dept_id,
                    "evidence_type": EvidenceType.RESEARCH_INTEREST.value,
                    "source_table": "professors",
                    "source_id": prof.id,
                    "link_id": None,
                    "chunk_index": 0,
                    "chunk_count": 1,
                    "title": f"Research Interests — {prof.name}",
                    "text_content": text_content,
                    "canonical_topics_json": c_topics_json,
                    "topic_domains_json": t_domains_json,
                    "topic_areas_json": t_areas_json,
                    "metadata_json": json.dumps(
                        {
                            "professor_name": prof.name,
                            "raw_phrases": phrases,
                            "research_group": group_raw or None,
                            "has_generic_root_only": gen_only,
                            "has_noisy_topics": has_noisy,
                        },
                        sort_keys=True,
                    ),
                    "source_url": prof_source_url,
                    "verification_status": prof.verification_status,
                    "confidence_score": 1.0,
                    "content_hash": compute_sha256(text_content),
                })

            # 3. Faculty Biographies (Tier 4 evidence: sentence-chunked)
            bio_raw = (prof.biography or "").strip()
            if len(bio_raw) > 10:
                bio_chunks = chunk_biography_text(bio_raw)
                for idx, chunk_text in enumerate(bio_chunks):
                    doc_id = make_deterministic_document_id(
                        EvidenceType.BIOGRAPHY.value,
                        "professors",
                        prof.id,
                        professor_id=prof.id,
                        chunk_index=idx,
                    )
                    docs.append({
                        "document_id": doc_id,
                        "professor_id": prof.id,
                        "university_id": univ_id,
                        "department_id": dept_id,
                        "evidence_type": EvidenceType.BIOGRAPHY.value,
                        "source_table": "professors",
                        "source_id": prof.id,
                        "link_id": None,
                        "chunk_index": idx,
                        "chunk_count": len(bio_chunks),
                        "title": f"Biography ({idx + 1}/{len(bio_chunks)}) — {prof.name}",
                        "text_content": chunk_text,
                        "canonical_topics_json": c_topics_json,
                        "topic_domains_json": t_domains_json,
                        "topic_areas_json": t_areas_json,
                        "metadata_json": json.dumps(
                            {
                                "professor_name": prof.name,
                                "chunk_index": idx,
                                "chunk_count": len(bio_chunks),
                                "has_generic_root_only": gen_only,
                            },
                            sort_keys=True,
                        ),
                        "source_url": prof_source_url,
                        "verification_status": prof.verification_status,
                        "confidence_score": 1.0,
                        "content_hash": compute_sha256(chunk_text),
                    })

            # 4. Research Projects (Tier 3 evidence: one document per ProfessorProject link)
            for pproj in sorted(prof.professor_projects, key=lambda x: x.id):
                proj = pproj.project
                if not proj or not (proj.title or "").strip():
                    continue
                role_str = pproj.role or "Principal Investigator"
                sponsor_str = proj.sponsor or ""
                status_str = proj.status or "completed"
                cat_str = proj.project_category or "sponsored_research"

                parts = [proj.title.strip()]
                if sponsor_str:
                    parts.append(f"Sponsor: {sponsor_str}")
                parts.append(f"Role: {role_str}")
                parts.append(f"Status: {status_str}")
                text_content = ". ".join(parts)

                doc_id = make_deterministic_document_id(
                    EvidenceType.RESEARCH_PROJECT.value,
                    "research_projects",
                    proj.id,
                    professor_id=prof.id,
                    chunk_index=0,
                )
                docs.append({
                    "document_id": doc_id,
                    "professor_id": prof.id,
                    "university_id": univ_id,
                    "department_id": dept_id,
                    "evidence_type": EvidenceType.RESEARCH_PROJECT.value,
                    "source_table": "research_projects",
                    "source_id": proj.id,
                    "link_id": pproj.id,
                    "chunk_index": 0,
                    "chunk_count": 1,
                    "title": proj.title.strip(),
                    "text_content": text_content,
                    "canonical_topics_json": c_topics_json,
                    "topic_domains_json": t_domains_json,
                    "topic_areas_json": t_areas_json,
                    "metadata_json": json.dumps(
                        {
                            "professor_name": prof.name,
                            "project_category": cat_str,
                            "role": role_str,
                            "sponsor": sponsor_str or None,
                            "status": status_str,
                            "original_title": proj.original_title,
                        },
                        sort_keys=True,
                    ),
                    "source_url": resolve_project_source_url(proj.source_url, prof_source_url),
                    "verification_status": prof.verification_status,
                    "confidence_score": 1.0 if role_str == "Principal Investigator" else 0.85,
                    "content_hash": compute_sha256(text_content),
                })

            # 5. Publications: Strictly separate VERIFIED_PUBLICATION vs CANDIDATE_PUBLICATION
            for ppub in sorted(prof.professor_publications, key=lambda x: x.id):
                link_status = ppub.verification_status
                if link_status == VerificationStatus.REJECTED.value:
                    continue
                pub = ppub.publication
                if not pub or not (pub.title or "").strip():
                    continue

                if link_status == VerificationStatus.VERIFIED.value:
                    ev_type = EvidenceType.VERIFIED_PUBLICATION.value
                    disclosure_label = None
                else:
                    # pending or needs_review -> candidate_publication (never verified authorship)
                    ev_type = EvidenceType.CANDIDATE_PUBLICATION.value
                    disclosure_label = CANDIDATE_DISCLOSURE_LABEL

                pub_topics, pub_domains, pub_areas, pub_gen_only, pub_noisy = _summarize_topics(pub.topics)
                merged_topics = sorted(set(c_topics) | set(pub_topics))
                merged_domains = sorted(set(t_domains) | set(pub_domains))
                merged_areas = sorted(set(t_areas) | set(pub_areas))

                abstract_str = (pub.abstract or "").strip()
                if abstract_str:
                    text_content = f"{pub.title.strip()}. {abstract_str}"
                else:
                    text_content = pub.title.strip()

                doc_id = make_deterministic_document_id(
                    ev_type,
                    "publications",
                    pub.id,
                    professor_id=prof.id,
                    chunk_index=0,
                )
                docs.append({
                    "document_id": doc_id,
                    "professor_id": prof.id,
                    "university_id": univ_id,
                    "department_id": dept_id,
                    "evidence_type": ev_type,
                    "source_table": "publications",
                    "source_id": pub.id,
                    "link_id": ppub.id,
                    "chunk_index": 0,
                    "chunk_count": 1,
                    "title": pub.title.strip(),
                    "text_content": text_content,
                    "canonical_topics_json": json.dumps(merged_topics),
                    "topic_domains_json": json.dumps(merged_domains),
                    "topic_areas_json": json.dumps(merged_areas),
                    "metadata_json": json.dumps(
                        {
                            "professor_name": prof.name,
                            "doi": pub.doi,
                            "openalex_id": pub.openalex_id,
                            "publication_year": pub.publication_year,
                            "journal_or_conference": pub.journal_or_conference,
                            "author_position": ppub.author_position,
                            "citation_count": pub.citation_count,
                            "affiliation_evidence": ppub.affiliation_evidence,
                            "link_verification_status": link_status,
                            "candidate_disclosure_label": disclosure_label,
                            "has_generic_root_only": pub_gen_only,
                            "has_noisy_topics": pub_noisy,
                        },
                        sort_keys=True,
                    ),
                    "source_url": pub.source_url or pub.paper_url or prof_source_url,
                    "verification_status": link_status,
                    "confidence_score": float(ppub.confidence_score or 0.0),
                    "content_hash": compute_sha256(text_content),
                })

        return docs

    def rebuild_and_sync_documents(
        self,
        db: Session,
        department_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Idempotently synchronizes `search_documents` with the relational source tables.
        Returns counts of inserted, updated, deleted, and unchanged documents, plus per-type totals.
        """
        candidates = self.build_candidate_documents(db, department_codes=department_codes)
        cand_by_id = {c["document_id"]: c for c in candidates}

        existing_query = db.query(SearchDocument)
        if department_codes:
            dept_ids = [
                r[0]
                for r in db.query(Department.id).filter(Department.code.in_(department_codes)).all()
            ]
            existing_query = existing_query.filter(SearchDocument.department_id.in_(dept_ids))

        existing_rows = existing_query.all()
        existing_by_id = {r.document_id: r for r in existing_rows}

        inserted = 0
        updated = 0
        unchanged = 0
        deleted = 0

        # Delete stale documents that are no longer generated
        for doc_id, row in existing_by_id.items():
            if doc_id not in cand_by_id:
                db.delete(row)
                deleted += 1

        # Insert or update candidate documents
        MutableFields = (
            "content_hash",
            "title",
            "text_content",
            "canonical_topics_json",
            "topic_domains_json",
            "topic_areas_json",
            "metadata_json",
            "source_url",
            "verification_status",
            "confidence_score",
            "chunk_count",
        )
        now_dt = datetime.utcnow()
        to_insert: List[Dict[str, Any]] = []
        for doc_id, cand in cand_by_id.items():
            row = existing_by_id.get(doc_id)
            if row is None:
                cand_row = dict(cand)
                cand_row.setdefault("created_at", now_dt)
                cand_row.setdefault("updated_at", now_dt)
                to_insert.append(cand_row)
                inserted += 1
            else:
                changed = any(getattr(row, f) != cand[f] for f in MutableFields)
                if changed:
                    for f in MutableFields:
                        setattr(row, f, cand[f])
                    row.updated_at = now_dt
                    updated += 1
                else:
                    unchanged += 1

        if to_insert:
            for i in range(0, len(to_insert), 1000):
                db.bulk_insert_mappings(SearchDocument, to_insert[i : i + 1000])

        db.commit()

        by_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for c in candidates:
            et = c["evidence_type"]
            st = c["verification_status"]
            by_type[et] = by_type.get(et, 0) + 1
            by_status[st] = by_status.get(st, 0) + 1

        unique_hashes = len({c["content_hash"] for c in candidates})

        return {
            "total_documents": len(candidates),
            "unique_content_hashes": unique_hashes,
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
            "deleted": deleted,
            "by_evidence_type": by_type,
            "by_verification_status": by_status,
        }
