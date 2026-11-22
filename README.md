# AI-Powered Academic Professor Discovery Platform (Phase 1: IIT Kharagpur)

An institutional academic research database and discovery engine for academic units, faculty members, research projects, research publications, and multi-factor author disambiguation, focused on the **Indian Institute of Technology Kharagpur (IIT Kharagpur), India**.

This repository provides the complete Phase 1 data foundation for a larger AI-powered platform that helps students discover research professors based on geographical preferences and research interests, inspect their research contributions, and eventually generate personalized research applications.

---

## Architecture & System Design

```
professor-discovery/
│
├── backend/
│   ├── database/
│   │   ├── models.py              # Normalized SQLAlchemy models (12 tables)
│   │   ├── connection.py          # Engine, SessionLocal, and DB dependencies
│   │   └── migrations/            # Alembic database migrations (head: 00284571430e)
│   ├── api/
│   │   ├── main.py                # FastAPI application and route endpoints
│   │   └── schemas.py             # Pydantic response validation schemas
│   └── services/
│       └── reporting_service.py   # JSON & CSV coverage report generator
│
├── data_collection/
│   ├── department_scraper.py      # Scraper for all 65 academic units and divisions
│   ├── faculty_scraper.py         # Official directory AJAX & profile page scraper
│   ├── openalex_client.py         # OpenAlex API client (Institution ID: I145894827)
│   ├── crossref_client.py         # Crossref DOI metadata verification client
│   ├── author_disambiguation.py   # Multi-factor author matching engine
│   └── publication_fetcher.py     # Publication enrichment & ambiguous match handler
│
├── data_processing/
│   ├── cleaning.py                # DOI, URL, email, designation & name normalization
│   ├── deduplication.py           # Entity deduplication (DOIs, OpenAlex IDs, faculty)
│   └── topic_extraction.py        # Research topic extraction and normalization
│
├── verification/
│   ├── review_queue.py            # Query pending/needs_review queues
│   ├── csv_export.py              # Export faculty & publication review queues to CSV
│   └── csv_import.py              # Import reviewed CSV approvals & record audit logs
│
├── scripts/
│   ├── initialize_database.py     # Seed university and create schema
│   ├── collect_departments.py     # Standalone department collection
│   ├── collect_faculty.py         # Standalone faculty directory & profile collection
│   ├── collect_publications.py    # Standalone publication ingestion & author matching
│   └── run_pipeline.py            # Unified 17-stage idempotent ingestion pipeline
│
├── data/
│   ├── raw/                       # Cached department directory & profile HTML
│   ├── processed/                 # Active database, backup, and 4 coverage reports
│   └── exports/                   # CSV review queues and approval files
│
├── tests/                         # Comprehensive automated test suite (31 tests)
│   ├── test_cleaning_and_processing.py
│   ├── test_database_and_models.py
│   ├── test_author_disambiguation.py
│   ├── test_scrapers_and_fetchers.py
│   ├── test_api_endpoints.py
│   └── test_review_and_idempotency.py
│
├── docker-compose.yml             # PostgreSQL 16 + FastAPI Docker configuration
├── Dockerfile                     # Container build specification
├── requirements.txt               # Python dependencies
├── .env.example                   # Configuration template
└── README.md
```

---

## Database Architecture

The schema is normalized, relational, and database-agnostic (supports both SQLite and PostgreSQL via SQLAlchemy and Alembic):

1. **`universities`**: Institution identity, country, region, city, and website.
2. **`departments`**: Academic departments, schools, centres, and academic units (`code`, `academic_unit`, `official_url`, `collection_status`, `source_access_notes`).
3. **`professors`**: Faculty records collected **independently of publication indexing**, storing `name`, `designation`, `academic_unit`, `appointment_category`, `educational_background`, `email`, `biography`, `research_interests`, `research_group`, `profile_url`, `source_url`, `openalex_author_id`, `orcid`, `verification_status`, and boolean availability flags (`has_publications`, `has_research_interests`, `has_biography`, `has_projects`).
4. **`publications`**: Publications with `openalex_id`, normalized `doi`, `title`, reconstructed `abstract`, `publication_year`, `journal_or_conference`, `authors_list`, `paper_url`, `source_url`, `citation_count`, `source_name`, and `verification_status`.
5. **`professor_publications`**: Many-to-many relationship linking professors to publications with `author_position`, `confidence_score`, `affiliation_evidence`, and `verification_status` (`verified`, `pending`, `needs_review`, `rejected`).
6. **`research_topics`**: Normalized research topics and keywords across engineering, sciences, humanities, law, medicine, and management.
7. **`professor_topics`**: Associates professors with research topics.
8. **`publication_topics`**: Associates publications with research topics.
9. **`research_projects`**: Sponsored research projects (`title`, `status`, `source_url`) extracted from official faculty profiles.
10. **`professor_projects`**: Associates professors with research projects and their role (`Principal Investigator`, `Co-Principal Investigator`).
11. **`data_sources`**: Provenance tracking for collected records (`entity_type`, `entity_id`, `source_name`, `source_url`, `http_status`, `retrieval_error`, `retrieved_at`).
12. **`verification_records`**: Audit log of manual and automated verification status transitions (`entity_type`, `entity_id`, `previous_status`, `new_status`, `verified_by`, `evidence_or_notes`, `source_url`, `verified_at`).

