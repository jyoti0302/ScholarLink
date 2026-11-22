# Pre-Phase 2 Data Quality Correction Report — IIT Kharagpur Professor Discovery Platform

**Generated:** 2026-11-16  
**Database:** `data/processed/professor_discovery.db`  
**Preserved Backups:**  
- Pre-Phase A Backup: `data/processed/professor_discovery.db.pre_phase2_cleanup_backup`  
- Pre-Phase B Backup: `data/processed/professor_discovery.db.pre_phase_b_backup`  
- Pre-Phase C Backup: `data/processed/professor_discovery.db.pre_phase_c_backup`

---

## 1. Executive Summary & Before- vs. After-Cleanup Statistics

All three approved data-quality correction phases (**Phase A: Publication Verification & Public API Visibility**, **Phase B: Research Project Cleanup**, and **Phase C: Research Topic Normalization**) were executed sequentially inside database transactions with full backup and audit logging (`verification_records`).

| Metric / Table | Before Cleanup (Pre-Phase A) | After Cleanup (Post-Phase C) | Delta & Safeguard Verification |
| :--- | ---: | ---: | :--- |
| **Academic Units (`departments`)** | `65` | `65` | `0` (`100%` preserved) |
| **Faculty Records (`professors`)** | `877` | `877` | `0` (`0` faculty rows deleted; all `professor.id` keys preserved) |
| **Unique Publications (`publications`)** | `4,136` | `4,136` | `0` (`0` publication rows deleted; all `publication.id` keys preserved) |
| **Author-Publication Links (`professor_publications`)** | `4,679` | `4,679` | `0` (`0` link rows deleted) |
| — `verified` links | `84` | **`84`** | `84` verified links across `13` professors preserved |
| — `pending` links | `4,008` | **`3,910`** | `3,909` kept `pending` + `1` upgraded (`Arindam Basu [IP]`, `link_id=2241`) |
| — `needs_review` links | `587` | **`438`** | `429` kept `needs_review` + `9` demoted from `pending` |
| — `rejected` links | `0` | **`247`** | `90` from `pending` + `157` from `needs_review` (`217` name mismatches + `30` homonym links) |
| **`Professor.has_publications == True`** | `641` | **`13`** | Strictly represents professors with $\ge 1$ `verified` publication link |
| **Unique Research Projects (`research_projects`)** | `7,790` | **`7,760`** | `-30` (merged the exact `30` near-duplicate pairs; `0` non-duplicate deletions) |
| — `sponsored_research` | *(unclassified)* | **`7,172`** | Core R&D sponsored projects |
| — `routine_testing_vetting` | *(unclassified)* | **`411`** | Routine structural/hydraulic vetting, proof-checking, testing & calibration |
| — `industrial_consultancy` | *(unclassified)* | **`127`** | Industrial consultancy, DPRs & techno-economic feasibility studies |
| — `administrative_or_grant` | *(unclassified)* | **`50`** | Travel grants, conference/symposium grants & internal account codes |
| — `ALL CAPS` titles (`>10` chars) | `1,242` | **`9`** | `1,232` converted to readable Title Case (`original_title` preserved on all `7,760` rows) |
| **Professor-Project Links (`professor_projects`)** | `12,856` | **`12,801`** | `-55` duplicate links collapsed across the `30` merged pairs (`1` distinct Co-PI link transferred; `0` PI/Co-PI roles lost) |
| **Professors with $\ge 1$ Research Project** | `789` | **`789`** | `0` change (`100%` faculty project coverage preserved) |
| **Research Topics (`research_topics`)** | `6,553` | **`6,553`** | `0` (`0` topic rows deleted; all `topic_name` values preserved) |
| — Distinct `canonical_topic_name` values | `6,553` | **`6,495`** | `69` acronym/plural/punctuation/typo variants mapped to unified canonical names |
| — Topics assigned 3-Tier `Domain -> Area -> Canonical` | `0` | **`6,553`** | `100%` classified across `9` Domains and `25` Research Areas (`6,343` linked via `parent_topic_id`) |
| — Generic Level-0 Root Topics (`is_generic_root=1`) | `0` | **`21`** | Broad OpenAlex discipline tags (`Computer science`, `Engineering`, `Chemistry`, etc.) |
| — Noisy Artifact Topics (`is_noisy_artifact=1`) | `0` | **`197`** | Wikipedia parenthetical disambiguation tags (`(grammar)`, `(psychology)`), `>65` char phrases, unsplit `;`/`:` |
| **Professor-Topic Links (`professor_topics`)** | `3,960` | **`3,960`** | `0` (`100%` preserved) |
| **Publication-Topic Links (`publication_topics`)** | `17,451` | **`17,451`** | `0` (`100%` preserved) |
| **Audit Trail (`verification_records`)** | `1,028` | **`1,316`** | **`+288`** audit records logged (`+257` Phase A, `+30` Phase B, `+1` Phase C) |
| **SQLite Foreign Key Integrity Errors** | `0` | **`0`** | Verified via `PRAGMA foreign_key_check` |

