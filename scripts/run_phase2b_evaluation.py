"""
Phase 2B Search Quality Evaluation Runner & Scorer.

Usage:
  1. Run Experiments A (Dense-only), B (Sparse-only), C (Hybrid original-only),
     D (Multi-query Hybrid + Ranking), and E (Expansion Ablation) against `data/qdrant_full`,
     exporting results and the pooled human-relevance judgment CSV:
     python scripts/run_phase2b_evaluation.py run

  2. After human relevance labels (0-3) are filled in `data/evaluation/phase2b_relevance_judgments.csv`,
     compute Precision@5, Recall@10, nDCG@10, MRR, and Hit Rate@5/10:
     python scripts/run_phase2b_evaluation.py score
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from qdrant_client import QdrantClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database.connection import SessionLocal
from backend.database.models import Department, EvidenceType, Professor
from backend.search.embedding import DEFAULT_TARGET_DIM, DEFAULT_TARGET_MODEL, EmbeddingOutput, EmbeddingProvider
from backend.search.evaluation import (
    compute_system_level_metrics,
    hit_rate_at_k,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from backend.search.qdrant_index import QdrantIndexManager
from backend.search.query_understanding import ExpandedQuery, QueryExpansionService
from backend.search.ranking import (
    MatchExplanationService,
    ProfessorAggregationService,
    ProfessorRankingService,
    RankedProfessorMatch,
)
from backend.search.retrieval import DEFAULT_TYPE_QUOTAS, QueryEmbeddingService, RetrievedEvidenceItem


class PrecomputedQueryEmbeddingProvider(EmbeddingProvider):
    """Serves exact BGE-M3 dense + sparse vectors encoded for Phase 2B queries."""

    def __init__(self, embeddings_map: Dict[str, Dict[str, Any]]):
        self._map = embeddings_map

    @property
    def model_name(self) -> str:
        return DEFAULT_TARGET_MODEL

    @property
    def vector_dim(self) -> int:
        return DEFAULT_TARGET_DIM

    def encode(self, texts: Sequence[str]) -> List[EmbeddingOutput]:
        out: List[EmbeddingOutput] = []
        for t in texts:
            rec = self._map.get(t)
            if rec is None:
                raise KeyError(f"Query text not found in precomputed BGE-M3 query embeddings: {t!r}")
            out.append(
                EmbeddingOutput(
                    dense=rec["dense"],
                    sparse_indices=rec["sparse_indices"],
                    sparse_values=rec["sparse_values"],
                )
            )
        return out


def retrieve_with_mode(
    q_mgr: QdrantIndexManager,
    q_emb_svc: QueryEmbeddingService,
    queries: Sequence[ExpandedQuery],
    mode: str,  # "dense" | "sparse" | "hybrid"
    type_quotas: Dict[str, int] = DEFAULT_TYPE_QUOTAS,
) -> List[RetrievedEvidenceItem]:
    q_embs = q_emb_svc.embed_queries(queries)
    best_by_doc: Dict[str, RetrievedEvidenceItem] = {}

    for eq in queries:
        emb = q_embs[eq.query_text]
        for ev_type, limit in type_quotas.items():
            if mode == "dense":
                hits = q_mgr.dense_search(emb, evidence_types=[ev_type], limit=limit)
            elif mode == "sparse":
                hits = q_mgr.sparse_search(emb, evidence_types=[ev_type], limit=limit)
            elif mode == "hybrid":
                hits = q_mgr.hybrid_search(emb, evidence_types=[ev_type], limit=limit)
            else:
                raise ValueError(f"Unknown retrieval mode: {mode}")

            for rank_idx, h in enumerate(hits, start=1):
                pl = h["payload"]
                meta = pl.get("metadata") or {}
                if (
                    ev_type == EvidenceType.RESEARCH_PROJECT.value
                    and meta.get("project_category") == "administrative_or_grant"
                ):
                    continue
                doc_id = h["document_id"]
                cand = RetrievedEvidenceItem(
                    document_id=doc_id,
                    professor_id=pl.get("professor_id"),
                    department_id=int(pl.get("department_id", 0)),
                    evidence_type=ev_type,
                    score=float(h["score"]) * eq.weight,
                    rrf_rank=rank_idx,
                    originating_query=eq.query_text,
                    query_kind=eq.query_kind,
                    query_weight=eq.weight,
                    payload=pl,
                )
                prev = best_by_doc.get(doc_id)
                if prev is None or cand.score > prev.score:
                    best_by_doc[doc_id] = cand

    res = list(best_by_doc.values())
    res.sort(key=lambda x: x.score, reverse=True)
    return res


def aggregate_and_rank(
    db,
    retrieved: List[RetrievedEvidenceItem],
    profs_map: Dict[int, Professor],
    depts_map: Dict[int, Department],
    top_k: int = 10,
) -> List[RankedProfessorMatch]:
    agg_svc = ProfessorAggregationService()
    rank_svc = ProfessorRankingService()
    exp_svc = MatchExplanationService()

    bundles = agg_svc.aggregate(retrieved)
    ranked: List[RankedProfessorMatch] = []
    for pid, bundle in bundles.items():
        prof = profs_map.get(pid)
        if not prof or prof.verification_status == "rejected":
            continue
        score, cat, counts = rank_svc.score_bundle(bundle)
        if cat == "insufficient":
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
    return ranked[:top_k]


def serialize_match(m: RankedProfessorMatch) -> Dict[str, Any]:
    return {
        "professor_id": m.professor_id,
        "professor_name": m.professor_name,
        "department_code": m.department_code,
        "department_name": m.department_name,
        "score": m.score,
        "match_category": m.match_category,
        "evidence_counts": m.evidence_counts,
        "matched_topics": m.matched_topics,
        "matched_queries": m.matched_queries,
        "explanation": m.explanation,
        "supporting_evidence": m.supporting_evidence,
    }


def run_experiments() -> None:
    queries = [
        json.loads(l)
        for l in open("data/evaluation/phase2b_queries.jsonl", "r", encoding="utf-8")
        if l.strip()
    ]
    q_data = json.loads(Path("data/evaluation/phase2b_query_embeddings.json").read_text(encoding="utf-8"))
    provider = PrecomputedQueryEmbeddingProvider(q_data["embeddings"])
    q_emb_svc = QueryEmbeddingService(provider=provider)
    exp_svc = QueryExpansionService(max_expansions=5)

    q_client = QdrantClient(path="data/qdrant_full")
    q_mgr = QdrantIndexManager(client=q_client, vector_dim=DEFAULT_TARGET_DIM)

    db = SessionLocal()
    try:
        profs_map = {p.id: p for p in db.query(Professor).all()}
        depts_map = {d.id: d for d in db.query(Department).all()}

        experiments = {
            "A_dense_only": [],
            "B_sparse_only": [],
            "C_hybrid_original": [],
            "D_multi_query_hybrid": [],
        }

        # Pool candidates across A, B, C, D for human relevance judgment CSV
        pooled_rows: List[Dict[str, Any]] = []

        for q in queries:
            qid = q["query_id"]
            orig_q = q["original_query"]
            exp_res = exp_svc.expand(orig_q)
            orig_only = [exp_res.queries[0]]
            multi_q = exp_res.queries

            per_exp_ranked: Dict[str, List[RankedProfessorMatch]] = {}
            for exp_name, mode, q_list in [
                ("A_dense_only", "dense", orig_only),
                ("B_sparse_only", "sparse", orig_only),
                ("C_hybrid_original", "hybrid", orig_only),
                ("D_multi_query_hybrid", "hybrid", multi_q),
            ]:
                retrieved = retrieve_with_mode(q_mgr, q_emb_svc, q_list, mode=mode)
                ranked = aggregate_and_rank(db, retrieved, profs_map, depts_map, top_k=10)
                per_exp_ranked[exp_name] = ranked
                experiments[exp_name].append({
                    "query_id": qid,
                    "original_query": orig_q,
                    "query_type": q["query_type"],
                    "expanded_queries": [x.query_text for x in q_list],
                    "results": [serialize_match(m) for m in ranked],
                })

            # Build deduplicated pooled candidates across top-10 of A, B, C, D
            pool_by_pid: Dict[int, Dict[str, Any]] = {}
            for exp_name, ranked in per_exp_ranked.items():
                for rank_pos, m in enumerate(ranked, start=1):
                    entry = pool_by_pid.get(m.professor_id)
                    if entry is None:
                        snippets = []
                        urls = []
                        for ev in m.supporting_evidence[:3]:
                            label = (
                                f"[{ev['evidence_type']}|{ev['verification_status']}] "
                                f"{ev.get('title') or ''}: {(ev.get('snippet') or '')[:140]}"
                            )
                            snippets.append(label)
                            if ev.get("source_url"):
                                urls.append(ev["source_url"])
                        entry = {
                            "query_id": qid,
                            "original_query": orig_q,
                            "query_type": q["query_type"],
                            "professor_id": m.professor_id,
                            "professor_name": m.professor_name,
                            "department_code": m.department_code,
                            "retrieved_by_methods": [f"{exp_name}@{rank_pos}"],
                            "match_category_D": m.match_category if exp_name == "D_multi_query_hybrid" else "",
                            "verified_pub_count": m.evidence_counts.get("verified_publication", 0),
                            "candidate_pub_count_unverified": m.evidence_counts.get("candidate_publication", 0),
                            "interest_count": m.evidence_counts.get("research_interest", 0),
                            "project_count": m.evidence_counts.get("research_project", 0),
                            "bio_count": m.evidence_counts.get("biography", 0),
                            "evidence_snippets": " || ".join(snippets),
                            "source_urls": " | ".join(dict.fromkeys(urls)),
                            "relevance_score": "",  # To be filled by human judge (0, 1, 2, 3)
                            "judged_by": "",
                            "judgment_notes": "",
                        }
                        pool_by_pid[m.professor_id] = entry
                    else:
                        entry["retrieved_by_methods"].append(f"{exp_name}@{rank_pos}")
                        if exp_name == "D_multi_query_hybrid":
                            entry["match_category_D"] = m.match_category

            for entry in pool_by_pid.values():
                entry["retrieved_by_methods"] = ", ".join(entry["retrieved_by_methods"])
                pooled_rows.append(entry)

        # Compute system-level metrics for A, B, C, D and ablation C vs D
        system_metrics = {k: compute_system_level_metrics(v) for k, v in experiments.items()}

        # Compute overlap & novelty between C (original hybrid) and D (multi-query hybrid)
        c_only_profs = 0
        d_only_profs = 0
        both_profs = 0
        for c_q, d_q in zip(experiments["C_hybrid_original"], experiments["D_multi_query_hybrid"]):
            c_set = {r["professor_id"] for r in c_q["results"]}
            d_set = {r["professor_id"] for r in d_q["results"]}
            c_only_profs += len(c_set - d_set)
            d_only_profs += len(d_set - c_set)
            both_profs += len(c_set & d_set)

        out_json = {
            "parameters": {
                "qdrant_path": "data/qdrant_full",
                "collection_name": q_mgr.collection_name,
                "exact_points": q_mgr.count_points(exact=True),
                "embedding_model": DEFAULT_TARGET_MODEL,
                "type_quotas": DEFAULT_TYPE_QUOTAS,
                "top_k_professors": 10,
            },
            "system_level_metrics": system_metrics,
            "ablation_E_C_vs_D_top10_overlap": {
                "shared_professors": both_profs,
                "C_original_only_professors": c_only_profs,
                "D_multi_query_newly_surfaced_professors": d_only_profs,
            },
            "experiments": experiments,
        }
        Path("data/evaluation/phase2b_experiment_results.json").write_text(
            json.dumps(out_json, indent=2), encoding="utf-8"
        )

        # Write human-readable pooled relevance judgment CSV
        csv_path = Path("data/evaluation/phase2b_relevance_judgments.csv")
        fieldnames = [
            "query_id",
            "original_query",
            "query_type",
            "professor_id",
            "professor_name",
            "department_code",
            "retrieved_by_methods",
            "match_category_D",
            "verified_pub_count",
            "candidate_pub_count_unverified",
            "interest_count",
            "project_count",
            "bio_count",
            "evidence_snippets",
            "source_urls",
            "relevance_score",
            "judged_by",
            "judgment_notes",
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            writer = csv.DictWriter(cf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(pooled_rows)

        print(
            json.dumps(
                {
                    "queries_evaluated": len(queries),
                    "pooled_candidate_rows_for_judgment": len(pooled_rows),
                    "system_level_metrics": system_metrics,
                    "ablation_E_C_vs_D_top10_overlap": out_json["ablation_E_C_vs_D_top10_overlap"],
                },
                indent=2,
            )
        )
    finally:
        q_client.close()
        db.close()


def score_judgments() -> None:
    csv_path = Path("data/evaluation/phase2b_relevance_judgments.csv")
    exp_path = Path("data/evaluation/phase2b_experiment_results.json")
    exp_data = json.loads(exp_path.read_text(encoding="utf-8"))

    judgments_by_qid: Dict[str, Dict[int, int]] = {}
    labeled_rows = 0
    with open(csv_path, "r", encoding="utf-8") as cf:
        for row in csv.DictReader(cf):
            raw_rel = (row.get("relevance_score") or "").strip()
            if raw_rel in {"0", "1", "2", "3"}:
                judgments_by_qid.setdefault(row["query_id"], {})[int(row["professor_id"])] = int(raw_rel)
                labeled_rows += 1

    if labeled_rows == 0:
        print(
            json.dumps(
                {
                    "status": "no_human_labels_yet",
                    "message": "No relevance_score (0-3) entries found in data/evaluation/phase2b_relevance_judgments.csv.",
                },
                indent=2,
            )
        )
        return

    summary: Dict[str, Any] = {}
    for exp_name, q_runs in exp_data["experiments"].items():
        p5_vals, r10_vals, ndcg10_vals, mrr_vals, hr5_vals, hr10_vals = [], [], [], [], [], []
        for qr in q_runs:
            j = judgments_by_qid.get(qr["query_id"])
            if not j:
                continue
            ranked_ids = [r["professor_id"] for r in qr["results"]]
            p5 = precision_at_k(ranked_ids, j, k=5, min_rel=2)
            r10 = recall_at_k(ranked_ids, j, k=10, min_rel=2)
            nd10 = ndcg_at_k(ranked_ids, j, k=10)
            mrr = mean_reciprocal_rank(ranked_ids, j, min_rel=2)
            hr5 = hit_rate_at_k(ranked_ids, j, k=5, min_rel=2)
            hr10 = hit_rate_at_k(ranked_ids, j, k=10, min_rel=2)
            if p5 is not None:
                p5_vals.append(p5)
            if r10 is not None:
                r10_vals.append(r10)
            if nd10 is not None:
                ndcg10_vals.append(nd10)
            if mrr is not None:
                mrr_vals.append(mrr)
            if hr5 is not None:
                hr5_vals.append(hr5)
            if hr10 is not None:
                hr10_vals.append(hr10)

        def _mean(xs):
            return round(sum(xs) / len(xs), 4) if xs else None

        summary[exp_name] = {
            "judged_queries": len(p5_vals),
            "queries_with_relevant_professors": len(r10_vals),
            "precision_at_5": _mean(p5_vals),
            "recall_at_10": _mean(r10_vals),
            "ndcg_at_10": _mean(ndcg10_vals),
            "mrr": _mean(mrr_vals),
            "hit_rate_at_5": _mean(hr5_vals),
            "hit_rate_at_10": _mean(hr10_vals),
        }

    print(json.dumps({"labeled_rows": labeled_rows, "metrics": summary}, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Phase 2B evaluation runner and scorer")
    parser.add_argument("cmd", choices=["run", "score"])
    args = parser.parse_args()
    if args.cmd == "run":
        run_experiments()
    else:
        score_judgments()


if __name__ == "__main__":
    main()
