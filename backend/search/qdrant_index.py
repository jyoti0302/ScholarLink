"""
Phase 2A Step 4: Qdrant Collection Configuration & Hybrid Indexing Interface.

Manages:
- Single unified collection (`research_evidence_v1`) + alias (`research_evidence`)
- Named dense vector (`"dense"`, Cosine, 1024-d default for BAAI/bge-m3)
- Named sparse vector (`"sparse"`, learned lexical weights / sparse term weights)
- Payload field indexes (`professor_id`, `department_id`, `university_id`, `evidence_type`,
  `verification_status`, `confidence_score`)
- Upsert, payload-only update (`set_payload`), point deletion, and per-type RRF hybrid search.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from backend.search.embedding import DEFAULT_TARGET_DIM, EmbeddingOutput

DEFAULT_COLLECTION_NAME = "research_evidence_v1"
DEFAULT_COLLECTION_ALIAS = "research_evidence"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


class QdrantIndexManager:
    """High-level interface over QdrantClient for multi-evidence indexing and hybrid retrieval."""

    def __init__(
        self,
        client: Optional[QdrantClient] = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        alias_name: str = DEFAULT_COLLECTION_ALIAS,
        vector_dim: int = DEFAULT_TARGET_DIM,
    ):
        self.client = client or QdrantClient(location=":memory:")
        self.collection_name = collection_name
        self.alias_name = alias_name
        self.vector_dim = vector_dim

    def ensure_collection(self) -> bool:
        """
        Creates `collection_name` with named dense + sparse vectors and payload indexes
        if it does not already exist. Returns True if newly created, False if already present.
        """
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection_name in existing:
            return False

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: VectorParams(
                    size=self.vector_dim,
                    distance=Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: SparseVectorParams()
            },
        )

        # Create payload indexes for fast filtering
        index_specs = [
            ("professor_id", PayloadSchemaType.INTEGER),
            ("department_id", PayloadSchemaType.INTEGER),
            ("university_id", PayloadSchemaType.INTEGER),
            ("evidence_type", PayloadSchemaType.KEYWORD),
            ("verification_status", PayloadSchemaType.KEYWORD),
            ("confidence_score", PayloadSchemaType.FLOAT),
        ]
        for field_name, schema_type in index_specs:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema_type,
                )
            except Exception:
                # In-memory Qdrant accepts create_payload_index or no-ops gracefully
                pass

        return True

    def upsert_documents(
        self,
        points_data: Sequence[Tuple[str, EmbeddingOutput, Dict[str, Any]]],
        batch_size: int = 128,
    ) -> int:
        """
        Upserts `(document_id, embedding_output, payload)` tuples into Qdrant.
        """
        if not points_data:
            return 0
        self.ensure_collection()

        total = 0
        for start in range(0, len(points_data), batch_size):
            batch = points_data[start : start + batch_size]
            points = [
                PointStruct(
                    id=doc_id,
                    vector={
                        DENSE_VECTOR_NAME: emb.dense,
                        SPARSE_VECTOR_NAME: SparseVector(
                            indices=emb.sparse_indices,
                            values=emb.sparse_values,
                        ),
                    },
                    payload=payload,
                )
                for doc_id, emb, payload in batch
            ]
            self.client.upsert(collection_name=self.collection_name, points=points)
            total += len(points)
        return total

    def update_payloads(self, updates: Sequence[Tuple[str, Dict[str, Any]]]) -> int:
        """Updates payload metadata in-place without re-embedding the vector."""
        for doc_id, payload in updates:
            self.client.set_payload(
                collection_name=self.collection_name,
                payload=payload,
                points=[doc_id],
            )
        return len(updates)

    def delete_documents(self, document_ids: Sequence[str]) -> int:
        """Deletes points by `document_id` from Qdrant."""
        if not document_ids:
            return 0
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=list(document_ids)),
        )
        return len(document_ids)

    def count_points(self, evidence_type: Optional[str] = None, exact: bool = True) -> int:
        flt = None
        if evidence_type:
            flt = Filter(must=[FieldCondition(key="evidence_type", match=MatchValue(value=evidence_type))])
        return int(self.client.count(collection_name=self.collection_name, count_filter=flt, exact=exact).count)

    def get_existing_point_ids(self, batch_size: int = 1000) -> set:
        """Scrolls all existing point IDs currently stored in this Qdrant collection."""
        existing_ids = set()
        offset = None
        while True:
            pts, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            for pt in pts:
                existing_ids.add(str(pt.id))
            if offset is None:
                break
        return existing_ids

    def _build_filter(
        self,
        evidence_types: Optional[Sequence[str]] = None,
        university_id: Optional[int] = None,
        department_ids: Optional[Sequence[int]] = None,
    ) -> Optional[Filter]:
        must_conditions = []
        if evidence_types:
            if len(evidence_types) == 1:
                must_conditions.append(
                    FieldCondition(key="evidence_type", match=MatchValue(value=evidence_types[0]))
                )
            else:
                must_conditions.append(
                    FieldCondition(key="evidence_type", match=MatchAny(any=list(evidence_types)))
                )
        if university_id is not None:
            must_conditions.append(
                FieldCondition(key="university_id", match=MatchValue(value=university_id))
            )
        if department_ids:
            must_conditions.append(
                FieldCondition(key="department_id", match=MatchAny(any=list(department_ids)))
            )
        return Filter(must=must_conditions) if must_conditions else None

    def dense_search(
        self,
        query_embedding: EmbeddingOutput,
        evidence_types: Optional[Sequence[str]] = None,
        university_id: Optional[int] = None,
        department_ids: Optional[Sequence[int]] = None,
        limit: int = 30,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Executes dense-only retrieval against the `dense` named vector."""
        q_filter = self._build_filter(evidence_types, university_id, department_ids)
        res = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding.dense,
            using=DENSE_VECTOR_NAME,
            query_filter=q_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [
            {
                "document_id": str(pt.id),
                "score": float(pt.score),
                "payload": dict(pt.payload or {}),
            }
            for pt in res.points
        ]

    def sparse_search(
        self,
        query_embedding: EmbeddingOutput,
        evidence_types: Optional[Sequence[str]] = None,
        university_id: Optional[int] = None,
        department_ids: Optional[Sequence[int]] = None,
        limit: int = 30,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Executes learned-sparse-only retrieval against the `sparse` named vector."""
        if not query_embedding.sparse_indices:
            return []
        q_filter = self._build_filter(evidence_types, university_id, department_ids)
        res = self.client.query_points(
            collection_name=self.collection_name,
            query=SparseVector(
                indices=query_embedding.sparse_indices,
                values=query_embedding.sparse_values,
            ),
            using=SPARSE_VECTOR_NAME,
            query_filter=q_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [
            {
                "document_id": str(pt.id),
                "score": float(pt.score),
                "payload": dict(pt.payload or {}),
            }
            for pt in res.points
        ]

    def hybrid_search(
        self,
        query_embedding: EmbeddingOutput,
        evidence_types: Optional[Sequence[str]] = None,
        university_id: Optional[int] = None,
        department_ids: Optional[Sequence[int]] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Executes a hybrid (dense + sparse RRF-fused) query against the collection.
        """
        q_filter = self._build_filter(evidence_types, university_id, department_ids)
        prefetch_limit = max(limit * 2, 40)

        prefetches = [
            Prefetch(
                query=query_embedding.dense,
                using=DENSE_VECTOR_NAME,
                filter=q_filter,
                limit=prefetch_limit,
            )
        ]
        if query_embedding.sparse_indices:
            prefetches.append(
                Prefetch(
                    query=SparseVector(
                        indices=query_embedding.sparse_indices,
                        values=query_embedding.sparse_values,
                    ),
                    using=SPARSE_VECTOR_NAME,
                    filter=q_filter,
                    limit=prefetch_limit,
                )
            )

        res = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=prefetches,
            query=FusionQuery(fusion=Fusion.RRF),
            query_filter=q_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            {
                "document_id": str(pt.id),
                "score": float(pt.score),
                "payload": dict(pt.payload or {}),
            }
            for pt in res.points
        ]
