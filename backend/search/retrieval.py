"""
Phase 2A Step 7 (Stage 4): QueryEmbeddingService & HybridRetrievalService.

Critical rule:
Every user query (original or expanded) is encoded directly from its own text via
`EmbeddingProvider` (never by picking an existing document as a proxy).
Query embeddings are cached separately in memory by `(query_text, model_name)` and are
never mixed with PostgreSQL `embedding_cache` document records.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from backend.database.models import EvidenceType
from backend.search.cancellation import CancellationToken
from backend.search.embedding import EmbeddingOutput, EmbeddingProvider
from backend.search.qdrant_index import QdrantIndexManager
from backend.search.query_understanding import ExpandedQuery


# Completeness-oriented per-evidence-type retrieval ceilings.
# With score_threshold filtering (dense >= 0.40, sparse >= 0.04), limit=1000 is
# strictly exhaustive for research_interest (817 docs) and verified_publication (84 docs)
# in the current corpus while capturing all above-floor candidates for larger types.
DEFAULT_TYPE_QUOTAS: Dict[str, int] = {
    EvidenceType.VERIFIED_PUBLICATION.value: 1000,
    EvidenceType.RESEARCH_INTEREST.value: 1000,
    EvidenceType.RESEARCH_PROJECT.value: 1000,
    EvidenceType.BIOGRAPHY.value: 1000,
    EvidenceType.CANDIDATE_PUBLICATION.value: 1000,
}

DEFAULT_DENSE_SCORE_THRESHOLD: float = 0.40
DEFAULT_SPARSE_SCORE_THRESHOLD: float = 0.04


@dataclass
class RetrievedEvidenceItem:
    document_id: str
    professor_id: Optional[int]
    department_id: int
    evidence_type: str
    score: float
    rrf_rank: int
    originating_query: str
    query_kind: str
    query_weight: float
    payload: Dict[str, Any] = field(default_factory=dict)
    # Preserved raw retrieval signals (never overwritten by RRF)
    original_dense_score: float = 0.0
    original_sparse_score: float = 0.0
    expanded_dense_score: float = 0.0
    expanded_sparse_score: float = 0.0
    rrf_score: float = 0.0
    matched_queries: List[str] = field(default_factory=list)


class QueryEmbeddingService:
    """
    Encodes user and expanded queries directly via `EmbeddingProvider` with an
    in-memory query-only cache (kept strictly separate from document `embedding_cache`).
    """

    def __init__(self, provider: EmbeddingProvider):
        self.provider = provider
        self._query_cache: Dict[str, EmbeddingOutput] = {}

    def embed_queries(self, queries: Sequence[ExpandedQuery]) -> Dict[str, EmbeddingOutput]:
        missing_texts: List[str] = []
        for q in queries:
            if q.query_text not in self._query_cache and q.query_text not in missing_texts:
                missing_texts.append(q.query_text)

        if missing_texts:
            encoded = self.provider.encode(missing_texts)
            for txt, emb in zip(missing_texts, encoded):
                self._query_cache[txt] = emb

        return {q.query_text: self._query_cache[q.query_text] for q in queries}


class HybridRetrievalService:
    """
    Executes per-evidence-type hybrid (dense + sparse RRF) retrieval across original
    and expanded queries, deduplicating by `document_id` while retaining highest
    query-weighted relevance and provenance.
    """

    def __init__(
        self,
        index_manager: QdrantIndexManager,
        query_embedding_service: QueryEmbeddingService,
        type_quotas: Optional[Dict[str, int]] = None,
    ):
        self.index_manager = index_manager
        self.query_embedding_service = query_embedding_service
        self.type_quotas = dict(type_quotas or DEFAULT_TYPE_QUOTAS)

    def retrieve(
        self,
        expanded_queries: Sequence[ExpandedQuery],
        university_id: Optional[int] = None,
        department_ids: Optional[Sequence[int]] = None,
        include_candidate_publications: bool = True,
        cancel_token: Optional[CancellationToken] = None,
    ) -> List[RetrievedEvidenceItem]:
        if not expanded_queries:
            return []

        if cancel_token is not None:
            cancel_token.check("before_query_embedding")

        q_embeddings = self.query_embedding_service.embed_queries(expanded_queries)

        # Check immediately after GPU/CPU embedding finishes safely before starting Qdrant work
        if cancel_token is not None:
            cancel_token.check("after_query_embedding")

        best_by_doc: Dict[str, RetrievedEvidenceItem] = {}

        active_types = [
            et
            for et in self.type_quotas.keys()
            if include_candidate_publications or et != EvidenceType.CANDIDATE_PUBLICATION.value
        ]

        for eq in expanded_queries:
            q_emb = q_embeddings[eq.query_text]
            is_original = eq.query_kind == "original"
            for ev_type in active_types:
                if cancel_token is not None:
                    cancel_token.check("dense_retrieval")
                limit = self.type_quotas[ev_type]
                dense_hits = self.index_manager.dense_search(
                    query_embedding=q_emb,
                    evidence_types=[ev_type],
                    university_id=university_id,
                    department_ids=department_ids,
                    limit=limit,
                    score_threshold=DEFAULT_DENSE_SCORE_THRESHOLD,
                )
                if cancel_token is not None:
                    cancel_token.check("sparse_retrieval")
                sparse_hits = self.index_manager.sparse_search(
                    query_embedding=q_emb,
                    evidence_types=[ev_type],
                    university_id=university_id,
                    department_ids=department_ids,
                    limit=limit,
                    score_threshold=DEFAULT_SPARSE_SCORE_THRESHOLD,
                )
                dense_by_id = {h["document_id"]: (idx + 1, float(h["score"]), h["payload"]) for idx, h in enumerate(dense_hits)}
                sparse_by_id = {h["document_id"]: (idx + 1, float(h["score"]), h["payload"]) for idx, h in enumerate(sparse_hits)}

                all_doc_ids = set(dense_by_id.keys()) | set(sparse_by_id.keys())
                fused_docs = []
                for doc_id in all_doc_ids:
                    rrf_val = 0.0
                    d_score = 0.0
                    s_score = 0.0
                    pl = None
                    if doc_id in dense_by_id:
                        d_rank, d_score, pl = dense_by_id[doc_id]
                        rrf_val += 1.0 / (60.0 + d_rank)
                    if doc_id in sparse_by_id:
                        s_rank, s_score, s_pl = sparse_by_id[doc_id]
                        rrf_val += 1.0 / (60.0 + s_rank)
                        if pl is None:
                            pl = s_pl
                    fused_docs.append((doc_id, rrf_val, d_score, s_score, pl or {}))

                fused_docs.sort(key=lambda x: x[1], reverse=True)
                # Normalize RRF relative to max theoretical 2-list rank-1 score (2/61) so RRF stays on 0-1 scale
                max_rrf = 2.0 / 61.0
                for rank_idx, (doc_id, rrf_val, d_score, s_score, pl) in enumerate(fused_docs, start=1):
                    meta = pl.get("metadata") or {}
                    # Exclude administrative/grant projects from topic discovery
                    if (
                        ev_type == EvidenceType.RESEARCH_PROJECT.value
                        and meta.get("project_category") == "administrative_or_grant"
                    ):
                        continue

                    norm_rrf = min(1.0, rrf_val / max_rrf)
                    weighted_score = norm_rrf * eq.weight
                    prev = best_by_doc.get(doc_id)
                    if prev is None:
                        best_by_doc[doc_id] = RetrievedEvidenceItem(
                            document_id=doc_id,
                            professor_id=pl.get("professor_id"),
                            department_id=int(pl.get("department_id", 0)),
                            evidence_type=ev_type,
                            score=weighted_score,
                            rrf_rank=rank_idx,
                            originating_query=eq.query_text,
                            query_kind=eq.query_kind,
                            query_weight=eq.weight,
                            payload=pl,
                            original_dense_score=d_score if is_original else 0.0,
                            original_sparse_score=s_score if is_original else 0.0,
                            expanded_dense_score=0.0 if is_original else d_score,
                            expanded_sparse_score=0.0 if is_original else s_score,
                            rrf_score=norm_rrf,
                            matched_queries=[eq.query_text],
                        )
                    else:
                        if is_original:
                            prev.original_dense_score = max(prev.original_dense_score, d_score)
                            prev.original_sparse_score = max(prev.original_sparse_score, s_score)
                        else:
                            prev.expanded_dense_score = max(prev.expanded_dense_score, d_score)
                            prev.expanded_sparse_score = max(prev.expanded_sparse_score, s_score)
                        if eq.query_text not in prev.matched_queries:
                            prev.matched_queries.append(eq.query_text)
                        if weighted_score > prev.score:
                            prev.score = weighted_score
                            prev.rrf_rank = rank_idx
                            prev.rrf_score = norm_rrf
                            prev.originating_query = eq.query_text
                            prev.query_kind = eq.query_kind
                            prev.query_weight = eq.weight

        results = list(best_by_doc.values())
        results.sort(key=lambda x: x.score, reverse=True)
        return results
