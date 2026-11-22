# Phase 2F.0 — Comprehensive Retrieval Quality & Professor–Evidence Attribution Audit (Read-Only)

**Audit Date:** 2026-11-21  
**Scope:** Read-only audit of PostgreSQL (`877` professors, `65` departments, `19,493` `search_documents`), `data/qdrant_full` (`19,493` points), `data_collection/faculty_scraper.py`, `backend/search/`, and 7 live queries (`F1`–`F7`).  
**Constraints:** Zero modifications made to PostgreSQL, Qdrant, embeddings, or source code.

---

## 1. Current Retrieval Architecture

`SearchService.search()` ([ranking.py](file:///C:/Users/jyoti/OneDrive/MTP_2/backend/search/ranking.py)) executes a single-path pipeline:
1. `QueryUnderstandingService` + `QueryExpansionService` ([query_understanding.py](file:///C:/Users/jyoti/OneDrive/MTP_2/backend/search/query_understanding.py)) generate the original query + up to `5` taxonomy/rule-based expansions.
2. `QueryEmbeddingService` + `BGEM3FlagEmbeddingProvider` ([embedding.py](file:///C:/Users/jyoti/OneDrive/MTP_2/backend/search/embedding.py)) encode query texts into `1024-d` dense + learned sparse vectors.
3. `HybridRetrievalService.retrieve()` ([retrieval.py](file:///C:/Users/jyoti/OneDrive/MTP_2/backend/search/retrieval.py)) queries Qdrant across **5** evidence types (`verified_publication`, `research_interest`, `research_project`, `biography`, `candidate_publication`) using dense + sparse RRF (`k=60`).
4. `ProfessorAggregationService` deduplicates by `content_hash` / verified-vs-candidate publication ID and groups evidence by `professor_id`.
5. `ProfessorRankingService` + `RelevanceValidationService` ([relevance_validation.py](file:///C:/Users/jyoti/OneDrive/MTP_2/backend/search/relevance_validation.py)) score bundles and cap/reject weak matches.
6. `MatchExplanationService` builds grounded explanations and `supporting_evidence` lists.

---

## 2. Evidence Hierarchy Assessment

PostgreSQL `search_documents` (`19,493` rows) and `professors` (`877` rows) reveal a severe evidence imbalance:

| Evidence Type | `verified` | `pending` | `needs_review` | Total Docs | Professors Covered |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `verified_publication` | `84` | `0` | `0` | `84` | `13 / 877` (`1.5%`) |
| `candidate_publication` | `0` | `3,910` | `438` | `4,348` | `638` pending / `131` needs_review |
| `research_interest` | `798` | `2` | `17` | `817` | `790 / 877` (`90.1%`) |
| `research_project` | `12,435` | `224` | `142` | `12,801` | `789 / 877` (`90.0%`) |
| `biography` | `1,348` | `4` | `26` | `1,378` | `735 / 877` (`83.8%`) |
| `department_context` | `65` | `0` | `0` | `65` | `65 / 65` departments (**unused in retrieval**) |

- **35 of 877 professors** have **zero individual evidence** (`not has_publications and not has_research_interests and not has_biography and not has_projects`), including AI faculty such as `Anindita Maiti [AI]` and `Dipanjyoti Paul [AI]`.
- Because only `13` professors have `verified_publication` rows (`84` docs), those `13` professors receive a massive ranking boost (`weight=1.00` + multi-doc diminishing returns + diversity bonus) even when their verified papers are tangential to the query (e.g., `Hari V Warrior [NA]` #1 on Computer Vision `F5`).

---

## 3. Database Attribution Findings (Confirmed Bug)

**Confirmed Bug — Project `source_url` Attribution Leak (`5,041` links across `566` professors and `3,025` projects):**
- **Tables/Columns:** `research_projects.source_url`, `professor_projects (professor_id, project_id, role)`, `professors.profile_url`.
- **Expected:** Each professor's `search_documents` entry for a project should link to that professor's own profile URL (or project-specific source), and generic project titles should not merge unrelated professors.
- **Actual:** `5,041` `professor_projects` links have `research_projects.source_url <> professors.profile_url` (pointing to another faculty member's `/faculty/` URL).
- **Concrete Examples Verified in PostgreSQL:**
  - `Saptarshi Ghosh` (`id=277`, `cs-saptarshi`):
    - `proj_id=3470` (*Enhancing Confidence in Closed-LLM Answers for Indian Tax Law*) -> `source_url=https://www.iitkgp.ac.in/department/CS/faculty/cs-pawang` (legitimate collaboration with Pawan Goyal, wrong `source_url`).
    - `proj_id=329` (*Responsible AI for Decentralized Online Platforms*) -> `source_url=.../cs-niloy`.
  - `Shyamal Kumar Das Mandal` (`id=698`, `at-sdasmandal`):
    - `proj_id=6958` (*FIST- PROJECT (Level-2)*) -> `source_url=.../at-kkntnu` (generic title collision).
    - `proj_id=5429` (*AI Integration and Upskilling for Kendriya Vidyalaya Teachers...*) -> `source_url=.../me-director`.
- **Important Distinction:** Across all `7` live queries (`F1`–`F7`), `pg_bad = 0` — every `document_id` in Qdrant maps to the **correct `professor_id`** in `search_documents`. The mismatch is in **`source_url`** (not `professor_id`), caused by shared `ResearchProject` rows plus generic-title collisions.

---

## 4. Scraping & Ingestion Issues

- **File/Function:** `data_collection/faculty_scraper.py` (lines `595–643`).
- **Root Cause:** `project_key_cache` deduplicates `ResearchProject` globally by `normalize_project_key(title)` across all professors. Only the **first** scraped professor sets `proj.source_url = parsed.get("profile_url")`. Subsequent collaborators (and unrelated professors sharing generic titles like `"FIST- PROJECT (Level-2)"`) are attached via `ProfessorProject` without per-link `source_url`.
- **Secondary Scraping Issue:** Typo `"Natural Language Pocessing"` (missing `'r'`) appears in `professors.research_interests` for `Pawan Goyal`, `Sudeshna Sarkar`, `Jiaul Hoque Paik` (hurts exact lexical/concept matching on `"Natural Language Processing"`), and `Priyadarshi Patnaik [HS]` (`id=448`) has `profile_url` / `source_url` pointing to `hs-bapi`.
- **Severity:** **High** (undermines user trust when clicking a professor's evidence link opens another professor's page).

---

## 5. Search-Document & Qdrant Payload Issues

- **File/Function:** `backend/search/document_builder.py` (line `383`).
- **Root Cause:** Line `383` sets `"source_url": proj.source_url or prof_source_url`, propagating the first-scraped professor's `profile_url` into every co-investigator's `SearchDocument` and Qdrant payload.
- **Additional Observation:** `document_builder.py` attaches the professor's **profile-level** `canonical_topics` / `topic_domains` / `topic_areas` (`lines 369–371`) to every `research_project`, and sets `verification_status = prof.verification_status` (`verified`) on all project docs — even generic/merged ones.
- **Recommended Fix:** Prefer `prof_source_url` whenever `proj.source_url` is a `/faculty/` URL belonging to a different professor (or store `source_url` on `ProfessorProject`).

---

## 6. Retrieval & Aggregation Problems

1. **`department_context` Ignored (`backend/search/retrieval.py` lines `19–25`)**: `DEFAULT_TYPE_QUOTAS` includes only the 5 individual evidence types and omits `department_context`, so the `65` department documents are never retrieved.
2. **Verified-Publication Dominance (`backend/search/ranking.py`)**: Because only `13` professors have `verified_publication` rows, any topic-adjacent verified paper (e.g., `Hari V Warrior [NA]` on `F5`, `Niloy Ganguly [CS]` on `F2`) outranks domain specialists who have `research_interest` + `candidate_publication` + `research_project` evidence.
3. **Strong vs. Related Calibration**: Professors with `research_interest` + `verified_publication` can be capped to `related` (`F2` #1, `F5` #1) while a professor with only `research_project` + `candidate_publication` (`Q21` `Santanu Dhara`) can receive `strong`.

---

## 7. Query Understanding & Expansion Limitations

- **File/Function:** `backend/search/query_understanding.py` (`QueryExpansionService`).
- **Confirmed Issues:**
  1. **Broad Domain-Appended Expansions Cause Cross-Department Drift:** In `F6` (*Mineral processing*), expansion appends `"mineral processing and Geology, Geophysics & Architecture"`, pulling 5 `GG` professors into `#2`–`#6` ahead of `MI` mineral processing faculty (`Biswajit Samanta`, `Subhendu Mishra`).
  2. **No Department-Relevance Mapping:** `QueryUnderstandingService` does not identify target academic disciplines/departments for Path B fallback.
  3. **No Distinction Between Exact Topic Match vs. Adjacent Field:** All expanded subqueries (`weight=0.7–0.85`) feed the same RRF pool without separating primary-discipline hits from adjacent-discipline hits.

---

## 8. Department Relevance Modelling Proposal (Path B)

- **Represent departments semantically using existing PostgreSQL + Qdrant `department_context` documents** (enriched with department name, academic unit, curated research-area summaries, and faculty research-topic aggregations — **no hardcoded keyword-to-department tables**).
- **Two-Path Execution:**
  - **Path A (Individual Evidence):** Existing dense + sparse retrieval across `verified_publication`, `research_interest`, `research_project`, `biography`, `candidate_publication`.
  - **Path B (Department Discovery Fallback / Parallel):** Query `department_context` (and optionally LLM/taxonomy discipline mapping) to identify top `k` relevant departments (`AI`, `CS`, `EC`, `MI`, `CE`, etc.), then surface professors from those departments who lack sufficient individual evidence **only in a separate `department_contact` section/tier**, capped (e.g., top 2–3 per relevant department, prioritizing faculty with `research_interests` or `biography` over completely blank profiles).

---

## 9. Live Search Audit Results (`F1`–`F7`)

Executed read-only against `data/qdrant_full` (`19,493` pts) + PostgreSQL + `BAAI/bge-m3`:

| Query | Status / Count / Latency | Top-3 & Attribution Check | False Positives & Missed Candidates |
| :--- | :--- | :--- | :--- |
| **F1**: *NLP for Indian languages* | `ok` / `10` / `192.97 s` (cold) | 1. `Pawan Goyal [CS]` (`strong`)<br>2. `Sudeshna Sarkar [CS]` (`related`, `url_mm=2`)<br>3. `Krothapalli Sreenivasa Rao [CS]` (`related`) | `url_mm` on `Sudeshna Sarkar`, `Saptarshi Ghosh` (`cs-pawang`), `Priyadarshi Patnaik [HS]` (`hs-bapi`, `cs-ppchak`), `Shyamal Kumar Das Mandal [AT]` (`cs-ksrao`, `ai-plaban`). **Missed in top-10:** `AI` NLP faculty (`Jiaul Hoque Paik [AI]`, `Plaban Kumar Bhowmick [AI]`, `Amlan Chakrabarti [AI]`, `Koustav Rudra [AI]`). |
| **F2**: *Natural Language Processing* | `ok` / `10` / `110.69 s` | 1. `Niloy Ganguly [CS]` (`related`, `3.9109`, `15` verified pubs)<br>2. `Pawan Goyal [CS]` (`strong`, `3.2452`)<br>3. `Krothapalli Sreenivasa Rao [CS]` (`related`, `3.0549`) | `Niloy Ganguly` outranks `Pawan Goyal` due to `15` verified pubs; `Goutam Saha [EC]` (`#4`, speech/biomedical) outranks `Animesh Mukherjee [CS]` (`#5`). `url_mm` on `Animesh Mukherjee`, `Sudeshna Sarkar`, `Sourangshu Bhattacharya`. **Missed:** `Amlan Chakrabarti [AI]`, `Koustav Rudra [AI]`. |
| **F3**: *Speech recognition for Indian languages* | `ok` / `10` / `62.34 s` | 1. `Krothapalli Sreenivasa Rao [CS]` (`strong`)<br>2. `Sudeshna Sarkar [CS]` (`strong`, `url_mm=2`)<br>3. `Dripta Piplai (Mondal) [HS]` (`strong`, `url_mm=2`) | Good recall (`Goutam Saha [EC]` `#4`, `Shyamal Kumar Das Mandal [AT]` `#5`, `Aurobinda Routray [EE]` `#8` with speech paper). `url_mm` on `Sudeshna Sarkar`, `Dripta Piplai`, `Shyamal Kumar Das Mandal`, `Pabitra Mitra`, `Pawan Goyal`. |
| **F4**: *Machine learning for healthcare* | `ok` / `10` / `94.20 s` | 1. `Pabitra Mitra [CS]` (`strong`)<br>2. `Anirban Mukherjee [EE]` (`strong`, `url_mm=1`)<br>3. `Subhamoy Mandal [MM]` (`strong`, `url_mm=2`) | `Aurobinda Routray [EE]` (`#4`) surfaced via `verified_publication` on speech foundation models; `url_mm` on `Anirban Mukherjee`, `Subhamoy Mandal`, `Debashree Guha Adhya`, `Sudipta Mukhopadhyay`. **Missed in top-10:** `Mahesh Mohan M R [AI]` (`AI and ML in healthcare`), `Koustav Rudra [AI]` is `#6`. |
| **F5**: *Computer vision for autonomous systems* | `ok` / `10` / `99.77 s` | 1. **`Hari V Warrior [NA]`** (`related`, `3.4154`, `6` verified pubs)<br>2. **`Aurobinda Routray [EE]`** (`related`, `2.8929`, `8` verified pubs)<br>3. `Debashis Sen [EC]` (`strong`) | **Major False Positives:** `#1 Hari V Warrior [NA]` (Hydrodynamics) and `#2 Aurobinda Routray [EE]` (Arc Fault Detector) boosted by `verified_publication` imbalance. **Missed in top-10:** `Amlan Chakrabarti [AI]`, `Shreya Ghosh [AI]`, `Somdyuti Paul [AI]`, `Soumen Basu [AI]`, `Abir Das [CS]`, `Jayanta Mukhopadhyay [CS]`. |
| **F6**: *Mineral processing* | `ok` / `10` / `35.97 s` | 1. `Arun Kumar Majumder [MI]` (`strong`)<br>2. `Dewashish Upadhyay [GG]` (`related`, `url_mm=1`)<br>3. `Manish Atmaprakash Mamtani [GG]` (`related`, `url_mm=1`) | **Domain Drift:** 5 `GG` geology faculty ranked `#2`–`#6` ahead of `Biswajit Samanta [MI]` (`#7`), `Subhendu Mishra [MI]` (`#8`), `Chenna Rao Borra [MT]` (`#9`). `Debashish Chakravarty [MI]` (`#10`) has `url_mm=3`. |
| **F7**: *Geotechnical engineering* | `ok` / `9` / `38.74 s` | 1. `Debasis Roy [CE]` (`strong`)<br>2. `Shashi Prakash Sharma [GG]` (`related`)<br>3. `Paramita Bhattacharya [CE]` (`strong`) | Strong `CE` + `MI` coverage (`Debasis Roy`, `Paramita Bhattacharya`, `Debasis Deb`, `Troyee Tanu Dutta`, `Debarghya Chakraborty`, `Dilip Kumar Baidya`, `Sankhaneel Sinha`). `url_mm=0` across all 9 results. **Missed:** `Abhiram Kumar Verma [MI]`, `Islavath Sreenivasa Rao [MI]`, `Kousik Deb [CE]`. |

---

## 10. Recommended Ranking & Match-Category Architecture

1. **`direct_research_match` (Direct Research Match):** Supported by `verified_publication` (on-topic) or strong explicit `research_interest` + corroborated `research_project`/`biography` with high original-query dense/sparse support.
2. **`related_research_match` (Related Research Match):** Supported by relevant `research_interest`, `biography`, interdisciplinary `research_project`, or `candidate_publication` (explicitly labeled unverified).
3. **`department_relevant_contact` (Department-Relevant Academic Contact):** Returned **separately** via Path B (`department_context` semantic match) when individual evidence is insufficient/absent; explicitly labeled as department proximity, never merged into Path A ranks.
4. **`insufficient_evidence`:** Rejected / omitted.
5. **Rebalance Verified vs. Candidate/Interest Scoring:** Cap per-professor `verified_publication` dominance when the verified paper itself does not meet the query's semantic/concept threshold (fixing `F5` #1/#2).

---

## 11. Performance Optimization Opportunities

- **Qdrant Server Mode (`http://127.0.0.1:6333`)**: Already migrated (`19,493` pts) and ready to wire (`QDRANT_URL`), expected to cut warm retrieval from `22–80 s` down to `< 2–4 s`.
- **Qdrant `query_batch_points`**: Batch the 5 per-type dense + sparse queries per expanded query into fewer round-trips while preserving exact raw dense/sparse scores.
- **Startup Model Warmup & Bounded Query Cache**: Warm `BGEM3FlagEmbeddingProvider` in FastAPI lifespan; cache normalized query results in memory.

---

## 12. Proposed Phase 2F.1 Implementation Sequence (Awaiting Approval)

1. **Step 1 — Fix Project `source_url` Attribution & Typo Normalization:**
   - Update `document_builder.py` (`line 383`) to use `prof_source_url` when `proj.source_url` is another professor's `/faculty/` URL (and fix `data_collection/faculty_scraper.py` for future scrapes so `ProfessorProject` or per-prof `source_url` is preserved, plus guard generic titles like `"FIST- PROJECT (Level-2)"`).
   - Normalize `"Pocessing"` -> `"Processing"` at query/indexing time without altering DB records unnecessarily.
2. **Step 2 — Fix Topic-Relevance Gating on `verified_publication` (`F5` / `F2`):**
   - Require individual `verified_publication` items contributing to ranking to pass a minimum query-similarity/concept check so off-topic verified papers cannot propel `Hari V Warrior [NA]` or `Aurobinda Routray [EE]` to `#1`/`#2` on Computer Vision.
3. **Step 3 — Implement Path B Department-Relevant Academic Discovery:**
   - Enable `department_context` retrieval in `HybridRetrievalService` / `SearchService` as a separate `department_contacts` section (`department_relevant_contact` category) for queries with sparse/no individual coverage or cross-departmental discovery.
4. **Step 4 — Switch FastAPI to Qdrant Server (`QDRANT_URL`) & Verify:**
   - Start PostgreSQL + Qdrant server (`127.0.0.1:6333`), run full pytest suite sequentially, and re-benchmark `F1`–`F7` + `Q15`, `Q16`, `Q21`, `Q33`, `Q35`.

*Report saved to [PHASE2F0_RETRIEVAL_ATTRIBUTION_AUDIT_REPORT.md](file:///C:/Users/jyoti/OneDrive/MTP_2/evaluation/PHASE2F0_RETRIEVAL_ATTRIBUTION_AUDIT_REPORT.md). No code, database records, embeddings, or Qdrant collections were modified.*
