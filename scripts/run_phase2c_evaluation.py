"""
Phase 2C Evaluation Runner (In-Memory Read-Only Cached Optimization).

Loads the 19,493 points from `data/qdrant_full` (read-only) into a separate
`QdrantClient(":memory:")` instance, verifies exact point count and dense+sparse vectors,
caches `(mode, query_text, ev_type, limit)` retrieval calls across Experiments A-D,
and saves `evaluation/results/phase2c_before_after.json`.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database.connection import SessionLocal
from backend.database.models import Department, EvidenceType, Professor
from backend.search.embedding import DEFAULT_TARGET_DIM
from backend.search.evaluation import compute_system_level_metrics
from backend.search.qdrant_index import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, QdrantIndexManager
from backend.search.query_understanding import QueryExpansionService
from backend.search.ranking import (
    MatchExplanationService,
    ProfessorAggregationService,
    ProfessorRankingService,
    SearchService,
)
from backend.search.relevance_validation import RelevanceValidationService
from backend.search.retrieval import DEFAULT_TYPE_QUOTAS, QueryEmbeddingService, RetrievedEvidenceItem
from scripts.run_phase2b_evaluation import PrecomputedQueryEmbeddingProvider, serialize_match


def load_full_collection_into_memory(source_path: str = "data/qdrant_full") -> Tuple[QdrantClient, QdrantIndexManager]:
    """Reads all 19,493 points from `data/qdrant_full` without modifying it and loads them into `:memory:`."""
    src_client = QdrantClient(path=source_path)
    mem_client = QdrantClient(location=":memory:")
    mem_mgr = QdrantIndexManager(client=mem_client, vector_dim=DEFAULT_TARGET_DIM)
    mem_mgr.ensure_collection()

    offset = None
    batch_structs: List[PointStruct] = []
    loaded = 0
    while True:
        pts, offset = src_client.scroll(
            collection_name=mem_mgr.collection_name,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        for pt in pts:
            vecs = pt.vector or {}
            sp = vecs.get(SPARSE_VECTOR_NAME)
            batch_structs.append(
                PointStruct(
                    id=pt.id,
                    vector={
                        DENSE_VECTOR_NAME: list(vecs[DENSE_VECTOR_NAME]),
                        SPARSE_VECTOR_NAME: SparseVector(
                            indices=list(sp.indices),
                            values=list(sp.values),
                        ),
                    },
                    payload=dict(pt.payload or {}),
                )
            )
        if len(batch_structs) >= 500 or (offset is None and batch_structs):
            mem_client.upsert(collection_name=mem_mgr.collection_name, points=batch_structs)
            loaded += len(batch_structs)
            batch_structs = []
        if offset is None:
            break

    src_client.close()

    exact_cnt = mem_mgr.count_points(exact=True)
    assert exact_cnt == 19493, f"Expected 19,493 points in memory, got {exact_cnt}"
    sample_pts, _ = mem_client.scroll(
        collection_name=mem_mgr.collection_name, limit=2, with_payload=False, with_vectors=True
    )
    for sp in sample_pts:
        assert DENSE_VECTOR_NAME in sp.vector and len(sp.vector[DENSE_VECTOR_NAME]) == 1024
        assert SPARSE_VECTOR_NAME in sp.vector and len(sp.vector[SPARSE_VECTOR_NAME].indices) > 0

    print(f"[init] Loaded and verified {exact_cnt} points (dense 1024-d + sparse) into :memory: Qdrant", flush=True)
    return mem_client, mem_mgr


class CachedQdrantRetriever:
    """Caches `(mode, query_text, ev_type, limit)` hits across Experiments A, B, C, and D."""

    def __init__(self, q_mgr: QdrantIndexManager):
        self.q_mgr = q_mgr
        self._cache: Dict[Tuple[str, str, str, int], List[Dict]] = {}
        self.retrieval_calls = 0
        self.cache_hits = 0

    def search(self, mode: str, query_text: str, emb, ev_type: str, limit: int) -> List[Dict]:
        key = (mode, query_text, ev_type, limit)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        self.retrieval_calls += 1
        if mode == "dense":
            hits = self.q_mgr.dense_search(emb, evidence_types=[ev_type], limit=limit)
        elif mode == "sparse":
            hits = self.q_mgr.sparse_search(emb, evidence_types=[ev_type], limit=limit)
        else:
            raise ValueError(f"Unsupported base mode: {mode}")
        self._cache[key] = hits
        return hits


def run_mode_with_gate(
    retriever: CachedQdrantRetriever,
    q_emb_svc: QueryEmbeddingService,
    queries_list,
    mode: str,  # "dense" | "sparse" | "hybrid"
    orig_query: str,
    profs_map,
    depts_map,
    validator: RelevanceValidationService,
    top_k: int = 10,
):
    t_ret0 = time.perf_counter()
    q_embs = q_emb_svc.embed_queries(queries_list)
    best_by_doc: Dict[str, RetrievedEvidenceItem] = {}

    for eq in queries_list:
        emb = q_embs[eq.query_text]
        is_orig = eq.query_kind == "original"
        for ev_type, limit in DEFAULT_TYPE_QUOTAS.items():
            if mode in ("dense", "sparse"):
                hits = retriever.search(mode, eq.query_text, emb, ev_type, limit)
                for rank_idx, h in enumerate(hits, start=1):
                    pl = h["payload"]
                    meta = pl.get("metadata") or {}
                    if ev_type == EvidenceType.RESEARCH_PROJECT.value and meta.get("project_category") == "administrative_or_grant":
                        continue
                    doc_id = h["document_id"]
                    raw_s = float(h["score"])
                    cand = RetrievedEvidenceItem(
                        document_id=doc_id,
                        professor_id=pl.get("professor_id"),
                        department_id=int(pl.get("department_id", 0)),
                        evidence_type=ev_type,
                        score=raw_s * eq.weight,
                        rrf_rank=rank_idx,
                        originating_query=eq.query_text,
                        query_kind=eq.query_kind,
                        query_weight=eq.weight,
                        payload=pl,
                        original_dense_score=raw_s if (mode == "dense" and is_orig) else 0.0,
                        original_sparse_score=raw_s if (mode == "sparse" and is_orig) else 0.0,
                        expanded_dense_score=raw_s if (mode == "dense" and not is_orig) else 0.0,
                        expanded_sparse_score=raw_s if (mode == "sparse" and not is_orig) else 0.0,
                        rrf_score=0.0,
                        matched_queries=[eq.query_text],
                    )
                    prev = best_by_doc.get(doc_id)
                    if prev is None or cand.score > prev.score:
                        best_by_doc[doc_id] = cand
            else:
                # Exact Hybrid RRF logic matching HybridRetrievalService.retrieve()
                dense_hits = retriever.search("dense", eq.query_text, emb, ev_type, limit)
                sparse_hits = retriever.search("sparse", eq.query_text, emb, ev_type, limit)
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
                max_rrf = 2.0 / 61.0
                for rank_idx, (doc_id, rrf_val, d_score, s_score, pl) in enumerate(fused_docs[:limit], start=1):
                    meta = pl.get("metadata") or {}
                    if ev_type == EvidenceType.RESEARCH_PROJECT.value and meta.get("project_category") == "administrative_or_grant":
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
                            original_dense_score=d_score if is_orig else 0.0,
                            original_sparse_score=s_score if is_orig else 0.0,
                            expanded_dense_score=0.0 if is_orig else d_score,
                            expanded_sparse_score=0.0 if is_orig else s_score,
                            rrf_score=norm_rrf,
                            matched_queries=[eq.query_text],
                        )
                    else:
                        if is_orig:
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

    retrieved = sorted(best_by_doc.values(), key=lambda x: x.score, reverse=True)
    t_ret = time.perf_counter() - t_ret0

    t_val0 = time.perf_counter()
    agg_svc = ProfessorAggregationService()
    rank_svc = ProfessorRankingService()
    exp_svc = MatchExplanationService()

    bundles = agg_svc.aggregate(retrieved)
    ranked = []
    rejected_by_gate = 0
    for pid, bundle in bundles.items():
        prof = profs_map.get(pid)
        if not prof or prof.verification_status == "rejected":
            continue
        score, cat, counts = rank_svc.score_bundle(bundle)
        decision = validator.validate_bundle(orig_query, bundle, retrieval_mode=mode)
        if not decision.is_valid:
            rejected_by_gate += 1
            continue
        cat = SearchService._cap_category(cat, decision.max_allowed_category)
        if cat == "insufficient":
            rejected_by_gate += 1
            continue
        ranked.append(
            exp_svc.build_explanation(
                prof=prof,
                dept=depts_map.get(prof.department_id),
                bundle=bundle,
                score=score,
                match_category=cat,
                evidence_counts=counts,
            )
        )
    ranked.sort(key=lambda r: r.score, reverse=True)
    t_val = time.perf_counter() - t_val0

    return ranked[:top_k], rejected_by_gate, t_ret, t_val


def main():
    t_start = time.perf_counter()
    queries = [json.loads(l) for l in open("data/evaluation/phase2b_queries.jsonl", "r", encoding="utf-8") if l.strip()]
    q_data = json.loads(Path("data/evaluation/phase2b_query_embeddings.json").read_text(encoding="utf-8"))
    before_data = json.loads(Path("data/evaluation/phase2b_experiment_results.json").read_text(encoding="utf-8"))

    mem_client, mem_mgr = load_full_collection_into_memory("data/qdrant_full")
    retriever = CachedQdrantRetriever(mem_mgr)

    provider = PrecomputedQueryEmbeddingProvider(q_data["embeddings"])
    q_emb_svc = QueryEmbeddingService(provider=provider)
    exp_svc = QueryExpansionService(max_expansions=5)
    validator = RelevanceValidationService()

    db = SessionLocal()
    ckpt_path = Path("evaluation/results/phase2c_eval_checkpoint.json")
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        profs_map = {p.id: p for p in db.query(Professor).all()}
        depts_map = {d.id: d for d in db.query(Department).all()}

        after_exps = {
            "A_dense_only": [],
            "B_sparse_only": [],
            "C_hybrid_original": [],
            "D_multi_query_hybrid": [],
        }
        latency_stats = {k: {"ret_s": 0.0, "val_s": 0.0} for k in after_exps}
        tier_counts = {k: Counter() for k in after_exps}

        for idx, q in enumerate(queries, start=1):
            qid = q["query_id"]
            orig_q = q["original_query"]
            exp_res = exp_svc.expand(orig_q)
            orig_only = [exp_res.queries[0]]
            multi_q = exp_res.queries

            for exp_name, mode, q_list in [
                ("A_dense_only", "dense", orig_only),
                ("B_sparse_only", "sparse", orig_only),
                ("C_hybrid_original", "hybrid", orig_only),
                ("D_multi_query_hybrid", "hybrid", multi_q),
            ]:
                ranked, rej_cnt, t_ret, t_val = run_mode_with_gate(
                    retriever, q_emb_svc, q_list, mode, orig_q, profs_map, depts_map, validator
                )
                latency_stats[exp_name]["ret_s"] += t_ret
                latency_stats[exp_name]["val_s"] += t_val
                if not ranked:
                    tier_counts[exp_name]["insufficient_queries"] += 1
                for r in ranked:
                    tier_counts[exp_name][r.match_category] += 1

                after_exps[exp_name].append({
                    "query_id": qid,
                    "original_query": orig_q,
                    "query_type": q["query_type"],
                    "rejected_by_relevance_gate": rej_cnt,
                    "results": [serialize_match(m) for m in ranked],
                })

            elapsed = time.perf_counter() - t_start
            print(
                f"[progress] {idx}/{len(queries)} ({qid}) | calls={retriever.retrieval_calls} "
                f"hits={retriever.cache_hits} | elapsed={elapsed:.1f}s",
                flush=True,
            )
            if idx % 6 == 0:
                ckpt_path.write_text(json.dumps({"completed_queries": idx, "after_exps": after_exps}), encoding="utf-8")

        after_metrics = {k: compute_system_level_metrics(v) for k, v in after_exps.items()}

        focus_comparison = {}
        for qid in ["Q15", "Q16", "Q21", "Q33", "Q34", "Q35", "Q36"]:
            b_q = next(x for x in before_data["experiments"]["D_multi_query_hybrid"] if x["query_id"] == qid)
            a_q = next(x for x in after_exps["D_multi_query_hybrid"] if x["query_id"] == qid)
            focus_comparison[qid] = {
                "query": b_q["original_query"],
                "query_type": b_q["query_type"],
                "before_count": len(b_q["results"]),
                "before_top3": [(r["professor_name"], r["department_code"], r["score"], r["match_category"]) for r in b_q["results"][:3]],
                "after_count": len(a_q["results"]),
                "after_top3": [(r["professor_name"], r["department_code"], r["score"], r["match_category"]) for r in a_q["results"][:3]],
            }

        total_elapsed = round(time.perf_counter() - t_start, 2)
        out_path = Path("evaluation/results/phase2c_before_after.json")
        out_obj = {
            "execution_summary": {
                "total_elapsed_seconds": total_elapsed,
                "retrieval_calls": retriever.retrieval_calls,
                "cache_hits": retriever.cache_hits,
                "in_memory_points_verified": mem_mgr.count_points(exact=True),
            },
            "before_system_metrics": before_data["system_level_metrics"],
            "after_system_metrics": after_metrics,
            "after_tier_counts": {k: dict(v) for k, v in tier_counts.items()},
            "latency_per_query_ms": {
                k: {
                    "retrieval_ms": round((v["ret_s"] / len(queries)) * 1000, 2),
                    "validation_ms": round((v["val_s"] / len(queries)) * 1000, 2),
                    "total_ms": round(((v["ret_s"] + v["val_s"]) / len(queries)) * 1000, 2),
                }
                for k, v in latency_stats.items()
            },
            "focus_comparison_D": focus_comparison,
        }
        out_path.write_text(json.dumps(out_obj, indent=2), encoding="utf-8")
        print(json.dumps(out_obj["execution_summary"], indent=2))
        print(json.dumps(out_obj["after_tier_counts"], indent=2))
        print(json.dumps(out_obj["focus_comparison_D"], indent=2))
    finally:
        mem_client.close()
        db.close()


if __name__ == "__main__":
    main()
