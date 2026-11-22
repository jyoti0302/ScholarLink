"""
Phase 2A Step 4: Content-Hash Incremental Synchronization Service (`IndexSyncService`).

Synchronizes `SearchDocument` rows from PostgreSQL into Qdrant while:
1. Deduplicating embedding calls via `EmbeddingCacheStore` (`content_hash` + `embedding_model`)
2. Performing payload-only updates (`set_payload`) when `content_hash` is unchanged
3. Deleting stale points from Qdrant when a `SearchDocument` is removed or rejected.
"""
import json
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.database.models import Department, IndexSyncState, SearchDocument
from backend.search.document_builder import compute_sha256
from backend.search.embedding import EmbeddingCacheStore, EmbeddingOutput, EmbeddingProvider
from backend.search.qdrant_index import QdrantIndexManager


def build_qdrant_payload(doc: SearchDocument) -> Dict[str, Any]:
    """Builds the lean Qdrant payload from a `SearchDocument` ORM row."""
    meta = json.loads(doc.metadata_json or "{}")
    return {
        "document_id": doc.document_id,
        "professor_id": doc.professor_id,
        "university_id": doc.university_id,
        "department_id": doc.department_id,
        "evidence_type": doc.evidence_type,
        "source_table": doc.source_table,
        "source_id": doc.source_id,
        "link_id": doc.link_id,
        "chunk_index": doc.chunk_index,
        "chunk_count": doc.chunk_count,
        "title": doc.title,
        "text_snippet": (doc.text_content or "")[:600],
        "canonical_topics": json.loads(doc.canonical_topics_json or "[]"),
        "topic_domains": json.loads(doc.topic_domains_json or "[]"),
        "topic_areas": json.loads(doc.topic_areas_json or "[]"),
        "source_url": doc.source_url,
        "verification_status": doc.verification_status,
        "confidence_score": float(doc.confidence_score),
        "content_hash": doc.content_hash,
        "metadata": meta,
    }


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    return compute_sha256(json.dumps(payload, sort_keys=True))


class IndexSyncService:
    """Diff-based synchronization between PostgreSQL `search_documents` and Qdrant."""

    def __init__(self, index_manager: QdrantIndexManager, embedding_provider: EmbeddingProvider):
        self.index_manager = index_manager
        self.provider = embedding_provider

    def sync_documents(
        self,
        db: Session,
        department_codes: Optional[List[str]] = None,
        batch_size: int = 64,
    ) -> Dict[str, int]:
        """
        Synchronizes `search_documents` (optionally scoped to `department_codes`) with Qdrant.
        """
        self.index_manager.ensure_collection()
        model_name = self.provider.model_name
        collection_name = self.index_manager.collection_name

        doc_query = db.query(SearchDocument)
        if department_codes:
            dept_ids = [
                r[0]
                for r in db.query(Department.id).filter(Department.code.in_(department_codes)).all()
            ]
            doc_query = doc_query.filter(SearchDocument.department_id.in_(dept_ids))

        docs = doc_query.order_by(SearchDocument.id.asc()).all()
        docs_by_id = {d.document_id: d for d in docs}

        sync_rows = (
            db.query(IndexSyncState)
            .filter(IndexSyncState.collection_name == collection_name)
            .all()
        )
        sync_by_id = {s.document_id: s for s in sync_rows}

        # 1. Identify deleted documents (only among synced rows in scope)
        to_delete_ids: List[str] = []
        if not department_codes:
            for doc_id, srow in list(sync_by_id.items()):
                if doc_id not in docs_by_id:
                    to_delete_ids.append(doc_id)
                    db.delete(srow)
                    del sync_by_id[doc_id]

        if to_delete_ids:
            self.index_manager.delete_documents(to_delete_ids)

        # 2. Check actual Qdrant point IDs in the target instance so switching Qdrant storage paths
        #    never falsely marks missing points as `unchanged`.
        qdrant_existing_ids = self.index_manager.get_existing_point_ids()

        # 3. Classify documents into: needs_upsert, needs_payload_only, unchanged
        needs_upsert: List[Tuple[SearchDocument, Dict[str, Any], str]] = []
        needs_payload_only: List[Tuple[SearchDocument, Dict[str, Any], str]] = []
        unchanged = 0

        for doc in docs:
            payload = build_qdrant_payload(doc)
            phash = compute_payload_hash(payload)
            srow = sync_by_id.get(doc.document_id)

            if (
                doc.document_id not in qdrant_existing_ids
                or srow is None
                or srow.content_hash != doc.content_hash
                or srow.embedding_model != model_name
            ):
                needs_upsert.append((doc, payload, phash))
            elif srow.payload_hash != phash:
                needs_payload_only.append((doc, payload, phash))
            else:
                unchanged += 1

        # 3. Resolve embeddings for `needs_upsert` using `EmbeddingCacheStore` first
        unique_hashes_needed = sorted({doc.content_hash for doc, _, _ in needs_upsert})
        cached_map = EmbeddingCacheStore.get_cached_batch(db, unique_hashes_needed, model_name)
        cache_hits = len(cached_map)

        hash_to_text: Dict[str, str] = {}
        for doc, _, _ in needs_upsert:
            if doc.content_hash not in cached_map and doc.content_hash not in hash_to_text:
                hash_to_text[doc.content_hash] = doc.text_content

        missing_hashes = list(hash_to_text.keys())
        newly_embedded: Dict[str, EmbeddingOutput] = {}
        for i in range(0, len(missing_hashes), batch_size):
            batch_hashes = missing_hashes[i : i + batch_size]
            batch_texts = [hash_to_text[h] for h in batch_hashes]
            batch_outputs = self.provider.encode(batch_texts)
            for h, emb_out in zip(batch_hashes, batch_outputs):
                newly_embedded[h] = emb_out

        if newly_embedded:
            EmbeddingCacheStore.save_cached_batch(
                db=db,
                items=newly_embedded,
                model_name=model_name,
                vector_dim=self.provider.vector_dim,
            )
            cached_map.update(newly_embedded)

        # 4. Upsert points to Qdrant and update IndexSyncState
        points_to_upsert: List[Tuple[str, EmbeddingOutput, Dict[str, Any]]] = []
        for doc, payload, phash in needs_upsert:
            emb = cached_map[doc.content_hash]
            points_to_upsert.append((doc.document_id, emb, payload))
            srow = sync_by_id.get(doc.document_id)
            if srow is None:
                db.add(
                    IndexSyncState(
                        document_id=doc.document_id,
                        collection_name=collection_name,
                        content_hash=doc.content_hash,
                        payload_hash=phash,
                        embedding_model=model_name,
                        qdrant_status="synced",
                    )
                )
            else:
                srow.content_hash = doc.content_hash
                srow.payload_hash = phash
                srow.embedding_model = model_name
                srow.qdrant_status = "synced"

        if points_to_upsert:
            self.index_manager.upsert_documents(points_to_upsert, batch_size=batch_size)

        # 5. Apply payload-only updates without re-embedding
        if needs_payload_only:
            self.index_manager.update_payloads([(doc.document_id, payload) for doc, payload, _ in needs_payload_only])
            for doc, _, phash in needs_payload_only:
                srow = sync_by_id[doc.document_id]
                srow.payload_hash = phash

        db.commit()

        return {
            "upserted": len(points_to_upsert),
            "payload_updated_only": len(needs_payload_only),
            "deleted": len(to_delete_ids),
            "unchanged": unchanged,
            "unique_hashes_embedded": len(newly_embedded),
            "embedding_cache_hits": cache_hits,
        }
