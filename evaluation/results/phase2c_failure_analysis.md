# Phase 2C Failure Analysis: False Positives & Relevance Validation

## 1. Root Causes Identified

1. **Rank-Based RRF Masks Low Raw Similarity**:
   Reciprocal Rank Fusion ($\text{RRF}(d) = \sum 1 / (60 + \text{rank})$) depends solely on document rank within the top-$k$ list, discarding raw cosine similarity (`original_dense_score`) and lexical inner-product (`original_sparse_score`). Consequently, even when no document in the corpus is semantically relevant to an out-of-scope query, Qdrant always returns top-$k$ nearest neighbors, and RRF assigns positive scores that promoted unrelated professors into `strong` or `related` tiers.

2. **Single-Term Lexical / Broad-Term False Positives**:
   Multi-word technical queries can match documents via a single shared token (e.g., `"laser"` in combustion diagnostics matching `"laser powder bed fusion"`), without matching the broader query concepts (`"3d"`, `"printing"`, `"powder"`, `"bed"`, `"fusion"`, `"titanium"`, `"alloys"`).

3. **Unaligned Query Expansion Drift**:
   Without drift checks and original-query grounding, expanded sub-queries could pull in tangential evidence that lacked direct support from the original user query.

4. **Missing Evidence-Type & Support Floor Enforcement**:
   `department_only` or `candidate_publication`-only hits without primary corroborated research evidence (`research_project`, `research_interest`, `biography`, `verified_publication`) needed explicit gating.

---

## 2. Safeguards Implemented (`backend/search/relevance_validation.py`)

Provisional thresholds in `RelevanceValidationConfig` (derived from the Phase 2B raw score audit and subject to human-label validation):
- `min_original_dense_score = 0.54`
- `min_original_sparse_score = 0.08`
- `strong_min_original_dense_score = 0.58`
- `single_term_guard_dense_floor = 0.60`
- `min_query_terms_for_concept_guard = 3`

Additionally:
- `HybridRetrievalService.retrieve` in `backend/search/retrieval.py` preserves `original_dense_score`, `original_sparse_score`, `expanded_dense_score`, `expanded_sparse_score`, `rrf_score`, and `matched_queries`.
- `QueryExpansionService.is_expansion_aligned()` in `backend/search/query_understanding.py` filters drifted expansions.
- `SearchService` in `backend/search/ranking.py` applies `RelevanceValidationService` and `_cap_category()`.

---

## 3. Before / After Focus Query Comparison (`D_multi_query_hybrid`)

### Positive In-Scope Queries

| Query | Before (`count` / Top-3) | After (`count` / Top-3) | Observation |
| :--- | :--- | :--- | :--- |
| **Q15**: *Generative AI for healthcare applications* (`application`) | `10`<br>1. Niloy Ganguly [CS] `1.3111` (`strong`)<br>2. Goutam Saha [EC] `1.1948` (`strong`)<br>3. Nirmalya Ghosh [EE] `1.125` (`related`) | `10`<br>1. Niloy Ganguly [CS] `2.9073` (`related`)<br>2. Aurobinda Routray [EE] `2.8214` (`related`)<br>3. Subhamoy Mandal [MM] `2.4925` (`related`) | Full `10` recommendations preserved; category calibrated to `related` based on raw support. |
| **Q16**: *Natural language processing for Indian languages* (`application`) | `10`<br>1. Pawan Goyal [CS] `2.4751` (`strong`)<br>2. Sudeshna Sarkar [CS] `1.5158` (`strong`)<br>3. Krothapalli Sreenivasa Rao [CS] `1.4885` (`strong`) | `10`<br>1. Pawan Goyal [CS] `3.2055` (`strong`)<br>2. Dripta Piplai (Mondal) [HS] `2.8517` (`strong`)<br>3. Krothapalli Sreenivasa Rao [CS] `2.8488` (`strong`) | Full `10` recommendations preserved with `strong` tier intact; HS linguistics match surfaced at #2. |
| **Q21**: *3D printing and laser powder bed fusion of titanium alloys* (`synonym`) | `10`<br>1. Sujoy Kumar Kar [MT] `1.4221` (`strong`)<br>2. Jyotsna Dutta Majumdar [MT] `1.0428` (`related`)<br>3. Ratan Joarder [AE] `0.9469` (`related`) | `10`<br>1. Jyotsna Dutta Majumdar [MT] `3.114` (`strong`)<br>2. Sujoy Kumar Kar [MT] `2.7924` (`related`)<br>3. Shampa Aich [MT] `2.7125` (`related`) | Single-term false positive **Ratan Joarder [AE]** (`laser` combustion) eliminated from top-3; Materials (`MT`) specialists occupy all top-3 slots. |

### Out-of-Scope Queries

| Query | Max Original Raw Score (Dense / Sparse) | Before (`count` / Top-3) | After (`count` / Top-3) | Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **Q33**: *Medieval Byzantine numismatics and ecclesiastical iconography* | `0.4900` / `0.0359` | `10`<br>1. Debapratim Pandit [AR] `0.7459` (`related`)<br>2. Hari V Warrior [NA] `0.6659` (`related`)<br>3. Niloy Ganguly [CS] `0.57` (`related`) | `0` (`insufficient_evidence`) | All false positives rejected. |
| **Q34**: *Extraterrestrial lunar regolith sintering for orbital habitat construction* | `0.5309` / `0.0638` | `10`<br>1. Sujoy Kanti Ghosh [GG] `0.8788` (`related`)<br>2. Arnab Roy [AE] `0.8541` (`related`)<br>3. Tapas Laha [MT] `0.7847` (`related`) | `0` (`insufficient_evidence`) | All false positives rejected. |
| **Q35**: *Macroeconomic monetary policy in post-Brexit European central banking* | `0.5164` / `0.1158` | `10`<br>1. Gourishankar S Hiremath [HS] `1.4678` (`strong`)<br>2. Krittika Banerjee [HS] `1.2292` (`strong`)<br>3. Siddhartha Chattopadhyay [HS] `0.9722` (`related`) | `2`<br>1. Siddhartha Chattopadhyay [HS] `2.5651` (`related`)<br>2. Krittika Banerjee [HS] `2.1651` (`related`) | Reduced from `10` (`strong`) to `2` (`related`) economists in HS due to macroeconomics/monetary policy overlap (`sparse=0.1158 >= 0.08`). |
| **Q36**: *Ancient Mesoamerican Mayan epigraphy and calendrical astronomy* | `0.4618` / `0.0607` | `10`<br>1. Mahesh K [KS] `1.5042` (`strong`)<br>2. Hari V Warrior [NA] `0.7183` (`related`)<br>3. Chandranath Chatterjee [AG] `0.6224` (`related`) | `0` (`insufficient_evidence`) | All false positives (including `strong` `Mahesh K [KS]`) rejected. |