---

## 2. Phase A — Publication Verification & Public API Visibility

### 2.1 Fixes Applied to Author Disambiguation (`data_collection/author_disambiguation.py` & `data_processing/cleaning.py`)
1. **Honorific Normalization (`clean_author_name`)**: Updated regex to `r"^(?:Professor|Doctor|Prof|Dr|Mr|Ms|Mrs|Shri|Smt)(?:\.|\b)\s*"` so honorifics with or without periods (`"Prof. Niloy Ganguly"`, `"Dr Binita Tiwari"`) are stripped cleanly without consuming punctuation into the name.
2. **First-Name, Surname & Initial Compatibility (`calculate_name_similarity`)**:
   - Matches identical full tokens (`len > 1`) first so 1-letter initials cannot falsely match an already-shared middle or last name.
   - Expands 2-letter uppercase leading/middle initials (`"VN Achutha Naikan"` $\leftrightarrow$ `"V N Achutha Naikan"`).
   - Preserves South Indian inverted surname-initial conventions (`"Mahendra Reddy Vanteru"` $\leftrightarrow$ `"V. Mahendra Reddy"`, `"M Amaranatha Reddy"` $\leftrightarrow$ `"Amaranatha Reddy Muppireddy"`).
   - Rejects (`0.0`) any pair where both sides have conflicting full tokens or conflicting initials (`"Gaurab Das Mahapatra"` vs `"Rita Das Mahapatra"`, `"Nihar Ranjan Jana"` vs `"Nihar Ranjan Sahu"`, `"Krothapalli Sreenivasa Rao"` vs `"Y. Sreenivasa Rao"`).
   - Scores strict token-subset / extra-initial matches (`"Arup Das"` vs `"Arup K. Das"`, `"Sri Krishna Kumar"` vs `"Krishna Kumar"`, `"P V S N Murthy"` vs `"P. V. Murthy"`) at `0.55` (`needs_review`).

### 2.2 Re-evaluation of the `231` Suspicious Links & `27` Shared Homonym Publications (`54` Links)
- **Across the `231` suspicious first/last-name mismatch links**:
  - **`217` moved to `rejected`** (`69` from `pending`, `148` from `needs_review`).
  - **`2` moved from `pending` to `needs_review`** (`link_ids=3711, 3714`: `Sri Krishna Kumar` vs `Krishna Kumar`).
  - **`5` retained in `needs_review`** (`link_ids=2496, 2976, 2977, 3308, 3309`).
  - **`7` retained in `pending`** (`link_ids=1891, 1892, 2982, 2984, 2986, 2989, 3607`: South Indian inverted initials & `"Dr Binita Tiwari"`).
- **Across the `234` same-first-and-last-name initial expansions**:
  - **`227` valid middle-initial expansions preserved** (`9` `verified`, `115` `pending`, `103` `needs_review`).
  - **`7` uncertain extra-initial links moved from `pending` to `needs_review`** (`link_ids=1818, 1820, 2464, 2465, 2466, 3779, 3911`).
