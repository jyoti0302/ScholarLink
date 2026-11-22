"""
Encodes all Phase 2B evaluation queries (original + expanded queries) using native
`BAAI/bge-m3` (`FlagEmbedding.BGEM3FlagModel`, FP16, max_length=512, dense + learned sparse).
Run with `C:\GPU_Environment\python.exe` (or any environment with FlagEmbedding + PyTorch).
"""
import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.search.query_understanding import QueryExpansionService


def main():
    queries_path = Path("data/evaluation/phase2b_queries.jsonl")
    out_path = Path("data/evaluation/phase2b_query_embeddings.json")

    exp_svc = QueryExpansionService(max_expansions=5)
    queries = [json.loads(l) for l in open(queries_path, "r", encoding="utf-8") if l.strip()]

    unique_query_texts = []
    seen = set()
    expansions_by_qid = {}
    for q in queries:
        exp = exp_svc.expand(q["original_query"])
        expansions_by_qid[q["query_id"]] = [
            {"query_text": eq.query_text, "query_kind": eq.query_kind, "weight": eq.weight}
            for eq in exp.queries
        ]
        for eq in exp.queries:
            if eq.query_text not in seen:
                seen.add(eq.query_text)
                unique_query_texts.append(eq.query_text)

    import torch
    from FlagEmbedding import BGEM3FlagModel

    fp16 = torch.cuda.is_available()
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=fp16)
    res = model.encode(
        unique_query_texts,
        batch_size=8,
        max_length=512,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )

    embeddings = {}
    for q_txt, d_vec, lex_dict in zip(unique_query_texts, res["dense_vecs"], res["lexical_weights"]):
        pairs = sorted(
            (
                (int(k), round(float(v), 6))
                for k, v in lex_dict.items()
                if math.isfinite(float(v)) and round(float(v), 6) > 0.0
            ),
            key=lambda x: x[0],
        )
        embeddings[q_txt] = {
            "dense": [round(float(x), 6) for x in d_vec],
            "sparse_indices": [p[0] for p in pairs],
            "sparse_values": [p[1] for p in pairs],
        }

    out_path.write_text(
        json.dumps(
            {
                "model_name": "BAAI/bge-m3",
                "use_fp16": fp16,
                "max_length": 512,
                "vector_dim": 1024,
                "unique_query_texts_encoded": len(unique_query_texts),
                "expansions_by_query_id": expansions_by_qid,
                "embeddings": embeddings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "queries_count": len(queries),
                "unique_query_texts_encoded": len(unique_query_texts),
                "output_path": str(out_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
