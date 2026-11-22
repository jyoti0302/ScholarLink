# Phase 2C Relevance Validation Report

## 1. Executive Summary

Phase 2C addressed false-positive recommendations caused by rank-only Reciprocal Rank Fusion (RRF) and ungrounded query expansion in the IIT Kharagpur Professor Discovery Platform. By preserving raw `BAAI/bge-m3` dense cosine and learned sparse scores alongside RRF ranks, enforcing multi-concept grounding, and checking query-expansion alignment, the platform now rejects unsupported out-of-scope queries (`Q33`, `Q34`, `Q36`) and eliminates single-token false positives (`Q21` AE combustion match) while preserving valid in-scope recommendations (`Q15`, `Q16`, `Q21` MT specialists).

All evaluation runs were executed read-only against an in-memory Qdrant copy of the `19,493` points from `data/qdrant_full` (`research_evidence_v1`), reusing precomputed embeddings from `data/evaluation/phase2b_query_embeddings.json` without modifying PostgreSQL source tables, `embedding_cache` (`16,532` records), `data/qdrant_full`, or `data/qdrant_pilot` (`3,204` points).

---

## 2. Architecture Changes

1. **Raw Signal Preservation (`backend/search/retrieval.py`)**:
   - Extended `RetrievedEvidenceItem` and `HybridRetrievalService.retrieve` to preserve `original_dense_score`, `original_sparse_score`, `expanded_dense_score`, `expanded_sparse_score`, `rrf_score`, and `matched_queries` separately from fused RRF scores.
2. **Evidence-Based Relevance Validation (`backend/search/relevance_validation.py`)**:
   - Implemented `RelevanceValidationConfig`, `ValidationDecision`, `extract_query_concept_terms`, `count_concept_overlap`, and `RelevanceValidationService`.
   - Enforces original-query dense/sparse support floors, multi-concept overlap guards for technical queries (`min_query_terms_for_concept_guard = 3`), and evidence-type corroboration (preventing `department_only` or `candidate_publication`-only recommendations).
3. **Query Expansion Drift Guard (`backend/search/query_understanding.py`)**:
   - Added `QueryExpansionService.is_expansion_aligned()` to prevent drifted sub-queries from introducing off-topic evidence.
4. **Search Pipeline Integration (`backend/search/ranking.py`)**:
   - Integrated optional `relevance_validator` and `_cap_category()` into `SearchService` without altering production ranking weights.
5. **Regression Tests (`tests/test_relevance_validation.py`)**:
   - Added 4 regression tests covering `Q15`, `Q16`, `Q21`, `Q33`, empty/department-only, candidate-publication-only, expanded-only without original support, duplicate deduplication, and expansion drift.

### Provisional Thresholds (`RelevanceValidationConfig`)
Derived from the Phase 2B raw score distribution audit (`Q15`/`Q16`/`Q21` max original dense `0.6317–0.6601`, sparse `0.1146–0.1763` vs. `Q33`–`Q36` max original dense `0.4618–0.5309`, sparse `0.0359–0.1158`):
- `min_original_dense_score = 0.54`
- `min_original_sparse_score = 0.08`
- `strong_min_original_dense_score = 0.58`
- `single_term_guard_dense_floor = 0.60`
- `min_query_terms_for_concept_guard = 3`

> **Note**: These thresholds are provisional and must be validated against manual human relevance judgments once `data/evaluation/phase2b_relevance_judgments.csv` is labeled. Precision@5, Recall@10, nDCG@10, and MRR are intentionally not reported as validated metrics yet.

---

## 3. Evaluation Results (`evaluation/results/phase2c_before_after.json`)

### Execution Summary
- **In-memory Qdrant points verified**: `19,493`
- **Total elapsed time**: `2127.26 s`
- **Retrieval calls**: `1,300` (`cache_hits: 760`)

