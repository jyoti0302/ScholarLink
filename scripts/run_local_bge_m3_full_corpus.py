"""
Resumable Local GPU Runner for Remaining Full-Corpus `BAAI/bge-m3` Embeddings (Phase 2A Step 6).

Designed for `C:\\GPU_Environment\\python.exe` (PyTorch + CUDA + FlagEmbedding) without
modifying PostgreSQL, Qdrant, or any existing pilot embeddings.

Features:
- Processes ONLY the uncached hashes in `data/full_corpus/full_corpus_remaining_texts.jsonl` (13,624)
- Cross-checks `data/pilot/pilot_cs_me_bt_embeddings_v1.jsonl.gz` (read-only) to confirm 0 overlap
- Uses native `BAAI/bge-m3` with `use_fp16=True`, `batch_size=8`, `max_length=512`
- Generates both 1,024-d dense vectors and learned sparse `lexical_weights`
- Durable incremental checkpointing every 64 completed records via `flush()` + `os.fsync()`
- Crash-safe recovery (ignores truncated trailing checkpoint lines, deduplicates by `content_hash`)
- Atomic `.jsonl.gz` finalization and manifest generation
- Supports `--dry-run` and `--validate-only` modes
"""
import argparse
import gzip
import importlib.metadata
import json
import math
import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

DEFAULT_INPUT = Path("data/full_corpus/full_corpus_remaining_texts.jsonl")
DEFAULT_CHECKPOINT = Path("data/full_corpus/full_corpus_remaining_checkpoint.jsonl")
DEFAULT_OUTPUT = Path("data/full_corpus/full_corpus_remaining_embeddings_v1.jsonl.gz")
DEFAULT_MANIFEST = Path("data/full_corpus/full_corpus_embedding_manifest.json")
DEFAULT_PILOT_GZ = Path("data/pilot/pilot_cs_me_bt_embeddings_v1.jsonl.gz")

MODEL_NAME = "BAAI/bge-m3"
EXPECTED_DIM = 1024


def validate_embedding_record(rec: Dict, expected_dim: int = EXPECTED_DIM) -> Optional[str]:
    """Returns None if valid, otherwise an error description."""
    chash = rec.get("content_hash")
    if not isinstance(chash, str) or not chash:
        return "missing content_hash"
    dense = rec.get("dense")
    if not isinstance(dense, list) or len(dense) != expected_dim:
        return f"invalid dense dimension ({len(dense) if isinstance(dense, list) else type(dense)})"
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in dense):
        return "non-finite dense value"
    s_idx = rec.get("sparse_indices")
    s_val = rec.get("sparse_values")
    if not isinstance(s_idx, list) or not isinstance(s_val, list) or len(s_idx) != len(s_val):
        return "sparse_indices/sparse_values length mismatch"
    if any(not isinstance(i, int) or isinstance(i, bool) or i < 0 for i in s_idx):
        return "invalid sparse index"
    if any(s_idx[k] >= s_idx[k + 1] for k in range(len(s_idx) - 1)):
        return "sparse_indices not strictly increasing"
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in s_val):
        return "invalid sparse weight"
    return None


