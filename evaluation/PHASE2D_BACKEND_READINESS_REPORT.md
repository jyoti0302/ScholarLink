# Phase 2D — Backend Readiness Audit Report

**Audit Date:** 2026-11-17  
**Scope:** Read-only audit of `backend/api/` and `backend/search/` prior to frontend development.  
**Result:** **NO-GO for immediate UI integration** (Phase 2 search pipeline is verified in `backend/search/`, but is **not yet exposed** in `backend/api/main.py`).

---

## 1. API Integration Findings

### Current State of `backend/api/main.py`
`backend/api/main.py` currently serves only **Phase 1** data-foundation endpoints (`GET /` reports `"phase": 1`):
- `GET /` (health check)
- `GET /universities`
- `GET /universities/{university_id}/departments`
- `GET /departments/{department_id}/professors`
- `GET /professors`
- `GET /professors/{professor_id}`
- `GET /professors/{professor_id}/publications`
- `GET /publications/{publication_id}`
- `GET /admin/review/faculty`, `GET /admin/review/professors/{professor_id}/publications`, `GET /admin/review/publications`

### Production API vs. Evaluation Runner Gap
| Pipeline Component | `backend/search/` (`SearchService`) | `backend/api/main.py` (FastAPI) | Status |
| :--- | :--- | :--- | :--- |
| `QueryUnderstandingService` | Invoked via `QueryExpansionService` | Not wired | Missing in API |
| `QueryExpansionService` | Invoked in `SearchService.search()` | Not wired | Missing in API |
| BGE-M3 Query Embedding | Invoked via `QueryEmbeddingService` | Not wired | Missing in API |
| Qdrant Hybrid Retrieval | Invoked via `HybridRetrievalService` | Not wired | Missing in API |
| `ProfessorAggregationService` | Invoked in `SearchService.search()` | Not wired | Missing in API |
| `ProfessorRankingService` | Invoked in `SearchService.search()` | Not wired | Missing in API |
| `RelevanceValidationService` | Invoked when `relevance_validator` is passed | Not wired | Missing in API |
| `MatchExplanationService` | Invoked in `SearchService.search()` | Not wired | Missing in API |

Both `GET /search?q=machine+learning` and `POST /search` on `backend.api.main:app` currently return **`404 {"detail": "Not Found"}`**.

### Response Field Gaps in `SearchService`
`SearchService.search()` and `RankedProfessorMatch` (`backend/search/ranking.py`) already return `query`, `expansion`, `status`, `message`, `professor_id`, `professor_name`, `department_code`, `department_name`, `profile_url`, `score`, `match_category`, `evidence_counts`, `matched_topics`, `matched_queries`, `supporting_evidence`, and `explanation`. However, the following UI-required fields are not yet included in the search response object:
- Top-level: `request_id`, `search_latency_ms`
- Per-professor: `designation`, `email`, `research_interests` (available on the `Professor` ORM model)
- Per-evidence item: `evidence_id` / `document_id` (available on `RetrievedEvidenceItem`, omitted in `MatchExplanationService.build_explanation`)

---

## 2. Actual Endpoint & `SearchService` Test Results

### FastAPI `TestClient(app)` Results
- `GET /`: `200` (`{'status': 'online', 'platform': 'AI-Powered Professor Discovery Platform', 'phase': 1, 'institution': 'Indian Institute of Technology Kharagpur'}`)
- `GET /universities`: `200` (`1` university)
- `GET /universities/1/departments`: `200` (`65` departments)
- `GET /professors?page=1&page_size=2`: `200` (`2` professors)
- `GET /professors/1`: `200`
- `GET /professors/1/publications`: `200`
- `GET /search?q=machine+learning`: `404 {"detail": "Not Found"}`
- `POST /search`: `404 {"detail": "Not Found"}`

### `SearchService` End-to-End Results (`data/qdrant_full` + PostgreSQL + `RelevanceValidationService`)
Executed read-only using precomputed BGE-M3 query embeddings (`data/evaluation/phase2b_query_embeddings.json`):

