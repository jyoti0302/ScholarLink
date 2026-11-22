# ScholarLink — Answers to Everything Asked in the PDF

This document maps your **ScholarLink (IIT Kharagpur Professor Discovery & Research Application Platform)** project directly to every requirement in the PDF.

> **Important Note on Artifact 1 (Rule 1e):** The PDF explicitly states: *"Ensure this page is not created by AI."* Therefore, Section 1 below provides **factual bullet notes and structure** from your project so you can write the 300–700 word 1-page narrative in your own voice.

---

## Artifact 1: 1-Page Write-Up (~300–700 Words) — Outline & Notes to Write in Your Own Words

Use these points to draft your own 1-page document (~300–700 words):

### a. Your Take on the Problem Statement
- **Who has the problem:** Undergraduate and postgraduate students (specifically at IIT Kharagpur, like yourself and your hostel-mates/batchmates) looking for professors for BTP/MTP theses, research internships, or summer research projects.
- **Why it matters:**
  - Finding the right faculty advisor currently requires manually clicking through dozens of department pages, outdated faculty profiles, Google Scholar, and PDFs.
  - Generic keyword searches fail (for example, searching *"Transformer architecture in AI"* brings up electrical engineering power-transformer professors).
  - Once students find 5–10 relevant professors, they struggle to tailor separate resumes and outreach materials for each professor without losing track or mixing up versions.
- **Why an app is the right solution:**
  - Combining structured faculty data (profiles, biographies, projects, verified publications) with hybrid semantic search surfaces every qualifying professor ranked by actual research match—with clickable source evidence.
  - Keeping one master **My Academic Profile** and letting students select professor-specific items into isolated **My Applications** workspaces solves both discovery and tailored application prep in one workflow.
- **Assumptions vs. Verified vs. Guessed** *(fill in your own real conversations!)*:
  - **Verified:** *(Add 1–2 real observations/conversations—e.g., your own experience searching IIT KGP faculty pages, or a 10-minute chat with a hostel-mate/batchmate about how long it takes to shortlist professors and customize resumes).*
  - **Assumptions / Guesses:** *(e.g., students prefer seeing transparent evidence & unverified-publication warnings over a black-box score; students want separate versioned resumes per professor rather than one generic resume; local browser storage is sufficient for an MVP before server-side application sync).*

### b. What Is In Scope (Built in ScholarLink)
1. **Professor Discovery & Hybrid Search (IIT Kharagpur):** BGE-M3 dense + sparse hybrid retrieval in Qdrant over official IIT KGP faculty profiles, research projects, biographies, and publications; domain disambiguation (e.g., AI Transformers vs. electrical transformers); broad-domain recall; match-score sorting; pagination; cooperative Stop Search.
2. **Dedicated Professor Profile Pages:** Overview, verified Contact Information card (official email, office phone, department address/website, personal webpage, bio sketch, ORCID/IRINS/OpenAlex), biography, research interests, research projects, and verified vs. clearly labelled unverified publications.
3. **Student Authentication & Master Academic Profile:** Minimal email + password registration (`scrypt` + HS256 JWT), PostgreSQL-backed CRUD for 9 profile sections (Personal/Academic Info, Education, Technical Skills, Research Skills & Interests, Projects, Research Experience, Internships/Work, Achievements/Certifications, Publications), and a 100-point backend-computed completion tracker.
4. **My Applications & Professor-Specific Tailored Resume Generation:** Isolated per-professor workspaces, 5-state status workflow (*Not Started → In Progress → Ready to Review → Ready to Send → Sent* with explicit student approval/confirmation gates), professor-specific profile item selection, factually grounded AI tailored resume generation (Gemini 2.5 Flash + deterministic grounded fallback), split-pane editor & live preview, version management (v1, v2, duplicate, delete), and PDF/DOCX export.

### c. What Is Out of Scope (Not Built Yet)
- Automated email sending / Gmail integration (students review and send outreach themselves).
- AI cover-letter and cold-outreach email generation (tabs reserved for Stage 6.3+).
- Multi-university coverage beyond IIT Kharagpur (architecture supports multiple universities, but only IIT KGP is indexed today).
- Server-side cross-device persistence for application workspaces (currently student-scoped `localStorage`; master profile is in PostgreSQL).
- Profile photo uploads, real-time scraping on every query, or automated scholarship/funding matching.

