import pytest
from backend.search.evaluation import (
    compute_system_level_metrics,
    hit_rate_at_k,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


def test_graded_ranking_metrics_and_empty_truth_handling():
    judgments = {10: 3, 20: 2, 30: 1, 40: 0}
    ranked = [20, 40, 10, 50, 30]

    assert precision_at_k(ranked, judgments, k=5, min_rel=2) == pytest.approx(2 / 5)
    assert recall_at_k(ranked, judgments, k=10, min_rel=2) == pytest.approx(1.0)
    assert mean_reciprocal_rank(ranked, judgments, min_rel=2) == pytest.approx(1.0)
    assert hit_rate_at_k(ranked, judgments, k=5, min_rel=2) == 1.0
    ndcg = ndcg_at_k(ranked, judgments, k=10)
    assert ndcg is not None and 0.0 < ndcg < 1.0

    # Ideal ranking achieves nDCG@10 == 1.0
    assert ndcg_at_k([10, 20, 30, 40], judgments, k=10) == pytest.approx(1.0)

    # Queries with 0 known relevant professors return None rather than misleading 0/0
    no_rel = {10: 0, 20: 1}
    assert recall_at_k(ranked, no_rel, k=10, min_rel=2) is None
    assert mean_reciprocal_rank(ranked, no_rel, min_rel=2) is None
    assert hit_rate_at_k(ranked, no_rel, k=5, min_rel=2) is None


def test_system_level_metrics():
    runs = [
        {
            "query_id": "Q1",
            "results": [
                {"professor_id": 1, "evidence_counts": {"research_interest": 1, "research_project": 2}},
                {"professor_id": 2, "evidence_counts": {"candidate_publication": 1}},
            ],
        },
        {"query_id": "Q2", "results": []},
    ]
    m = compute_system_level_metrics(runs)
    assert m["total_queries"] == 2
    assert m["queries_with_results"] == 1
    assert m["coverage_rate"] == 0.5
    assert m["department_only_recommendation_rate"] == 0.0
    assert m["candidate_publication_only_rate"] == 0.5
