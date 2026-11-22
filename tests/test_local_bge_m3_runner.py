import gzip
import json
import tempfile
from pathlib import Path
import pytest

from scripts.pilot_embedding_pipeline import validate_and_load_embeddings
from scripts.run_local_bge_m3_full_corpus import (
    EXPECTED_DIM,
    load_valid_checkpoint,
    run_local_embedding,
)


def _fake_encoder_factory(model_name, batch_size, max_length, use_fp16):
    call_counter = {"texts": 0}

    def _encode(texts):
        call_counter["texts"] += len(texts)
        dense = [[0.01] * EXPECTED_DIM for _ in texts]
        sparse = [{10 + i: 0.75, 200 + i: 0.42} for i, _ in enumerate(texts)]
        return dense, sparse

    _encode.call_counter = call_counter
    return _encode, use_fp16


def test_local_runner_dry_run_resume_and_import_compatibility():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "remaining.jsonl"
        ckpt = tmp / "checkpoint.jsonl"
        out = tmp / "embeddings_v1.jsonl.gz"
        manifest = tmp / "manifest.json"
        pilot = tmp / "pilot.jsonl.gz"

        # 1. Create 10 synthetic remaining texts + 1 pilot embedding with distinct hash
        records = [{"content_hash": f"hash_{i:03d}", "text_content": f"Research text {i}"} for i in range(10)]
        inp.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

        with gzip.open(pilot, "wt", encoding="utf-8") as pf:
            pf.write(json.dumps({
                "content_hash": "pilot_only_hash",
                "dense": [0.02] * EXPECTED_DIM,
                "sparse_indices": [5],
                "sparse_values": [0.9],
            }) + "\n")

        # 2. Simulate an interrupted checkpoint with 4 valid records + 1 truncated trailing line
        with open(ckpt, "w", encoding="utf-8") as cf:
            for i in range(4):
                cf.write(json.dumps({
                    "content_hash": f"hash_{i:03d}",
                    "dense": [0.05] * EXPECTED_DIM,
                    "sparse_indices": [1, 2],
                    "sparse_values": [0.5, 0.3],
                }) + "\n")
            cf.write('{"content_hash": "hash_004", "dense": [0.1')  # truncated crash line

        # 3. Dry-run must report 4 valid, 1 corrupt ignored, 6 remaining
        dry = run_local_embedding(
            input_path=inp,
            checkpoint_path=ckpt,
            output_path=out,
            manifest_path=manifest,
            pilot_gz_path=pilot,
            batch_size=8,
            checkpoint_every=64,
            dry_run=True,
        )
        assert dry["input_unique_hashes"] == 10
        assert dry["pilot_embeddings_preserved"] == 1
        assert dry["existing_valid_checkpoint_records"] == 4
        assert dry["ignored_corrupt_checkpoint_lines"] == 1
        assert dry["remaining_to_encode"] == 6
        assert not out.exists()

        # 4. Run completion with fake encoder: only the 6 missing hashes are encoded
        encoded_hashes = []

        def _tracking_factory(model_name, batch_size, max_length, use_fp16):
            fn, fp16 = _fake_encoder_factory(model_name, batch_size, max_length, use_fp16)

            def _wrapped(texts):
                encoded_hashes.extend(texts)
                return fn(texts)

            return _wrapped, fp16

        res = run_local_embedding(
            input_path=inp,
            checkpoint_path=ckpt,
            output_path=out,
            manifest_path=manifest,
            pilot_gz_path=pilot,
            batch_size=4,
            checkpoint_every=4,
            encoder_factory=_tracking_factory,
        )
        assert len(encoded_hashes) == 6
        assert res["unique_texts_encoded"] == 10
        assert out.exists() and manifest.exists()

        # 5. Validate with existing import validator (`validate_and_load_embeddings`)
        expected = {r["content_hash"] for r in records}
        loaded = validate_and_load_embeddings(out, expected_hashes=expected)
        assert len(loaded) == 10
        # Existing 4 checkpoint records must be preserved untouched (0.05, not 0.01)
        assert loaded["hash_000"].dense[0] == pytest.approx(0.05)
        assert loaded["hash_009"].dense[0] == pytest.approx(0.01)

        # 6. Validate-only mode succeeds
        val_res = run_local_embedding(
            input_path=inp,
            output_path=out,
            pilot_gz_path=pilot,
            validate_only=True,
        )
        assert val_res["validated_records"] == 10
        assert val_res["missing"] == 0


def test_sub_threshold_fp16_sparse_weight_regression():
    """Regression test for tiny FP16 lexical_weights (e.g. 2.384e-7) that round to 0.0 at 6 decimals."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        inp = tmp / "rem.jsonl"
        ckpt = tmp / "ckpt.jsonl"
        out = tmp / "out.jsonl.gz"
        manifest = tmp / "manifest.json"
        inp.write_text(
            json.dumps({"content_hash": "d5a5e64a_test", "text_content": "Dr. Brajesh Kr. Dubey"}) + "\n",
            encoding="utf-8",
        )

        def _tiny_weight_factory(model_name, batch_size, max_length, use_fp16):
            def _encode(texts):
                dense = [[0.01] * EXPECTED_DIM for _ in texts]
                sparse = [{"2356": 2.384185791015625e-07, "4500": 0.184231}]
                return dense, sparse

            return _encode, use_fp16

        res = run_local_embedding(
            input_path=inp,
            checkpoint_path=ckpt,
            output_path=out,
            manifest_path=manifest,
            pilot_gz_path=None,
            batch_size=8,
            checkpoint_every=64,
            encoder_factory=_tiny_weight_factory,
        )
        assert res["unique_texts_encoded"] == 1
        loaded = validate_and_load_embeddings(out, expected_hashes={"d5a5e64a_test"})
        assert loaded["d5a5e64a_test"].sparse_indices == [4500]
        assert loaded["d5a5e64a_test"].sparse_values == [pytest.approx(0.184231)]