### d. What Is Your Solution & Why
- **Solution:** ScholarLink is an end-to-end web app (React + TypeScript + Tailwind frontend, FastAPI + PostgreSQL + Qdrant + BGE-M3 backend) that connects research-grounded professor discovery with a single master student profile and professor-specific application workspaces.
- **Why this design:**
  - **Transparency over black-box AI:** Every match shows supporting evidence, distinguishes verified vs. unverified publications, and links back to official IIT KGP pages.
  - **Strict factual grounding:** Tailored resumes only use verified items selected from the student's master profile—preventing hallucinated projects, metrics, skills, or dates.
  - **No cross-professor contamination:** Each professor gets an isolated workspace and independent resume versions without ever overwriting the student's master academic profile.

---

## Artifact 2: Prompts Used to Create the Tool

Below is the chronological set of prompts you used across the build of ScholarLink:

1. **Retrieval & Domain Disambiguation (Stage 1–2):**
   - *"Fix domain disambiguation so AI queries like 'Work in Artificial Intelligence working in the field of Transformer architecture' exclude electrical power-transformer faculty, separate exact-topic and broad-domain evidence, disclose abstract availability, and preserve authorship verification."*
   - *"Stage 2 Correction: Remove the strict topic gate in `validate_bundle()` so 'Work in Artificial Intelligence working in the field of Transformer architecture' returns the union of professors with exact Transformer architecture evidence and professors with genuine broad AI/ML research."*
2. **Complete Professor Discovery, Pagination & Match-Score Sorting (Stage 3 & 3.2):**
   - *"Stage 3: Retrieve every qualifying professor available in the indexed dataset rather than only the first 10, preserve BGE-M3 hybrid retrieval and domain validation, support pagination and total result counts, and return an honest no-results response when no faculty qualify."*
   - *"Stage 3.2: Sort professors by highest research match score first and lowest last before pagination, ensuring the score used for sorting matches the Strong/Relevant match badges and is not overridden by the frontend."*
3. **Dedicated Professor Profile & Verified Contact Info (Stage 4.1–4.3 + Enhancement):**
   - *"Stage 4.1–4.3: Audit the professor database/ORM, build `GET /professors/{professor_id}/profile` returning complete faculty details, projects, and verified/candidate publications, and build the dedicated Professor Profile page with Official Website, Create Resume, and Create Cover Letter actions."*
   - *"Professor Profile Enhancement: Add a dedicated Contact Information card after the overview displaying verified public email, office telephone, address, department link, research group website, and academic links from existing PostgreSQL and cached official IIT KGP HTML records without fabricating any field."*
4. **Student Identity & Master Academic Profile (Stage 5.1–5.3):**
   - *"Stage 5.1–5.2: Audit auth, create 7 dedicated student PostgreSQL tables (`students`, `student_educations`, `student_skills`, `student_projects`, `student_experiences`, `student_achievements`, `student_publications`), additive Alembic migrations, salted `scrypt` + HS256 JWT auth (`/auth/register`, `/auth/login`, `/auth/me`), and restrict registration to email and password only."*
   - *"Stage 5.3: Build authenticated `/student/profile` CRUD APIs with ownership enforcement and a 100-point backend-computed completion formula, plus the full React My Academic Profile page across all 9 sections."*
5. **My Applications Architecture, Status Workflow & Profile Selection (Stage 6.0–6.1):**
   - *"Replace the standalone Resume Builder nav item with My Applications organized into isolated per-professor workspaces, connected to Professor Profile actions (Create Tailored Resume, Create Cover Letter, Generate Outreach Email)."*
   - *"Stage 6.0–6.1: Implement the 5-state application status workflow (Not Started, In Progress, Ready to Review, Ready to Send, Sent) with explicit approval/submission confirmation, and complete the Selected Profile Items tab loading real student profile data with independent per-professor selections."*
6. **Professor-Specific AI Tailored Resume Generation & Export (Stage 6.2):**
   - *"Stage 6.2: Implement guided professor-specific AI tailored resume generation grounded strictly in selected student profile items and professor research context (never inventing projects, skills, dates, or metrics), a split-pane editor with live preview, multi-version management, and PDF/DOCX export."*

---

## Artifact 3: Evals Used to Test Your Solution