---

## Data Collection Sources & Status

| Source | Target / Purpose | Access Status | Handling / Notes |
|---|---|---|---|
| **IIT Kharagpur Website** (`www.iitkgp.ac.in`) | Academic units (`/navpage/academics`), Official department faculty directory AJAX (`POST /Departments/showPeopleFormerStaff`), Individual faculty profile pages | **Accessible (HTTP 200)** | Primary source for all 65 academic units and faculty identity, regardless of publication indexing. |
| **OpenAlex API** (`api.openalex.org`) | Works, reconstructed abstracts, OpenAlex Author IDs, venues, co-authors, topics | **Accessible (HTTP 200)** | Institution ID: `I145894827` (ROR: `03w5sq511`). Used as an independent enrichment step. |
| **Crossref API** (`api.crossref.org`) | DOI verification, publication year & venue validation | **Accessible (HTTP 200)** | Verifies DOI metadata and journal/conference titles. |
| **IIT KGP FacWeb** (`erp.iitkgp.ac.in/FacWeb/`) | Legacy ERP Faculty directory | **Inaccessible (HTTP 404)** | Deprecated endpoint; logged gracefully without failure. |
| **IIT KGP IRINS** (`iitkgp.irins.org`) | Institutional Research Information System | **Inaccessible (HTTP 403)** | Protected by anti-bot challenge; respected without bypassing. |

---

## 17-Stage Idempotent Pipeline (`scripts/run_pipeline.py`)

1. **Stage 1**: Initialize or migrate database and seed university record.
2. **Stage 2**: Discover all 65 IIT Kharagpur academic units (departments, schools, centres, academies).
3. **Stage 3**: Collect faculty from official department directories (`faculty`, `inspired_faculty`, `adjunct_faculty`) and enrich profiles (`div#research_statement`, research areas, sponsored projects).
4. **Stage 4**: Clean and deduplicate faculty records; reconcile primary department affiliations and reject broken/non-person entries.
5. **Stage 5**: Persist faculty candidates independently of publications (`has_publications=False` by default until linked).
6. **Stage 6**: Export faculty review queue (`data/exports/faculty_review_queue.csv`).
7. **Stage 7**: Import approved faculty records (`data/exports/faculty_approved.csv`) and record verification audit entries.
8. **Stage 8**: Discover publication authors in OpenAlex (`I145894827`).
9. **Stage 9**: Fetch publication candidates, venues, co-author lists, and inverted-index abstracts.
10. **Stage 10**: Verify publication DOIs and metadata via Crossref.
11. **Stage 11**: Perform multi-factor author disambiguation (`verified`, `pending`, `needs_review`, `rejected`).
12. **Stage 12**: Persist publication candidates and update `has_publications`.
13. **Stage 13**: Export publication review queue (`data/exports/publication_review_queue.csv`).
14. **Stage 14**: Import approved publication relationships (`data/exports/publication_approved.csv`).
15. **Stage 15**: Extract and normalize research topics across professors and publications.
16. **Stage 16**: Generate `data/processed/collection_summary_report.json`.
17. **Stage 17**: Generate `data/processed/department_coverage_report.csv`, `data/processed/faculty_coverage_report.csv`, and `data/processed/publication_coverage_report.csv`.

---

## Quickstart & Execution

### 1. Setup Environment
```bash
python -m pip install -r requirements.txt
```

### 2. Configure Database & Migrations
By default, the project runs on SQLite at `sqlite:///./data/processed/professor_discovery.db` (configured in `.env`). PostgreSQL is fully supported by setting `DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5432/professor_discovery` in `.env` (or running `docker-compose up -d db`).

Apply Alembic migrations:
```bash
python -m alembic upgrade head
```

### 3. Run the Ingestion Pipeline
```bash
# Run full 17-stage pipeline:
python -m scripts.run_pipeline --enrich-profiles --limit-pubs 15 --auto-approve

# Run specific stages (e.g. regenerate reports):
python -m scripts.run_pipeline --stages 15 16 17
```

### 4. Run Automated Tests
```bash
python -m pytest tests -v
```

### 5. Start FastAPI Web Server
```bash
uvicorn backend.api.main:app --reload --port 8000
```

---

## API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/universities` | List universities (supports `?country=India`) |
| `GET` | `/universities/{id}/departments` | List all academic units in a university |
| `GET` | `/departments/{id}/professors` | List professors in a department (`?status=`, `?has_publications=`) |
| `GET` | `/professors` | Paginated professor list (`?department_id=`, `?status=`, `?has_publications=`, `?search=`, `?page=`, `?page_size=`) |
| `GET` | `/professors/{id}` | Detailed professor profile including topics, biography, and availability flags |
| `GET` | `/professors/{id}/publications` | List publications for a professor (returns `[]` cleanly when professor has 0 publications) |
| `GET` | `/publications/{id}` | Detailed publication metadata, reconstructed abstract, venue, authors, and DOI |
| `GET` | `/admin/review/faculty` | Review queue for faculty (`?status=pending` or `?status=needs_review`) |
| `GET` | `/admin/review/publications` | Review queue for publication records (`?status=pending` or `?status=needs_review`) |