- **Across the `27` shared publications (`54` links) on the 3 exact faculty homonym pairs**:
  - **`Abhijit Das` (`id=27` `CS` vs `id=112` `BT`)**: Kept `14` Cryptography/Number Theory papers on `id=27` (`CS`), rejected `14` links on `id=112` (`BT`), and rejected `pub_id=336` (*Cooperative Adaptive Control for Higher-Order Nonlinear Systems*) on both `CS` and `BT`.
  - **`Arindam Basu` (`id=390` `GG` vs `id=740` `IP`)**: Upgraded `pub_id=1466` (*Oxford Handbook of Environmental and Natural Resources Law in India*) to `pending` (`0.90`) on `id=740` (`IP` - Law) and rejected on `id=390` (`GG`); kept `pub_id=1468` (*Journal of the Geological Society of India*) on `id=390` (`GG`) and rejected on `id=740` (`IP`); rejected hardware circuit papers `pub_ids=1467, 1469` on both.
  - **`Santanu Chattopadhyay` (`id=365` `EC` vs `id=724` `RT`)**: Kept `2` Polymer/Rubber papers (`pub_ids=2172, 3059`) on `id=724` (`RT`) and rejected on `id=365` (`EC`); kept `6` VLSI/Network-on-Chip/Testing papers (`pub_ids=2760, 3058, 3060..3063`) on `id=365` (`EC`) and rejected on `id=724` (`RT`).

### 2.3 Public API Visibility & `Professor.has_publications` Semantics
- `Professor.has_publications` is now strictly `True` **only** when a professor has $\ge 1$ `verified` publication link (`13` professors).
- `ProfessorBriefSchema` and `ProfessorDetailSchema` expose `has_publications`, `verified_publication_count`, `pending_publication_count`, `needs_review_publication_count`, and `candidate_publication_count`.
- `GET /professors/{professor_id}/publications` returns **`verified` publications only by default** (`status="verified"`).
- Querying candidate publications requires an explicit filter (`?status=pending` or `?status=needs_review`).
- Requesting `?status=rejected` on the public endpoint returns `HTTP 403 Forbidden`; rejected links are restricted to `GET /admin/review/professors/{professor_id}/publications`.

---

## 3. Phase B — Research Project Cleanup

1. **Deduplication of the `30` Near-Duplicate Project Pairs**:
   - Merged all `30` identified near-duplicate pairs (`60` rows $\rightarrow$ `30` canonical rows), reducing `research_projects` from `7,790` to **`7,760`**.
   - Preserved all sponsor and funding details (e.g., merging `SERB` and `ANRF` sponsor strings on canonical project `id=5350`: *"Manufacturing of Bimetallic Ti - Al alloy structure by CMT-WAAM"*).
   - Merged `professor_projects` links without losing a single `Principal Investigator` or `Co-Principal Investigator` relationship (`55` duplicate links collapsed, `1` distinct Co-PI link for `prof_id=652` transferred from `id=1255` to `id=1254`, resulting in `12,801` clean links across all `789` professors).
   - Logged `30` audit records in `verification_records` (`verified_by="phase2_phase_b_dedup"`).
2. **Preservation of Original Titles & Normalization**:
   - Stored the exact pre-cleanup extracted string in `research_projects.original_title` for all `7,760` projects (`0` nulls).
   - Fixed missing line-wrap spaces and hyphens (`CondensateFormation` $\rightarrow$ `Condensate Formation`, `forTuberculosis` $\rightarrow$ `for Tuberculosis`, `DrugLoaded` $\rightarrow$ `Drug Loaded`, `InstrumentationSystem` $\rightarrow$ `Instrumentation System`, `withInformation` $\rightarrow$ `with Information`, `FluxHollow` $\rightarrow$ `Flux Hollow`, `ofBrackish` $\rightarrow$ `of Brackish`, `Lab-ona-Chip` $\rightarrow$ `Lab-on-a-Chip`).
   - Converted `1,232` multi-word `ALL CAPS` project titles into readable Title Case while preserving `580+` technical and agency acronyms (`UAV`, `MAV`, `CFD`, `VLSI`, `DRDO`, `ISRO`, `ICMR`, `SERB`, `ANRF`, `MHRD`, `NTPC`, `BHEL`, `RDSO`, `NHAI`, etc.).
