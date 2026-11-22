# Phase 3.1 — Frontend & Prototype Readiness Audit (Read-Only)

**Audit Date:** 2026-11-21  
**Scope:** Read-only audit of existing frontend assets, FastAPI backend (`backend/api/main.py`, `backend/api/schemas.py`), `POST /search` integration, and readiness for the 5-screen student prototype.

---

## 1. Current Frontend Architecture

**No frontend exists yet.** Inspecting the workspace root confirms only backend, data pipeline, evaluation, and test directories (`backend/`, `data/`, `data_collection/`, `data_processing/`, `scripts/`, `tests/`, `tools/`, `evaluation/`, `docs/`). There is no `frontend/`, `package.json`, routing, styling framework, state management, auth, or file-upload UI in the repository.

- **Local Toolchain Available:** Node.js `v22.22.2` is installed on the host, so a new React + Vite + TypeScript + Tailwind CSS application can be scaffolded in `frontend/` without affecting the Python backend.

---

## 2. Current Backend API Inventory

All endpoints below are verified in [main.py](file:///C:/Users/jyoti/OneDrive/MTP_2/backend/api/main.py) and [schemas.py](file:///C:/Users/jyoti/OneDrive/MTP_2/backend/api/schemas.py):

| HTTP | Endpoint | Request / Params | Response Structure | Status | Usable Directly? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/` | None | `{status, platform, phase, institution}` | Implemented | Yes |
| `POST` | `/search` | `SearchRequestSchema` (`query`, `limit` 1–50, `use_expansion`, `department_ids`, `include_candidate_publications`) | `SearchResponseSchema` (`request_id`, `query`, `expanded_queries`, `status`, `message`, `search_latency_ms`, `total_results`, `results[]`) | Implemented | Yes |
| `GET` | `/universities` | Optional `country` | `List[UniversitySchema]` | Implemented | Yes |
| `GET` | `/universities/{university_id}/departments` | `university_id: int` | `List[DepartmentSchema]` (`id`, `name`, `code`, `academic_unit`, `official_url`) | Implemented | Yes |
| `GET` | `/departments/{department_id}/professors` | `department_id: int`, optional `status`, `has_publications` | `List[ProfessorBriefSchema]` | Implemented | Yes |
| `GET` | `/professors` | Optional `department_id`, `status`, `has_publications`, `search`, `page`, `page_size` | `List[ProfessorBriefSchema]` | Implemented | Yes |
| `GET` | `/professors/{professor_id}` | `professor_id: int` | `ProfessorDetailSchema` (`biography`, `research_interests`, `research_group`, `designation`, `email`, `profile_url`, `topics[]`, pub counts) | Implemented | Yes |
| `GET` | `/professors/{professor_id}/publications` | `professor_id: int`, `status` (`verified` default; `pending`, `needs_review` allowed; `rejected` -> `403`) | `List[ProfessorPublicationSchema]` | Implemented | Yes |
| `GET` | `/publications/{publication_id}` | `publication_id: int` | `PublicationDetailSchema` | Implemented | Yes |
| `GET` | `/admin/review/*` | Admin review filters | Faculty / publication review lists | Implemented | Admin only |

---

## 3. Existing vs. Missing Functionality

| Prototype Feature (Screens 1–5) | Backend Status | Gap / Note |
| :--- | :--- | :--- |
| **Screen 1 — Landing / Search** | Ready (`POST /search`) | Frontend UI needed |
| **Screen 2 — Search Results** | Ready (`POST /search` returns name, dept, designation, email, profile_url, interests, score, match_category, explanation, supporting_evidence) | Frontend UI needed; only top 3 items per evidence type are included in `supporting_evidence` |
| **Screen 3 — Professor Profile** | Mostly ready (`GET /professors/{id}`, `GET /professors/{id}/publications`) | **Missing:** `GET /professors/{id}/projects` endpoint (`ProfessorDetailSchema` only returns `has_projects: bool`, not the project list). Also only `13/877` professors have `verified` publications, so UI should optionally display `pending`/`needs_review` publications with explicit unverified disclosure. |
| **Screen 4 — Generate Email** | **Missing** | No email-generation endpoint exists. Can be implemented cleanly in frontend (grounded template using professor evidence + student profile, editable & copyable) or via optional backend endpoint. |
| **Screen 5 — Student Profile & Resume** | **Missing** | No student profile table, auth, or file-upload endpoint exists. Prototype can persist Student Profile in browser `localStorage` (+ optional stateless resume-text parser later). |

---

## 4. `POST /search` Integration Details

- **Request:** `{"query": "...", "limit": 10, "use_expansion": true, "department_ids": null, "include_candidate_publications": true}`
- **Validation & Errors:** Empty/whitespace `query` and out-of-range `limit` (`<1` or `>50`) return `422`; DB or Qdrant unavailability returns `503`; unexpected errors return safe `500`.
- **Result Representation:** Each `SearchProfessorResultSchema` item includes `professor_id`, `professor_name`, `department`, `department_code`, `department_name`, `designation`, `email`, `profile_url`, `score`, `match_category` (`strong`, `related`, `limited`), `research_interests`, `evidence_counts`, `matched_topics`, `matched_queries`, `supporting_evidence[]` (`evidence_id`, `evidence_type`, `title`, `snippet`, `source_url`, `verification_status`, `score`, `authorship_note`), and `explanation`.
- **Empty & Loading States:** When `status === "insufficient_evidence"` or `total_results === 0`, UI should display `message` cleanly and suggest broadening the query. Loading state must tolerate `20–80 s` in local Qdrant mode (or `~2–5 s` once Qdrant server `127.0.0.1:6333` is running).

---

## 5. Recommended Prototype Architecture

- **Frontend Stack:** `frontend/` built with **React 18 + Vite + TypeScript + Tailwind CSS + React Router** (clean academic design: slate/navy palette, crisp serif/sans typography, clear evidence badges distinguishing `Verified` vs. `Candidate — Unverified`).
- **API Communication:**
  - Base URL via `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`).
  - Existing CORS in [main.py](file:///C:/Users/jyoti/OneDrive/MTP_2/backend/api/main.py#L109-L115) already allows `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`.
  - Thin `src/api/client.ts` wrapper with `AbortController` timeout handling (`>= 120 s` for search) and typed error mapping (`422`, `503`, `500`).
- **State Management:** React Context / `localStorage` for `StudentProfile` (name, university, department, skills, interests, projects, optional uploaded `.txt`/`.md` resume summary) and last search results, avoiding unnecessary Redux/backend auth complexity.

---

## 6. Proposed Page & Component Structure (`frontend/src/`)

- `pages/LandingSearchPage.tsx` (Screen 1: title, description, search bar, clickable example queries)
- `pages/SearchResultsPage.tsx` (Screen 2: filterable results, `ProfessorCard`, evidence snippets, match explanation, `View Profile` & `Draft Email` actions, loading/empty/error states)
- `pages/ProfessorProfilePage.tsx` (Screen 3: profile header, biography, research interests, publications tab with verified/candidate filter, projects section, official profile link)
- `pages/EmailDraftPage.tsx` (Screen 4: selected professor + evidence context, student profile summary, editable subject & body, copy-to-clipboard & `mailto:` link)
- `pages/StudentProfilePage.tsx` (Screen 5: student details, skills, interests, projects, resume text/file import stored in `localStorage`)
- `components/`: `Navbar.tsx`, `SearchBar.tsx`, `ProfessorCard.tsx`, `EvidenceBadge.tsx`, `LoadingSkeleton.tsx`, `EmptyState.tsx`
- `api/client.ts` & `types/api.ts`

---

## 7. Implementation Roadmap

1. **Phase 3.2 — Frontend Scaffold, Landing Page & Search Interface:** Initialize `frontend/` (Vite + React + TS + Tailwind), typed API client, `LandingSearchPage`, and navigation shell.
2. **Phase 3.3 — Search Results & Professor Profile:** Build `SearchResultsPage`, `ProfessorCard`, `ProfessorProfilePage` (+ optional read-only `GET /professors/{id}/projects` backend endpoint if approved).
3. **Phase 3.4 — Student Profile & Resume Handling:** Build `StudentProfilePage` with `localStorage` persistence and client-side `.txt`/`.md` (or optional PDF) resume parsing.
4. **Phase 3.5 — Personalized Email Generation:** Build `EmailDraftPage` generating grounded, editable outreach emails referencing the professor's actual matched papers/projects and the student's profile.
5. **Phase 3.6 — End-to-End Integration & UI Testing:** Verify full student journey against live FastAPI (`C:\GPU_Environment\python.exe` + PostgreSQL + Qdrant server) and add frontend component/smoke tests.

---

## 8. Exact Files Likely to Be Created/Modified in Phase 3.2

- `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/tailwind.config.js`
- `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`
- `frontend/src/types/api.ts`, `frontend/src/api/client.ts`
- `frontend/src/components/Navbar.tsx`, `frontend/src/components/SearchBar.tsx`
- `frontend/src/pages/LandingSearchPage.tsx`
- *(No backend files modified in Phase 3.2.)*

---

## 9. Technical Risks & Dependencies

1. **Runtime Environment & Latency:** Live `POST /search` requires `C:\GPU_Environment\python.exe` (`FlagEmbedding` + CUDA). Running Qdrant server (`http://127.0.0.1:6333`, `QDRANT_URL`) is strongly recommended during UI testing so search takes seconds instead of `22–80 s`.
2. **Professor Projects on Profile Page:** Without a `GET /professors/{id}/projects` endpoint, Screen 3 can only show projects returned in `POST /search` `supporting_evidence` (max 3), not a professor's full project list.
3. **Pre-rebuild Project `source_url`s:** Until a separate `DocumentBuilder` + Qdrant payload sync is approved, some existing `research_project` cards in Qdrant still carry a collaborator's `/faculty/` URL.
4. **Email Generation Mode:** Template-based email drafting works offline with zero hallucination risk; LLM-based drafting would require an API key and backend endpoint.

---

## 10. Decisions Requiring Approval Before Phase 3.2

1. **Frontend stack:** Approve scaffolding `frontend/` with **React + Vite + TypeScript + Tailwind CSS**.
2. **Professor projects endpoint (for Phase 3.3):** Approve adding a read-only `GET /professors/{professor_id}/projects` endpoint, or restrict Screen 3 to existing endpoints (`GET /professors/{id}` + `supporting_evidence`).
3. **Email & Student Profile scope (for Phases 3.4–3.5):** Approve `localStorage`-backed Student Profile + grounded template email generation (with optional LLM enhancement later).

*No code, database records, embeddings, or Qdrant collections were modified. Ready to start Phase 3.2 upon your approval.*