| Query | Status | Count | Latency (`ms`) | Top Results |
| :--- | :--- | :---: | :---: | :--- |
| **Q15**: *Generative AI for healthcare applications* | `ok` | `10` | `30082.86` | 1. `Niloy Ganguly [CS]` (`id=20`, `2.9207`, `related`)<br>2. `Aurobinda Routray [EE]` (`id=5`, `2.8205`, `related`)<br>3. `Subhamoy Mandal [MM]` (`id=845`, `2.4941`, `related`) |
| **Q16**: *Natural language processing for Indian languages* | `ok` | `10` | `24216.52` | 1. `Pawan Goyal [CS]` (`id=272`, `3.2064`, `strong`)<br>2. `Dripta Piplai (Mondal) [HS]` (`id=433`, `2.8517`, `strong`)<br>3. `Krothapalli Sreenivasa Rao [CS]` (`id=268`, `2.8488`, `strong`) |
| **Q21**: *3D printing and laser powder bed fusion of titanium alloys* | `ok` | `10` | `21380.42` | 1. `Jyotsna Dutta Majumdar [MT]` (`id=585`, `3.1186`, `strong`)<br>2. `Sujoy Kumar Kar [MT]` (`id=599`, `2.7922`, `related`)<br>3. `Shampa Aich [MT]` (`id=594`, `2.7125`, `related`) |
| **Q33**: *Medieval Byzantine numismatics and ecclesiastical iconography* | `insufficient_evidence` | `0` | `5363.52` | *(none — out-of-scope rejected)* |
| **Q35**: *Macroeconomic monetary policy in post-Brexit European central banking* | `ok` | `2` | `16136.75` | 1. `Siddhartha Chattopadhyay [HS]` (`id=454`, `2.5666`, `related`)<br>2. `Krittika Banerjee [HS]` (`id=442`, `2.1651`, `related`) |

- `Q21` eliminated the single-term laser-combustion false positive (`Ratan Joarder [AE]`), surfacing Materials (`MT`) specialists in all top-3 positions.
- `Q33` cleanly returned `insufficient_evidence` with `0` results.
- `Q35` returned `2` `HS` economics professors (`related`) due to macroeconomics/monetary policy overlap (`sparse >= 0.08`).

---

## 3. Error Handling Verification

| Case | Layer Tested | Observed Behavior | Readiness Note |
| :--- | :--- | :--- | :--- |
| Invalid query params (`page=0`, `status=bogus`) | FastAPI (`backend/api/main.py`) | `422 Unprocessable Entity` | Ready |
| Missing resource (`/professors/999999`) | FastAPI (`backend/api/main.py`) | `404 {"detail": "Professor not found"}` | Ready |
| Restricted publication status (`status=rejected`) | FastAPI (`backend/api/main.py`) | `403 Forbidden` | Ready |
| Missing `profile_url` | PostgreSQL + FastAPI | `0` professors have `profile_url IS NULL`; schema allows `Optional[str] = None` | Ready |
| Empty (`""`) / whitespace (`"   "`) query | `SearchService` | Returns `status="insufficient_evidence"`, `count=0` | Should return `422` at FastAPI boundary before embedding |
| No matching evidence (`Q33`) | `SearchService` | Returns `status="insufficient_evidence"`, `count=0` | Ready |
| Query expansion LLM failure | `QueryExpansionService` | Falls back automatically to rule-based + original query (`5` queries) | Ready |
| Qdrant unavailable (missing collection) | `HybridRetrievalService` | Raises `ValueError: Collection research_evidence_v1 not found` | Needs FastAPI `503` handler |
| PostgreSQL unavailable | `SearchService` | Raises `sqlalchemy.exc.OperationalError` | Needs FastAPI `503` handler |

---

## 4. Data Integrity Checks (Read-Only)

All production stores remain intact and unmodified:
- PostgreSQL `search_documents`: **`19,493`**
- PostgreSQL `embedding_cache`: **`16,532`**
- PostgreSQL `professors`: **`877`**
- PostgreSQL `departments`: **`65`**
- Qdrant full collection (`data/qdrant_full`, `research_evidence_v1`): **`19,493`** points
- Qdrant pilot collection (`data/qdrant_pilot`, `research_evidence_v1`): **`3,204`** points