### 1. Domain & Retrieval Quality Evals
- **7 Research-Domain End-to-End Queries** (verified manually and via `data/evaluation/phase2b_queries.jsonl` & `phase2b_relevance_judgments.csv`):
  - `"Work in Artificial Intelligence working in the field of Transformer architecture"` (must exclude electrical power-transformer professors while preserving both exact Transformer and broad AI/ML faculty).
  - `"NLP for Indian languages"`
  - `"Generative AI for healthcare"`
  - Plus 4 additional IIT KGP domain queries verifying complete recall, score-calibrated ordering (`Strong match` before `Relevant match`), pagination consistency, and honest empty-state handling for universities/filters with zero matches.
- **Authorship & Evidence Transparency Evals:**
  - Unverified/candidate publications are always separated and labelled `Unverified` with confidence scores; rejected publication links are never shown publicly.

### 2. AI Factual Grounding & Tailoring Evals (`tests/test_resume_generation.py`)
- **Professor-specific prioritization:** Same student profile tested against an NLP professor vs. a Computer Vision professor—verifies NLP/BERT/RAG project ranks #1 for the NLP professor and Drone Object Detection ranks #1 for the CV professor.
- **Anti-hallucination / grounding check:** Injects a mocked LLM response containing an unknown `source_id` (`"9999": ["HALLUCINATED PROJECT"]`) and verifies the validator strips it while preserving exact original titles, dates, and organizations.
- **Resilience to AI failures:** Verifies both upstream exceptions/timeouts and malformed non-JSON/non-dict responses fall back cleanly to the grounded relevance-ranked engine.
- **Cross-student security:** Passing foreign/non-owned record IDs (`999`, `888`, etc.) returns empty lists—Student A can never pull Student B's items.
- **PDF & DOCX export validation:** Verifies non-empty `%PDF-1.4` (`%%EOF`, clickable `/Subtype /Link` URI annotations) and valid OpenXML `.docx` ZIP packages (`word/document.xml`, `word/styles.xml`, `word/_rels/document.xml.rels`, clickable hyperlinks) across all 3 templates reflecting the student's latest edits.

### 3. Contact Information Evals (`tests/test_professor_contact.py` & `ProfessorContactCard.test.ts`)
- Verifies extraction of official office phone, personal webpage, and bio sketch PDF from IIT KGP HTML without fabricating room numbers.
- Verifies rejection of placeholder phone numbers (`0000000`) and unsafe URLs (`javascript:`).
- Tests professors with email only, multiple contact fields, and zero public contact info (`"Contact information is not publicly available."`).

### 4. Frontend Workflow, Isolation & Security Evals (`vitest` — 33/33 passing)
- **API Client & Stop Search (`client.test.ts` — 14 tests):** Empty query rejection, HTTP status mapping (`422`/`503`/`500`), timeout vs. manual `AbortController` cancellation, race-free rapid re-searching, and backend cancel notification.
- **Status Workflow & Profile Selection (`Applications.test.ts` — 12 tests):** All 5 statuses, blocking `ready_to_review`/`ready_to_send`/`sent` without documents or explicit approval/confirmation, loading all real student profile fields, checkbox toggling & live counts, `localStorage` save/restore round-trip, strict isolation between Professor A and Professor B, master profile immutability, and empty optional sections.
- **Resume Versioning & Preview (`ResumeGeneration.test.ts` — 3 tests):** Multiple versions per professor (`v1`, `v2`), duplication, editing without cross-professor mutation, safe deletion, student storage-key isolation (`student 1` vs `student 2`), and template/section visibility rendering.
- **Bundle Security Check:** Verified `frontend/dist` contains zero `GEMINI_API_KEY`, `JWT_SECRET_KEY`, or AI provider credentials.
- **Production Build Check:** `tsc -b && vite build` passes with 0 TypeScript or bundling errors.

---

## Artifact 4: Link to the App

- **App Link:** `[INSERT YOUR PUBLIC DEPLOYED URL HERE]` *(e.g., Vercel/Netlify frontend URL + Render/Railway/tunnelled FastAPI backend URL, or a hosted prototype link on Lovable/Bolt/Claude)*
- **Evaluator Access Checklist (from "Please Note"):**
  - [ ] Confirm the link opens without requiring private VPN or localhost access.
  - [ ] Provide a demo student account (or verify self-registration with email + password works smoothly on the hosted instance).
  - [ ] Confirm `GEMINI_API_KEY` (optional) and `JWT_SECRET_KEY` are configured on the hosted backend (never in frontend code).
  - [ ] Test the full flow in an incognito browser window before submitting: **Search Professor → View Professor Profile → Click Create Tailored Resume → Complete Academic Profile / Select Items → Generate, Edit, Preview & Download PDF/DOCX**.
