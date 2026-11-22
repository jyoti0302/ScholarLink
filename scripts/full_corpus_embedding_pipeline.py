"""
Phase 2A Step 6: Full-Corpus BGE-M3 Export, Validation, Import & Qdrant Sync Pipeline.

Reuses `pilot_embedding_pipeline.py` validation and `backend.search` sync primitives.
Preserves all existing `embedding_cache` records (including the 2,908 CS/ME/BT pilot vectors)
and exports only uncached `content_hash` + `text_content` pairs for GPU encoding.

Usage:
  1. Export remaining uncached unique texts across all IIT Kharagpur departments:
     python scripts/full_corpus_embedding_pipeline.py export

  2. After running `notebooks/bge_m3_full_corpus_embedding_colab.ipynb` on Colab/Kaggle GPU,
     validate, import into PostgreSQL `embedding_cache`, and sync all 19,493 documents to Qdrant:
     python scripts/full_corpus_embedding_pipeline.py import-and-sync --input data/full_corpus/full_corpus_remaining_embeddings_v1.jsonl.gz
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Set

from qdrant_client import QdrantClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database.connection import SessionLocal
from backend.database.models import EmbeddingCache, SearchDocument
from backend.search.embedding import DEFAULT_TARGET_DIM, DEFAULT_TARGET_MODEL, EmbeddingCacheStore
from backend.search.index_sync import IndexSyncService
from backend.search.qdrant_index import QdrantIndexManager
from scripts.pilot_embedding_pipeline import CacheOnlyEmbeddingProvider, validate_and_load_embeddings


def export_uncached_full_corpus_texts(
    output_path: Path,
    model_name: str = DEFAULT_TARGET_MODEL,
) -> Dict:
    """
    Exports only uncached `(content_hash, text_content)` pairs from `search_documents`
    so existing pilot embeddings in `embedding_cache` are preserved and never regenerated.
    """
    db = SessionLocal()
    try:
        cached_hashes: Set[str] = {
            r[0]
            for r in db.query(EmbeddingCache.content_hash)
            .filter(EmbeddingCache.embedding_model == model_name)
            .all()
        }

        rows = (
            db.query(SearchDocument.content_hash, SearchDocument.text_content)
            .order_by(SearchDocument.id.asc())
            .all()
        )

        seen_all: Set[str] = set()
        to_export: List[Dict[str, str]] = []
        for chash, text in rows:
            if chash not in seen_all:
                seen_all.add(chash)
                if chash not in cached_hashes:
                    to_export.append({"content_hash": chash, "text_content": text})

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in to_export:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return {
            "total_search_documents": len(rows),
            "total_unique_content_hashes": len(seen_all),
            "already_cached_hashes_preserved": len(seen_all & cached_hashes),
            "uncached_unique_texts_exported": len(to_export),
            "output_path": str(output_path),
        }
    finally:
        db.close()


def import_and_sync_full_corpus(
    input_path: Path,
    qdrant_path: str = "data/qdrant_full",
) -> Dict:
    """
    Validates the newly generated embeddings against all uncached `search_documents` hashes,
    imports them into PostgreSQL `embedding_cache`, and synchronizes all 19,493 documents
    (including the 3,204 pilot documents from `embedding_cache`) into Qdrant.
    """
    db = SessionLocal()
    try:
        all_doc_hashes: Set[str] = {
            r[0] for r in db.query(SearchDocument.content_hash).all()
        }
        already_cached: Set[str] = {
            r[0]
            for r in db.query(EmbeddingCache.content_hash)
            .filter(EmbeddingCache.embedding_model == DEFAULT_TARGET_MODEL)
            .all()
        }
        expected_new_hashes = all_doc_hashes - already_cached

        loaded = validate_and_load_embeddings(input_path, expected_hashes=expected_new_hashes)
        added_cache = EmbeddingCacheStore.save_cached_batch(
            db=db,
            items=loaded,
            model_name=DEFAULT_TARGET_MODEL,
            vector_dim=DEFAULT_TARGET_DIM,
        )
        db.commit()

        q_client = QdrantClient(path=qdrant_path)
        q_mgr = QdrantIndexManager(client=q_client, vector_dim=DEFAULT_TARGET_DIM)
        sync_svc = IndexSyncService(index_manager=q_mgr, embedding_provider=CacheOnlyEmbeddingProvider())
        sync_stats = sync_svc.sync_documents(db, department_codes=None)

        # Verify idempotent re-sync
        resync_stats = sync_svc.sync_documents(db, department_codes=None)

        total_cached = (
            db.query(EmbeddingCache.content_hash)
            .filter(EmbeddingCache.embedding_model == DEFAULT_TARGET_MODEL)
            .count()
        )
        return {
            "validated_new_embeddings": len(loaded),
            "cache_records_inserted": added_cache,
            "total_embedding_cache_records": total_cached,
            "qdrant_sync": sync_stats,
            "qdrant_idempotent_resync": resync_stats,
            "qdrant_total_points": q_mgr.count_points(),
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Full-corpus BGE-M3 export/import pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export")
    p_exp.add_argument("--output", default="data/full_corpus/full_corpus_remaining_texts.jsonl")

    p_imp = sub.add_parser("import-and-sync")
    p_imp.add_argument("--input", required=True)
    p_imp.add_argument("--qdrant-path", default="data/qdrant_full")

    args = parser.parse_args()
    if args.cmd == "export":
        res = export_uncached_full_corpus_texts(Path(args.output))
    else:
        res = import_and_sync_full_corpus(Path(args.input), qdrant_path=args.qdrant_path)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