def load_input_texts(input_path: Path) -> List[Dict[str, str]]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    items: List[Dict[str, str]] = []
    seen: Set[str] = set()
    with open(input_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            chash = obj["content_hash"]
            if chash in seen:
                raise ValueError(f"Duplicate content_hash '{chash}' in input at line {line_no}")
            seen.add(chash)
            items.append({"content_hash": chash, "text_content": obj["text_content"]})
    return items


def load_pilot_hashes(pilot_gz_path: Optional[Path]) -> Set[str]:
    if not pilot_gz_path or not pilot_gz_path.exists():
        return set()
    hashes: Set[str] = set()
    with gzip.open(pilot_gz_path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                hashes.add(json.loads(line)["content_hash"])
    return hashes


def load_valid_checkpoint(checkpoint_path: Path) -> Tuple[Dict[str, str], int]:
    """
    Reads an existing checkpoint JSONL safely.
    - Deduplicates by `content_hash` (keeps first valid record).
    - Ignores any corrupted/truncated trailing line from an interrupted write.
    Returns `(valid_lines_by_hash, ignored_corrupt_lines)`.
    """
    if not checkpoint_path.exists():
        return {}, 0
    valid_by_hash: Dict[str, str] = {}
    ignored = 0
    with open(checkpoint_path, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
                err = validate_embedding_record(rec)
                if err is not None:
                    ignored += 1
                    continue
                chash = rec["content_hash"]
                if chash not in valid_by_hash:
                    valid_by_hash[chash] = json.dumps(rec)
            except Exception:
                ignored += 1
    return valid_by_hash, ignored


def validate_output_archive(
    output_path: Path,
    expected_hashes: Set[str],
) -> Dict[str, int]:
    if not output_path.exists():
        raise FileNotFoundError(f"Output archive not found: {output_path}")
    seen: Set[str] = set()
    opener = gzip.open if str(output_path).endswith(".gz") else open
    with opener(output_path, "rt", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            rec = json.loads(raw)
            err = validate_embedding_record(rec)
            if err is not None:
                raise ValueError(f"Invalid record at line {line_no} ({rec.get('content_hash')}): {err}")
            chash = rec["content_hash"]
            if chash in seen:
                raise ValueError(f"Duplicate content_hash '{chash}' in {output_path} at line {line_no}")
            seen.add(chash)

    missing = expected_hashes - seen
    extra = seen - expected_hashes
    if missing:
        raise ValueError(f"Missing {len(missing)} expected hashes in {output_path}")
    if extra:
        raise ValueError(f"Found {len(extra)} unexpected hashes in {output_path}")
    return {"validated_records": len(seen), "missing": 0, "extra": 0}


def default_flag_encoder_factory(model_name: str, batch_size: int, max_length: int, use_fp16: bool):
    import torch
    from FlagEmbedding import BGEM3FlagModel  # type: ignore

    fp16 = bool(use_fp16 and torch.cuda.is_available())
    model = BGEM3FlagModel(model_name, use_fp16=fp16)

    def _encode(texts: List[str]) -> Tuple[List[List[float]], List[Dict]]:
        out = model.encode(
            texts,
            batch_size=batch_size,
            max_length=max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        return out["dense_vecs"], out["lexical_weights"]

    return _encode, fp16


def run_local_embedding(
    input_path: Path = DEFAULT_INPUT,
    checkpoint_path: Path = DEFAULT_CHECKPOINT,
    output_path: Path = DEFAULT_OUTPUT,
    manifest_path: Path = DEFAULT_MANIFEST,
    pilot_gz_path: Optional[Path] = DEFAULT_PILOT_GZ,
    batch_size: int = 8,
    max_length: int = 512,
    checkpoint_every: int = 64,
    use_fp16: bool = True,
    dry_run: bool = False,
    validate_only: bool = False,
    encoder_factory: Optional[Callable] = None,
) -> Dict:
    items = load_input_texts(input_path)
    expected_hashes = {x["content_hash"] for x in items}
    pilot_hashes = load_pilot_hashes(pilot_gz_path)
    overlap_with_pilot = expected_hashes & pilot_hashes

    if validate_only:
        val_stats = validate_output_archive(output_path, expected_hashes)
        return {
            "mode": "validate_only",
            "input_unique_hashes": len(items),
            "pilot_hashes_preserved": len(pilot_hashes),
            "pilot_overlap": len(overlap_with_pilot),
            **val_stats,
        }

    valid_ckpt, ignored_corrupt = load_valid_checkpoint(checkpoint_path)
    remaining = [x for x in items if x["content_hash"] not in valid_ckpt]

    if dry_run:
        return {
            "mode": "dry_run",
            "model_name": MODEL_NAME,
            "batch_size": batch_size,
            "max_length": max_length,
            "checkpoint_every": checkpoint_every,
            "use_fp16": use_fp16,
            "input_unique_hashes": len(items),
            "pilot_embeddings_preserved": len(pilot_hashes),
            "pilot_overlap_count": len(overlap_with_pilot),
            "existing_valid_checkpoint_records": len(valid_ckpt),
            "ignored_corrupt_checkpoint_lines": ignored_corrupt,
            "remaining_to_encode": len(remaining),
            "output_path": str(output_path),
            "checkpoint_path": str(checkpoint_path),
        }

    if overlap_with_pilot:
        raise RuntimeError(
            f"Refusing to run: {len(overlap_with_pilot)} input hashes overlap with pilot embeddings."
        )

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Rewrite checkpoint cleanly only if corrupt lines were detected, preserving all valid records
    if ignored_corrupt > 0:
        tmp_ckpt = checkpoint_path.with_suffix(".jsonl.tmp")
        with open(tmp_ckpt, "w", encoding="utf-8") as tf:
            for item in items:
                line = valid_ckpt.get(item["content_hash"])
                if line:
                    tf.write(line + "\n")
            tf.flush()
            os.fsync(tf.fileno())
        os.replace(tmp_ckpt, checkpoint_path)

    peak_gpu_mb = 0.0
    elapsed = 0.0
    actual_fp16 = use_fp16

    if remaining:
        factory = encoder_factory or default_flag_encoder_factory
        encode_fn, actual_fp16 = factory(MODEL_NAME, batch_size, max_length, use_fp16)

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
        except ImportError:
            pass

        t0 = time.time()
        newly_encoded = 0
        since_sync = 0

        with open(checkpoint_path, "a", encoding="utf-8") as ckpt_f:
            for start in range(0, len(remaining), batch_size):
                batch = remaining[start : start + batch_size]
                texts = [b["text_content"] for b in batch]
                dense_vecs, lexical_weights = encode_fn(texts)

                for rec, d_vec, lex_dict in zip(batch, dense_vecs, lexical_weights):
                    # Filter AFTER rounding to 6 decimals so FP16 sub-5e-7 weights that round
                    # to 0.0 are omitted cleanly while preserving all non-zero learned sparse terms.
                    pairs = sorted(
                        (
                            (int(k), round(float(v), 6))
                            for k, v in lex_dict.items()
                            if math.isfinite(float(v)) and round(float(v), 6) > 0.0
                        ),
                        key=lambda x: x[0],
                    )
                    row = {
                        "content_hash": rec["content_hash"],
                        "dense": [round(float(x), 6) for x in d_vec],
                        "sparse_indices": [p[0] for p in pairs],
                        "sparse_values": [p[1] for p in pairs],
                    }
                    err = validate_embedding_record(row)
                    if err is not None:
                        raise ValueError(f"Encoded invalid record for {rec['content_hash']}: {err}")
                    row_str = json.dumps(row)
                    ckpt_f.write(row_str + "\n")
                    valid_ckpt[rec["content_hash"]] = row_str
                    newly_encoded += 1
                    since_sync += 1

                if since_sync >= checkpoint_every:
                    ckpt_f.flush()
                    os.fsync(ckpt_f.fileno())
                    since_sync = 0
                    rate = newly_encoded / max(time.time() - t0, 1e-6) * 60.0
                    print(
                        f"[checkpoint] {len(valid_ckpt)}/{len(items)} total "
                        f"(+{newly_encoded} this run, {rate:.1f} docs/min)",
                        flush=True,
                    )

            ckpt_f.flush()
            os.fsync(ckpt_f.fileno())

        elapsed = round(time.time() - t0, 2)
        try:
            import torch
            if torch.cuda.is_available():
                peak_gpu_mb = round(torch.cuda.max_memory_allocated() / (1024 ** 2), 2)
        except ImportError:
            pass

    # Finalize atomically in input order (deduplicated)
    tmp_gz = output_path.with_suffix(".gz.tmp")
    written = 0
    with gzip.open(tmp_gz, "wt", encoding="utf-8") as gz_f:
        for item in items:
            line = valid_ckpt.get(item["content_hash"])
            if not line:
                raise RuntimeError(f"Missing checkpoint record for {item['content_hash']}")
            gz_f.write(line + "\n")
            written += 1
    os.replace(tmp_gz, output_path)

    # Validate finalized archive before writing manifest
    validate_output_archive(output_path, expected_hashes)

    lib_versions = {}
    for pkg in ("FlagEmbedding", "torch", "transformers"):
        try:
            lib_versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            lib_versions[pkg] = "unknown"

    manifest = {
        "model_name": MODEL_NAME,
        "use_fp16": actual_fp16,
        "batch_size": batch_size,
        "max_length": max_length,
        "checkpoint_every": checkpoint_every,
        "vector_dim": EXPECTED_DIM,
        "sparse_type": "bge_m3_lexical_weights",
        "unique_texts_encoded": written,
        "pilot_embeddings_preserved": len(pilot_hashes),
        "elapsed_seconds": elapsed,
        "peak_gpu_memory_mb": peak_gpu_mb,
        "library_versions": lib_versions,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Local RTX 4050 resumable BGE-M3 runner")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pilot-embeddings", type=Path, default=DEFAULT_PILOT_GZ)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--checkpoint-every", type=int, default=64)
    parser.add_argument("--no-fp16", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    res = run_local_embedding(
        input_path=args.input,
        checkpoint_path=args.checkpoint,
        output_path=args.output,
        manifest_path=args.manifest,
        pilot_gz_path=args.pilot_embeddings,
        batch_size=args.batch_size,
        max_length=args.max_length,
        checkpoint_every=args.checkpoint_every,
        use_fp16=not args.no_fp16,
        dry_run=args.dry_run,
        validate_only=args.validate_only,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
