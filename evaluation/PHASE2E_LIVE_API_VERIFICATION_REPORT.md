# Phase 2E.2 — Live Search API Verification Report

**Verification Date:** 2026-11-18  
**Target:** `backend.api.main:app` (`POST /search` and existing CRUD endpoints)  
**Overall Status:** **BLOCKED / FAILED ON LIVE BGE-M3 ENCODING** (split Python environment: `FlagEmbedding` is not installed in the Python 3.10 API environment, and `fastapi` is not installed in `C:\GPU_Environment`).

---

## 1. Environment & Dependency Findings

1. **Main Project Python 3.10 (`C:\Users\jyoti\AppData\Local\Programs\Python\Python310\python.exe`)**:
   - FastAPI `lifespan` initialized cleanly (`lifespan_search_service_ready: true`, `lifespan_search_init_error: null`).
   - PostgreSQL and `data/qdrant_full` (`research_evidence_v1`) connected cleanly.
   - `BGEM3FlagEmbeddingProvider` uses lazy model loading (`_ensure_loaded()`), so startup succeeded, but the first `POST /search` request failed with `ModuleNotFoundError: No module named 'FlagEmbedding'`.
2. **GPU Environment (`C:\GPU_Environment\python.exe`)**:
   - Verified `torch: 2.14.1+cu126`, `cuda: True`, and `FlagEmbedding` (`C:\GPU_Environment\Lib\site-packages\FlagEmbedding\__init__.py`) are installed.
   - Importing `fastapi.testclient.TestClient` failed immediately with `ModuleNotFoundError: No module named 'fastapi'`.

---

## 2. Data Integrity Verification (Read-Only)

Verified directly during the live `TestClient(app)` session:
- PostgreSQL `search_documents`: **`19,493`**
- PostgreSQL `embedding_cache`: **`16,532`**
- PostgreSQL `professors`: **`877`**
- PostgreSQL `departments`: **`65`**
- Qdrant `data/qdrant_full` (`research_evidence_v1`): **`19,493`** points

*(No database records, embeddings, or Qdrant collections were modified.)*

---

## 3. Existing CRUD Endpoint Verification

All 6 tested CRUD/health endpoints returned `200 OK`:

| Endpoint | HTTP Status | Latency (`ms`) |
| :--- | :---: | :---: |
| `GET /` | `200` | `10.15` |
| `GET /universities` | `200` | `110.38` |
| `GET /universities/1/departments` | `200` | `44.22` |
| `GET /professors?page=1&page_size=2` | `200` | `47.33` |
| `GET /professors/1` | `200` | `41.07` |
| `GET /professors/1/publications` | `200` | `50.24` |

---

## 4. Live `POST /search` Request Results

Executed against `backend.api.main:app` in Python 3.10 with `limit: 10`:

| Query ID | Query | HTTP Status | Latency (`ms`) | Error / Response Body |
| :--- | :--- | :---: | :---: | :--- |
| **Q15** | `Generative AI for healthcare` | `500` | `79.87` | `{"detail":"An unexpected error occurred while executing search."}` (`ModuleNotFoundError: No module named 'FlagEmbedding'`) |
| **Q16** | `NLP for Indian languages` | `500` | `14.28` | `{"detail":"An unexpected error occurred while executing search."}` (`ModuleNotFoundError: No module named 'FlagEmbedding'`) |
| **Q21** | `Laser powder bed fusion` | `500` | `15.04` | `{"detail":"An unexpected error occurred while executing search."}` (`ModuleNotFoundError: No module named 'FlagEmbedding'`) |
| **Q33** | `Medieval Byzantine numismatics and ecclesiastical iconography` | `500` | `15.64` | `{"detail":"An unexpected error occurred while executing search."}` (`ModuleNotFoundError: No module named 'FlagEmbedding'`) |
| **Q35** | `Macroeconomic monetary policy in post-Brexit European central banking` | `500` | `15.86` | `{"detail":"An unexpected error occurred while executing search."}` (`ModuleNotFoundError: No module named 'FlagEmbedding'`) |

Because `FlagEmbedding` could not be imported in Python 3.10, `POST /search` safely returned structured HTTP `500` responses without leaking internal tracebacks to the client, and could not execute live query embedding, Qdrant retrieval, relevance validation (`Q33`), or ranking.

---

## 5. Remediation Required Before Re-Verification

Unify the runtime environment so one Python interpreter has both the FastAPI/SQLAlchemy/Qdrant stack **and** `torch` + `FlagEmbedding`:
- **Option A (Recommended for GPU inference):** Install the API dependencies (`fastapi`, `uvicorn`, `sqlalchemy`, `psycopg2-binary`, `qdrant-client`, `pydantic`, `python-dotenv`, `httpx`) into `C:\GPU_Environment\python.exe` and launch Uvicorn from `C:\GPU_Environment\python.exe`.
- **Option B:** Install `FlagEmbedding` (and `torch`) into the main Python 3.10 environment.

Once unified, re-run the 5 live `POST /search` checks (`Q15`, `Q16`, `Q21`, `Q33`, `Q35`) to confirm `200 OK`, professor details, match categories, evidence, explanations, `Q33` `insufficient_evidence`, and live BGE-M3 latency.
