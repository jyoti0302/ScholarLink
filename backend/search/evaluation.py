"""
Phase 2B Search Quality Evaluation Metrics.

Supports:
- Graded relevance metrics (0-3 scale): Precision@5, Recall@10, nDCG@10, MRR, Hit Rate@5, Hit Rate@10
- Careful handling of queries with 0 known relevant professors or incomplete human labels
- System-level structural metrics: Coverage, Evidence Diversity, Department-Only Rate,
  Verified vs. Candidate Publication breakdown, and Duplicate-Evidence checks.
"""
import math
from typing import Any, Dict, List, Optional, Sequence


def precision_at_k(
    ranked_prof_ids: Sequence[int],
    judgments: Dict[int, int],
    k: int = 5,
    min_rel: int = 2,
) -> Optional[float]:
    """Fraction of top-k ranked professors that have relevance >= min_rel. Returns None if no judgments exist."""
    if not judgments or k <= 0:
        return None
    top = list(ranked_prof_ids)[:k]
    if not top:
        return 0.0
    hits = sum(1 for pid in top if judgments.get(pid, 0) >= min_rel)
    return hits / k


def recall_at_k(
    ranked_prof_ids: Sequence[int],
    judgments: Dict[int, int],
    k: int = 10,
    min_rel: int = 2,
) -> Optional[float]:
    """
    Fraction of known relevant professors (rel >= min_rel) retrieved in top-k.
    Returns None if there are 0 known relevant professors for the query (avoids 0/0 misleading scores).
    """
    relevant_set = {pid for pid, rel in judgments.items() if rel >= min_rel}
    if not relevant_set:
        return None
    top = set(list(ranked_prof_ids)[:k])
    return len(top & relevant_set) / len(relevant_set)


def ndcg_at_k(
    ranked_prof_ids: Sequence[int],
    judgments: Dict[int, int],
    k: int = 10,
) -> Optional[float]:
    """Graded nDCG@k using gain = (2^rel - 1) / log2(rank + 1). Returns None if ideal DCG is 0."""
    if not judgments or k <= 0:
        return None
    ideal_rels = sorted((rel for rel in judgments.values() if rel > 0), reverse=True)[:k]
    if not ideal_rels:
        return None

    def _dcg(rels: Sequence[int]) -> float:
        return sum(((2 ** r) - 1) / math.log2(idx + 2) for idx, r in enumerate(rels) if r > 0)

    idcg = _dcg(ideal_rels)
    if idcg <= 0.0:
        return None
    actual_rels = [judgments.get(pid, 0) for pid in list(ranked_prof_ids)[:k]]
    return _dcg(actual_rels) / idcg


def mean_reciprocal_rank(
    ranked_prof_ids: Sequence[int],
    judgments: Dict[int, int],
    min_rel: int = 2,
) -> Optional[float]:
    relevant_set = {pid for pid, rel in judgments.items() if rel >= min_rel}
    if not relevant_set:
        return None
    for idx, pid in enumerate(ranked_prof_ids, start=1):
        if pid in relevant_set:
            return 1.0 / idx
    return 0.0


def hit_rate_at_k(
    ranked_prof_ids: Sequence[int],
    judgments: Dict[int, int],
    k: int = 5,
    min_rel: int = 2,
) -> Optional[float]:
    relevant_set = {pid for pid, rel in judgments.items() if rel >= min_rel}
    if not relevant_set:
        return None
    top = set(list(ranked_prof_ids)[:k])
    return 1.0 if (top & relevant_set) else 0.0


def compute_system_level_metrics(query_runs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes label-free structural quality metrics across a list of query results:
    - Coverage (% queries with >= 1 non-insufficient professor result)
    - Evidence diversity (counts per evidence type across returned top-10 professors)
    - Department-context-only recommendation rate
    - Candidate-publication-only recommendation rate
    """
    total_queries = len(query_runs)
    if total_queries == 0:
        return {}

    queries_with_results = 0
    total_recs = 0
    ev_type_totals: Dict[str, int] = {}
    dept_only_recs = 0
    candidate_only_recs = 0
    avg_distinct_ev_types: List[int] = []

    for qr in query_runs:
        recs = qr.get("results") or []
        if recs:
            queries_with_results += 1
        for r in recs:
            total_recs += 1
            counts = r.get("evidence_counts") or {}
            distinct_non_dept = 0
            for et, cnt in counts.items():
                if cnt > 0:
                    ev_type_totals[et] = ev_type_totals.get(et, 0) + cnt
                    if et != "department_context":
                        distinct_non_dept += 1
            avg_distinct_ev_types.append(distinct_non_dept)

            non_zero_types = {et for et, cnt in counts.items() if cnt > 0}
            if non_zero_types and non_zero_types == {"department_context"}:
                dept_only_recs += 1
            if non_zero_types and non_zero_types.issubset({"candidate_publication", "department_context"}):
                candidate_only_recs += 1

    return {
        "total_queries": total_queries,
        "queries_with_results": queries_with_results,
        "coverage_rate": round(queries_with_results / total_queries, 4),
        "total_professor_recommendations": total_recs,
        "mean_distinct_evidence_types_per_prof": round(
            sum(avg_distinct_ev_types) / max(len(avg_distinct_ev_types), 1), 3
        ),
        "department_only_recommendation_rate": round(dept_only_recs / max(total_recs, 1), 4),
        "candidate_publication_only_rate": round(candidate_only_recs / max(total_recs, 1), 4),
        "evidence_type_distribution": ev_type_totals,
    }
