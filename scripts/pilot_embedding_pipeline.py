"""
Phase 2A Three-Department Pilot (CS, ME, BT) Embedding Export, Validation, Import & Qdrant Sync Pipeline.

Usage:
  1. Export unique pilot texts (no DB credentials or unrelated PII):
     python scripts/pilot_embedding_pipeline.py export --departments CS ME BT --output data/pilot/pilot_cs_me_bt_texts.jsonl

  2. After running `notebooks/bge_m3_pilot_embedding_colab.ipynb` on Colab/Kaggle GPU,
     validate, import into PostgreSQL `embedding_cache`, and sync to Qdrant:
     python scripts/pilot_embedding_pipeline.py import-and-sync --input data/pilot/pilot_cs_me_bt_embeddings_v1.jsonl.gz --departments CS ME BT
"""
import argparse
import gzip
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Set

from qdrant_client import QdrantClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database.connection import SessionLocal
from backend.database.models import Department, SearchDocument
from backend.search.embedding import (
    DEFAULT_TARGET_DIM,
    DEFAULT_TARGET_MODEL,
    EmbeddingCacheStore,
    EmbeddingOutput,
    EmbeddingProvider,
)
from backend.search.index_sync import IndexSyncService
from backend.search.qdrant_index import QdrantIndexManager


class CacheOnlyEmbeddingProvider(EmbeddingProvider):
    """
    Provider used during `import-and-sync`: all pilot vectors are already in `embedding_cache`.
    Raises if any unexpected uncached text is encountered.
    """

    def __init__(self, model_name: str = DEFAULT_TARGET_MODEL, vector_dim: int = DEFAULT_TARGET_DIM):
        self._model_name = model_name
        self._vector_dim = vector_dim

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def vector_dim(self) -> int:
        return self._vector_dim

    def encode(self, texts):
        raise RuntimeError(
            "CacheOnlyEmbeddingProvider cannot encode uncached texts. "
            "Ensure all pilot content_hashes are imported into embedding_cache first."
        )


def export_pilot_texts(
    department_codes: List[str],
    output_path: Path,
) -> Dict[str, int]:
    """Exports unique `(content_hash, text_content)` pairs for the specified departments."""
    db = SessionLocal()
    try:
        dept_ids = [
            r[0]
            for r in db.query(Department.id).filter(Department.code.in_(department_codes)).all()
        ]
        if not dept_ids:
            raise ValueError(f"No departments found for codes: {department_codes}")

        rows = (
            db.query(SearchDocument.content_hash, SearchDocument.text_content)
            .filter(SearchDocument.department_id.in_(dept_ids))
            .order_by(SearchDocument.id.asc())
            .all()
        )

        seen: Set[str] = set()
        unique_items: List[Dict[str, str]] = []
        for chash, text in rows:
            if chash not in seen:
                seen.add(chash)
                unique_items.append({"content_hash": chash, "text_content": text})

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in unique_items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return {
            "departments": department_codes,
            "total_search_documents": len(rows),
            "unique_texts_exported": len(unique_items),
            "output_path": str(output_path),
        }
    finally:
        db.close()


def validate_and_load_embeddings(
    input_path: Path,
    expected_hashes: Set[str],
    expected_dim: int = DEFAULT_TARGET_DIM,
) -> Dict[str, EmbeddingOutput]:
    """
    Validates imported BGE-M3 dense + sparse embeddings:
    - Exact 1,024-d dense vectors with finite values
    - Valid sparse token IDs (non-negative ints, strictly sorted) and finite positive weights
    - No duplicate content_hashes
    - No missing expected content_hashes
    """
    opener = gzip.open if str(input_path).endswith(".gz") else open
    loaded: Dict[str, EmbeddingOutput] = {}

    with opener(input_path, "rt", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            chash = rec["content_hash"]
            if chash in loaded:
                raise ValueError(f"Duplicate content_hash '{chash}' at line {line_no}")

            dense = rec["dense"]
            if len(dense) != expected_dim:
                raise ValueError(
                    f"Invalid dense dimension {len(dense)} != {expected_dim} for {chash}"
                )
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in dense):
                raise ValueError(f"Non-finite dense value in {chash}")

            s_idx = rec["sparse_indices"]
            s_val = rec["sparse_values"]
            if len(s_idx) != len(s_val):
                raise ValueError(f"Sparse indices/values length mismatch in {chash}")
            if any(not isinstance(i, int) or i < 0 for i in s_idx):
                raise ValueError(f"Invalid sparse index in {chash}")
            if any(s_idx[k] >= s_idx[k + 1] for k in range(len(s_idx) - 1)):
                raise ValueError(f"Sparse indices not strictly increasing in {chash}")
            if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in s_val):
                raise ValueError(f"Invalid sparse weight in {chash}")

            loaded[chash] = EmbeddingOutput(
                dense=[float(x) for x in dense],
                sparse_indices=s_idx,
                sparse_values=[float(x) for x in s_val],
            )

    missing = expected_hashes - set(loaded.keys())
    if missing:
        raise ValueError(f"Missing {len(missing)} expected content_hashes (sample: {list(missing)[:5]})")

    return loaded


def import_and_sync_pilot(
    input_path: Path,
    department_codes: List[str],
    qdrant_path: str = "data/qdrant_pilot",
) -> Dict:
    """Validates embeddings, imports into PostgreSQL `embedding_cache`, and syncs pilot Qdrant."""
    db = SessionLocal()
    try:
        dept_ids = [
            r[0]
            for r in db.query(Department.id).filter(Department.code.in_(department_codes)).all()
        ]
        expected_hashes = {
            r[0]
            for r in db.query(SearchDocument.content_hash)
            .filter(SearchDocument.department_id.in_(dept_ids))
            .all()
        }

        loaded = validate_and_load_embeddings(input_path, expected_hashes=expected_hashes)
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
        sync_stats = sync_svc.sync_documents(db, department_codes=department_codes)

        return {
            "validated_embeddings": len(loaded),
            "cache_records_inserted": added_cache,
            "qdrant_sync": sync_stats,
            "qdrant_total_points": q_mgr.count_points(),
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Pilot BGE-M3 export/import pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export")
    p_exp.add_argument("--departments", nargs="+", default=["CS", "ME", "BT"])
    p_exp.add_argument("--output", default="data/pilot/pilot_cs_me_bt_texts.jsonl")

    p_imp = sub.add_parser("import-and-sync")
    p_imp.add_argument("--input", required=True)
    p_imp.add_argument("--departments", nargs="+", default=["CS", "ME", "BT"])
    p_imp.add_argument("--qdrant-path", default="data/qdrant_pilot")

    args = parser.parse_args()
    if args.cmd == "export":
        res = export_pilot_texts(args.departments, Path(args.output))
    else:
        res = import_and_sync_pilot(Path(args.input), args.departments, qdrant_path=args.qdrant_path)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