### `D_multi_query_hybrid` System Metrics (After Validation)
- **Total queries**: `36`
- **Queries with results**: `32` (`coverage_rate = 0.8889`)
- **Total professor recommendations**: `306`
- **Mean distinct evidence types per professor**: `3.467`
- **Department-only recommendation rate**: `0.0`
- **Candidate-publication-only rate**: `0.0`
- **Evidence type distribution**:
  - `research_project`: `1,114`
  - `candidate_publication`: `497`
  - `biography`: `398`
  - `research_interest`: `297`
  - `verified_publication`: `276`

### Tier Distribution After Validation (`after_tier_counts`)

| Experiment | `strong` | `related` | `limited` | `insufficient_queries` |
| :--- | :---: | :---: | :---: | :---: |
| `A_dense_only` | 164 | 127 | 9 | 5 |
| `B_sparse_only` | 0 | 1 | 11 | 29 |
| `C_hybrid_original` | 153 | 153 | 0 | 4 |
| `D_multi_query_hybrid` | 164 | 142 | 0 | 4 |

### Per-Query Latency Breakdown (`latency_per_query_ms`)

| Experiment | `retrieval_ms` | `validation_ms` | `total_ms` |
| :--- | :---: | :---: | :---: |
| `A_dense_only` | 4854.48 | 16.98 | 4871.46 |
| `B_sparse_only` | 11225.02 | 16.29 | 11241.31 |
| `C_hybrid_original` | 3.57 | 18.57 | 22.15 |
| `D_multi_query_hybrid` | 41765.53 | 35.22 | 41800.75 |

*(Note: `C_hybrid_original` retrieval latency reflects in-memory cache hits from `A_dense_only` and `B_sparse_only`; `validation_ms` overhead remains `16.29–35.22 ms` per query across all configurations.)*

### Focus Query Before / After Summary (`D_multi_query_hybrid`)
- **Q15** (*Generative AI for healthcare applications*): `10` -> `10` professors (`Niloy Ganguly [CS] 2.9073 related`, `Aurobinda Routray [EE] 2.8214 related`, `Subhamoy Mandal [MM] 2.4925 related`).
- **Q16** (*Natural language processing for Indian languages*): `10` -> `10` professors (`Pawan Goyal [CS] 3.2055 strong`, `Dripta Piplai (Mondal) [HS] 2.8517 strong`, `Krothapalli Sreenivasa Rao [CS] 2.8488 strong`).
- **Q21** (*3D printing and laser powder bed fusion of titanium alloys*): `10` -> `10` professors (`Jyotsna Dutta Majumdar [MT] 3.114 strong`, `Sujoy Kumar Kar [MT] 2.7924 related`, `Shampa Aich [MT] 2.7125 related`). Eliminated `Ratan Joarder [AE]` (`laser` combustion false positive).
- **Q33** (*Medieval Byzantine numismatics and ecclesiastical iconography*): `10` (`related`) -> `0` (`insufficient_evidence`).
- **Q34** (*Extraterrestrial lunar regolith sintering for orbital habitat construction*): `10` (`related`) -> `0` (`insufficient_evidence`).
- **Q35** (*Macroeconomic monetary policy in post-Brexit European central banking*): `10` (`strong`/`related`) -> `2` (`Siddhartha Chattopadhyay [HS] 2.5651 related`, `Krittika Banerjee [HS] 2.1651 related`).
- **Q36** (*Ancient Mesoamerican Mayan epigraphy and calendrical astronomy*): `10` (`strong`/`related`) -> `0` (`insufficient_evidence`).

---

## 4. Remaining Limitations & Next Steps

1. **Human Relevance Labels Required**: Provisional thresholds in `RelevanceValidationConfig` need calibration/verification once `data/evaluation/phase2b_relevance_judgments.csv` is manually annotated.
2. **Partial Overlap on Broad Domain Terms (`Q35`)**: Out-of-scope query `Q35` retained 2 `HS` economists (`related`) because `"macroeconomic"` and `"monetary policy"` had learned sparse overlap (`0.1158 >= 0.08`) with IIT Kharagpur economics faculty.
3. **Sparse-Only Recall**: `B_sparse_only` yielded `insufficient_queries: 29` under the provisional `0.08` sparse floor, confirming that dense + sparse hybrid fusion (`C_hybrid_original` / `D_multi_query_hybrid`) is required for reliable recall.