---

## 5. Missing Functionality & Recommended Frontend API Contract

### Missing Functionality to Add Before UI Launch
1. **Wire `/search` (`POST /search`) in `backend/api/main.py`**: Initialize `FlagEmbeddingBGEM3Provider`, `QdrantClient(path="data/qdrant_full")`, `QueryExpansionService`, `HybridRetrievalService`, `RelevanceValidationService`, and `SearchService` once in FastAPI `lifespan` (read-only Qdrant + single-instance model warm-up).
2. **Enrich Search Response Schema (`backend/api/schemas.py`)**: Add `request_id`, `search_latency_ms`, `designation`, `email`, `research_interests`, and `supporting_evidence[].evidence_id`.
3. **API Boundary Validation & Resilience**: Reject empty/whitespace `query` with `422`; map Qdrant/DB connection errors to structured `503 Service Unavailable`.
4. **Latency Note**: Local file-based Qdrant hybrid retrieval across 5 evidence types × 4–6 expanded queries took `16.1–30.1 s` per query in `SearchService` (`Q15`, `Q16`, `Q21`, `Q35`). Consider capping default `use_expansion` sub-queries or running Qdrant in server mode if sub-second UI latency is required.

### Recommended Frontend API Contract

1. **Research Search — `POST /search`**
   - **Request**:
     ```json
     {
       "query": "Natural language processing for Indian languages",
       "top_k": 10,
       "use_expansion": true,
       "department_ids": null,
       "include_candidate_publications": true
     }
     ```
   - **Response** (`200 OK`):
     ```json
     {
       "request_id": "req_01J...",
       "query": "Natural language processing for Indian languages",
       "expanded_queries": [
         "Natural language processing for Indian languages",
         "Natural Language Processing applications in Indian Languages"
       ],
       "status": "ok",
       "message": null,
       "search_latency_ms": 2421.6,
       "results": [
         {
           "professor_id": 272,
           "professor_name": "Pawan Goyal",
           "department_code": "CS",
           "department_name": "Computer Science and Engineering",
           "designation": "Associate Professor",
           "profile_url": "https://www.iitkgp.ac.in/department/CS/faculty/cs-pawang",
           "email": "pawang@cse.iitkgp.ac.in",
           "score": 3.2064,
           "match_category": "strong",
           "explanation": "Strong match supported by: ...",
           "research_interests": "...",
           "evidence_counts": { "research_interest": 1, "verified_publication": 3 },
           "supporting_evidence": [
             {
               "evidence_id": "doc_...",
               "evidence_type": "research_interest",
               "title": "...",
               "snippet": "...",
               "source_url": "https://www.iitkgp.ac.in/department/CS/faculty/cs-pawang",
               "verification_status": "verified",
               "score": 0.6317
             }
           ]
         }
       ]
     }
     ```
2. **Professor Detail — `GET /professors/{professor_id}`** (already implemented; returns `ProfessorDetailSchema` with `id`, `name`, `designation`, `email`, `biography`, `research_interests`, `profile_url`, `topics`, and publication counts).
3. **Professor Publications & Evidence — `GET /professors/{professor_id}/publications?status=verified`** (already implemented; defaults to `verified`, allows `pending` / `needs_review`, blocks `rejected` with `403`).
4. **University & Department Metadata — `GET /universities`, `GET /universities/{university_id}/departments`, `GET /departments/{department_id}/professors`** (already implemented).

---

## 6. Final Recommendation: **NO-GO (Until `/search` Endpoint Is Wired)**

- **Backend Search Core (`backend/search/`)**: **Ready** (validated end-to-end on `19,493` Qdrant points and `877` professors).
- **FastAPI Layer (`backend/api/main.py`)**: **Not Ready for UI search** because `/search` does not exist yet and `SearchService` is not wired into FastAPI.
- **Next Action**: Add `POST /search` (plus `request_id`, `search_latency_ms`, `designation`, `email`, `research_interests`, `evidence_id`, `422` blank-query guard, and `503` backend-unavailable handling) to `backend/api/`, verify with `TestClient`, and then flip to **GO** for frontend development.