3. **Non-Destructive Project Classification (`project_category`)**:
   - `sponsored_research`: **`7,172`** projects (`92.4%`)
   - `routine_testing_vetting`: **`411`** projects (`5.3%`)
   - `industrial_consultancy`: **`127`** projects (`1.6%`)
   - `administrative_or_grant`: **`50`** projects (`0.6%`)

---

## 4. Phase C — Research Topic Normalization

1. **Non-Destructive Schema Extensions on `research_topics`**:
   - Added `canonical_topic_name`, `domain_name`, `area_name`, `parent_topic_id`, `is_generic_root`, and `is_noisy_artifact` to `research_topics` without deleting any of the `6,553` topics or any of the `3,960` `professor_topics` / `17,451` `publication_topics` links.
2. **Acronym, Singular/Plural, Spelling & Punctuation Normalization**:
   - Mapped acronyms and parenthetical acronym variants to canonical full forms (`NLP` $\rightarrow$ `Natural Language Processing`, `IOT` / `Internet of Things (IoT)` $\rightarrow$ `Internet of Things`, `CFD` / `Computational Fluid Dynamics (CFD)` $\rightarrow$ `Computational Fluid Dynamics`, `ML` $\rightarrow$ `Machine Learning`, `AI` $\rightarrow$ `Artificial Intelligence`, `VLSI` $\rightarrow$ `Very Large Scale Integration (VLSI)`, `UAV` / `UAVs` $\rightarrow$ `Unmanned Aerial Vehicles`, `FEM` $\rightarrow$ `Finite Element Method`, `CPS` $\rightarrow$ `Cyber-Physical Systems`, etc.).
   - Mapped singular/plural pairs (`Biofuel`/`Biofuels` $\rightarrow$ `Biofuels`, `Biosensor`/`Biosensors` $\rightarrow$ `Biosensors`, `Microgrid`/`Microgrids` $\rightarrow$ `Microgrids`, etc.), punctuation variants (`- 6g`/`6g` $\rightarrow$ `6G Wireless Communications`, `& Analytics` $\rightarrow$ `Analytics`, `Decision-making`/`Decision making` $\rightarrow$ `Decision Making`), and typos (`structuress` $\rightarrow$ `Structures`, `tansportation` $\rightarrow$ `Transportation`), consolidating `6,553` raw strings into **`6,495` distinct canonical topics** without merging ambiguous terms (e.g., `"Action (physics)"` vs `"Action"` remain distinct).
3. **Three-Tier Taxonomy (`Domain -> Research Area -> Canonical Topic`)**:
   - Assigned all `6,553` topics across **9 top-level Domains** and **25 Research Areas**, with `6,343` topics linked to their area's representative parent topic via `parent_topic_id`:
     - *Biosciences, Bioengineering, Agriculture & Medical Technology*: `2,005` topics
     - *Mechanical, Aerospace & Manufacturing Engineering*: `1,213` topics
     - *Civil, Infrastructure, Earth & Environmental Sciences*: `812` topics
     - *Computer Science & Artificial Intelligence*: `765` topics
     - *Electrical, Electronics & Communication Engineering*: `463` topics
     - *Humanities, Social Sciences, Management & Law*: `426` topics
     - *Basic Sciences (Physics, Chemistry & Mathematics)*: `379` topics
     - *Materials, Metallurgical & Chemical Engineering*: `291` topics
     - *Interdisciplinary & General Engineering Sciences*: `199` topics
4. **Root & Artifact Flagging for Future Semantic Indexing**:
   - Flagged **`21`** broad OpenAlex Level-0 discipline concepts (`is_generic_root = True`).
   - Flagged **`197`** noisy artifacts (`is_noisy_artifact = True`: Wikipedia disambiguation suffixes like `Object (grammar)`, sentence-length `>65` char strings, leading punctuation fragments, and unsplit `;` / `:` strings).
