# Phase 2 Pre-Implementation Data-Quality Audit Report

**Institution**: Indian Institute of Technology Kharagpur (`IIT Kharagpur`)  
**Database Audited**: [`data/processed/professor_discovery.db`](file:///c:/Users/jyoti/OneDrive/MTP_2/data/processed/professor_discovery.db) (Read-Only Audit)  
**Audit Date**: 2026-11-16  
**Scope**: Focused pre-Phase 2 audit across (1) Publication Verification, (2) Research Project Quality, and (3) Research Topic Normalization. No records were modified or deleted during this audit.

---

## Executive Summary

| Audit Dimension | Total Records | High-Quality / Clean | Flagged / Needs Correction | Primary Quality Issue Identified |
| :--- | ---: | ---: | ---: | :--- |
| **Professor–Publication Links** | `4,679` (`4,136` unique pubs) | `4,421` (`94.5%` exact or valid initial-expansion matches) | `258` (`5.5%`: `231` first/last-name token-overlap mismatches + `27` shared links across `3` exact faculty homonym pairs) | 2-token overlap (`len(intersection) >= 2`) in `AuthorDisambiguator` matches shared middle+last names (`"Kumar Das"`, `"Das Mahapatra"`, `"Prakash Sharma"`) across different first names; 3 exact faculty homonym pairs share 27 duplicate links. |
| **Research Projects** | `7,790` (`12,856` prof–project links) | `7,271` (`93.3%` distinct sponsored/R&D projects; `7,301` keeping 30 canonical near-dups) | `519` distinct rows (`526` raw sum across categories minus `7` overlapping rows; `489` distinct if counting only the `30` redundant near-dup rows) | `60` rows in `30` near-duplicate pairs (`30` redundant) + `12` CMS-truncated titles (`>=380` chars) + `14` cryptic codes (`<=12` chars) + `440` routine vetting/testing/grant entries = `526` raw (`7` overlaps: `6` truncated vetting titles + `1` `"TRAVEL GRANT"` = `519` distinct rows). |
| **Research Topics** | `6,553` (`160` shared between profs & pubs) | `6,343` (`96.8%` atomic domain concepts; `6,398` keeping 55 canonical singular/hyphen forms) | `210` distinct rows (`211` raw sum across 6 categories minus `1` overlap; `155` distinct if counting only redundant plural/hyphen rows) | `72` rows in `36` singular/plural pairs (`36` redundant) + `38` rows in `19` hyphen/space groups (`19` redundant) + `17` sentence-length phrases + `14` colon/semicolon strings + `15` generic Level-0 OpenAlex concepts + `55` Wikipedia disambiguation artifacts = `211` raw (`1` overlap = `210` distinct rows). |

---

## 1. Publication Verification Audit

### 1.1 Actual Database Statistics

#### A. `publications` Table (`4,136` Total Records)
| Verification Status | OpenAlex (`source_name='openalex'`) | Crossref (`source_name='crossref'`) | Total Publications | Share of Total |
| :--- | ---: | ---: | ---: | ---: |
| **`verified`** | `84` | `0` | **`84`** | `2.0%` |
| **`pending`** | `714` | `2,879` | **`3,593`** | `86.9%` |
| **`needs_review`** | `259` | `200` | **`459`** | `11.1%` |
| **`rejected`** | `0` | `0` | **`0`** | `0.0%` |
| **Total** | **`1,057`** | **`3,079`** | **`4,136`** | **`100.0%`** |

- **Metadata Completeness (`publications`)**:
  - **Normalized DOIs present**: `4,128 / 4,136` (`99.8%`; `0` duplicate DOIs)
  - **Publication Years present**: `4,134 / 4,136` (`99.95%`; `2` missing year, `2` pre-1980 historical matches)
  - **Journal / Conference Venue present**: `3,971 / 4,136` (`96.0%`; `165` missing venue, primarily arXiv/preprint DOIs)
  - **Abstracts present**: `2,297 / 4,136` (`55.5%`; `1,839` Crossref/OpenAlex works lack public abstract metadata in source APIs)

#### B. `professor_publications` Table (`4,679` Total Links Across `737` Professors)
| Link Status | Source: OpenAlex | Source: Crossref | Total Links | Min Confidence | Avg Confidence | Max Confidence |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **`verified`** | `84` | `0` | **`84`** | `0.85` | `0.89` | `0.90` |
| **`pending`** | `856` | `3,152` | **`4,008`** | `0.85` | `0.90` | `0.90` |
| **`needs_review`** | `347` | `240` | **`587`** | `0.00` | `0.58` | `0.70` |
| **`rejected`** | `0` | `0` | **`0`** | — | — | — |
| **Total** | **`1,287`** | **`3,392`** | **`4,679`** | **`0.00`** | **`0.86`** | **`0.90`** |

- **Confidence Score Distribution (`professor_publications`)**:
  - `confidence = 0.90`: `3,883` links (`75` `verified`, `3,808` `pending`)
  - `confidence = 0.85`: `209` links (`9` `verified`, `200` `pending`)
  - `confidence = 0.70`: `186` links (`needs_review`)
  - `confidence = 0.65`: `66` links (`needs_review`)
  - `confidence = 0.55`: `2` links (`needs_review`)
  - `confidence = 0.50`: `328` links (`needs_review`)
  - `confidence <= 0.30`: `5` links (`needs_review`)

- **Author Name Token-Matching Audit Across All `4,679` Links**:
  - **Exact Author Name Token Match** (`set(prof_tokens) == set(paper_author_tokens)`): **`4,214` links** (`90.1%`)
  - **Valid Initial / Middle-Name Expansion** (same first & last name, e.g., `Hari V Warrior` $\leftrightarrow$ `Hari Vijayan Warrior` or `Mahendra Reddy Vanteru` $\leftrightarrow$ `V. Mahendra Reddy`): **`234` links** (`5.0%` — `9` `verified`, `122` `pending`, `103` `needs_review`)
  - **First-Name or Last-Name Mismatch** (different person sharing 2 name tokens such as middle+last name `"Kumar Das"` or `"Das Mahapatra"`): **`231` links** (`4.9%` — `0` `verified`, **`78` `pending`**, **`153` `needs_review`**)
  - **Exact Faculty Homonym Collisions** (identical full name shared by two professors in different IIT Kharagpur departments): **`27` shared publication links** (`54` link rows across `3` professor pairs)

---

### 1.2 Concrete Examples of Detected Problems & Sample Source URLs

#### Problem 1A: False Positive 2-Token Overlap on Shared Middle + Last Names (`78` `pending` links, `153` `needs_review` links)
In [`data_collection/author_disambiguation.py`](file:///c:/Users/jyoti/OneDrive/MTP_2/data_collection/author_disambiguation.py#L47-L49), `calculate_name_similarity()` returns `0.85` whenever `len(tokens_a.intersection(tokens_b)) >= 2`, without verifying that the **first name** (given name) and **last name** (family name) actually match. For 3-token Indian names (`<First> <Middle> <Last>`), two completely different individuals who share `<Middle> <Last>` (e.g., `"Kumar Das"`, `"Das Mahapatra"`, `"Prakash Sharma"`, `"Kumar Gupta"`) or `<First> <Middle>` (e.g., `"Nihar Ranjan"`, `"Arun Kumar"`) receive a `0.85` name similarity score (`+0.30` in `evaluate_publication_authorship` + `0.40` IIT Kharagpur affiliation -> `0.70`, which `PublicationFetcher._persist_fetched_result` boosted to `0.85` (`pending`) when `author_match_status != "needs_review"`).

- **Example 1 (Law Professor Linked to Geophysics Papers — `pending`, `conf=0.85`)**:
  - **Professor**: `Prakash Sharma` (`professor_id=750`, Dept: `IP` — Rajiv Gandhi School of Intellectual Property Law, Research Interests: *International Law, Criminal Law, Administrative Law*)
  - **Official Profile URL**: https://www.iitkgp.ac.in/department/IP/faculty/ip-prakash
  - **Incorrectly Linked Publication (`link_id=4427`, `pub_id=3168`)**: *"Integrating Apparent Conductance in Resistivity Sounding to Constrain 2D Gravity Modeling for Subsurface Structure Associated with Uranium Mineralization across South Purulia Shear Zone, West Bengal, India"* (`2014`, *International Journal of Geophysics*)
  - **Publication Source URL**: https://api.crossref.org/works/10.1155/2014/691521 (DOI: `10.1155/2014/691521`)
  - **Root Cause**: The paper's actual IIT Kharagpur author is **Prof. Shashi Prakash Sharma** (`professor_id=369`, Dept: `GG` — Geology and Geophysics, https://www.iitkgp.ac.in/department/GG/faculty/gg-spsharma). Because `"Prakash Sharma"` shares 2 tokens with `"Shashi Prakash Sharma"`, it matched with `confidence_score=0.85`.

- **Example 2 (Architecture Professor Linked to Chemistry Organogel Papers — `pending`, `conf=0.85`)**:
  - **Professor**: `Gaurab Das Mahapatra` (`professor_id=61`, Dept: `AR` — Architecture and Regional Planning, Research Interests: *Universal Design, Built Environment, Age-friendly Cities*)
  - **Official Profile URL**: https://www.iitkgp.ac.in/department/AR/faculty/ar-gaurabdasmahapatra
  - **Incorrectly Linked Publications (`link_ids=1107..1113`, `pub_ids=1141..1146`)**: 6 *Langmuir* / *Soft Matter* chemistry papers authored by `Rita Das Mahapatra` (e.g., *"Ultrasound-Induced Gelation of Organic Liquids by L-Cysteine-Derived Amphiphiles"*, DOI: `10.1021/acs.langmuir.5b02259`, Source URL: https://api.crossref.org/works/10.1021/acs.langmuir.5b02259).
  - **Root Cause**: Shared compound surname `"Das Mahapatra"` (`2` tokens) triggered `len(intersection) >= 2 -> sim=0.85` despite the completely different given name (`Gaurab` vs `Rita`).

- **Example 3 (First + Middle Name Overlap with Different Surname — `pending`, `conf=0.85`)**:
  - **Professor**: `Nihar Ranjan Jana` (`professor_id=121`, Dept: `BT` — Bioscience and Biotechnology, https://www.iitkgp.ac.in/department/BT/faculty/bt-nihar)
  - **Incorrectly Linked Publication (`link_id=1157`, `pub_id=1179`)**: *"Impact of air gap thickness on acoustic metamaterials with internal protrusions"* (DOI: `10.3397/in_2024_4039`, Source URL: https://api.crossref.org/works/10.3397/in_2024_4039), authored by `Nihar Ranjan SAHU` (sharing `"Nihar Ranjan"`).
  - **Professor**: `Arun Kumar Majumder` (`professor_id=566`, Dept: `MI` — Mining Engineering, https://www.iitkgp.ac.in/department/MI/faculty/mi-akm)
  - **Incorrectly Linked Publication (`link_id=3427`, `pub_id=1472`)**: *"Evidence for an Imbricated Lower Crust and Its Role in Accommodating Crustal Shortening in Sikkim Himalaya"* (DOI: `10.1029/2023tc008044`, Source URL: https://api.crossref.org/works/10.1029/2023tc008044), co-authored by `Arun Kumar Dubey` (sharing `"Arun Kumar"`).

- **Example 4 (OpenAlex Co-Author Fan-Out on `"Kumar Das"` — `needs_review`, `conf=0.65`–`0.70`)**:
  - **Publications (`pub_id=340` & `pub_id=350`)**: *"T-GNN: Gap-Aware Temporal Graph Learning for Vegetation Change Detection from UAV Imagery"* (https://openalex.org/W7223094566) and *"Uncertainty-Aware Self-Consistency Learning for Low-Altitude UAV-Based Crop Health Assessment"* (https://openalex.org/W7160423839), co-authored by `Rajendra Machavaram` (`AG`) and `Shyamal Kumar Das Mandal` (`AT`).
  - **Root Cause**: Because `Shyamal Kumar Das Mandal` contains `{"kumar", "das"}`, the co-author indexer created `needs_review` links (`conf=0.65`–`0.70`) for 5 other professors named `<First> Kumar Das` (`Amit Kumar Das [BT]`, `Manab Kumar Das [ME]`, `Prasanta Kumar Das [ME]`, `Amal Kumar Das [PH]`, `Rajat Kumar Das [MS]`).

#### Problem 1B: Exact Faculty Homonyms Across Different IIT Kharagpur Departments (`3` Pairs, `27` Shared Publications)
Three pairs of IIT Kharagpur faculty share the **exact same full name** across different departments. Because Crossref and OpenAlex queries by `author_name + "Indian Institute of Technology Kharagpur"` do not filter by department name, both professors in each pair were linked to the same pool of papers:

1. **`Abhijit Das` (`15` shared publications)**:
   - `professor_id=27` (`CS` — Computer Science and Engineering, https://www.iitkgp.ac.in/department/CS/faculty/cs-abhij, Research: *Cryptography, Number Theory*)
   - `professor_id=112` (`BT` — Bioscience and Biotechnology, https://www.iitkgp.ac.in/department/BT/faculty/bt-abhijit.das, Research: *Cancer Biology, Cell Signaling*)
   - **Collision**: Both are linked to 15 Computer Science / Cryptography papers (e.g., `pub_id=323`, *"Security Analysis of WAGE Against Division Property Based Cube Attack"*, *Lecture Notes in Computer Science*, DOI: `10.1007/978-981-99-7032-2_29`, https://openalex.org/W4387930791). All 15 belong to `professor_id=27` (`CS`) and are false associations for `professor_id=112` (`BT`).
2. **`Arindam Basu` (`4` shared publications)**:
   - `professor_id=390` (`GG` — Geology and Geophysics, https://www.iitkgp.ac.in/department/GG/faculty/gg-abasu)
   - `professor_id=740` (`IP` — Rajiv Gandhi School of Intellectual Property Law, https://www.iitkgp.ac.in/department/IP/faculty/ip-arindam)
   - **Collision**: Both are linked to `pub_id=1466` (*"Energy and Sustainability"*, *The Oxford Handbook of Environmental and Natural Resources Law in India*, DOI: `10.1093/oxfordhb/9780198884682.013.43` — belongs to `IP` `id=740`) and `pub_id=1468` (*"Quantification of Microcrack Anisotropy in Quartzite"*, *Journal of the Geological Society of India*, DOI: `10.1007/s12594-012-0128-6` — belongs to `GG` `id=390`).
3. **`Santanu Chattopadhyay` (`8` shared publications)**:
   - `professor_id=365` (`EC` — Electronics & Electrical Communication Engg., https://www.iitkgp.ac.in/department/EC/faculty/ec-santanu, Research: *VLSI, Network-on-Chip*)
   - `professor_id=724` (`RT` — Rubber Technology, https://www.iitkgp.ac.in/department/RT/faculty/rt-santanu, Research: *Polymer Nanocomposites, Hydrogels*)
   - **Collision**: Both are linked to `pub_id=2172` (*"Thermoresponsive biodegradable PEG-PCL-PEG based injectable hydrogel for pulsatile insulin delivery"*, DOI: `10.1002/jbm.a.34800` — belongs to `RT` `id=724`) and 7 VLSI/NoC papers (e.g., `pub_id=3058`, *"Mesh-of-tree deterministic routing for network-on-chip architecture"*, DOI: `10.1145/1366110.1366191` — belongs to `EC` `id=365`).

#### Problem 1C: `pending` Relationships Treated as Confirmed Authorship in API & `has_publications` Flag
1. **`Professor.has_publications` Boolean Flag**:
   - In [`data_collection/publication_fetcher.py`](file:///c:/Users/jyoti/OneDrive/MTP_2/data_collection/publication_fetcher.py#L455-L456), `professor.has_publications = True` is set whenever `combined_status in ("pending", "verified")`. Consequently, `641` professors have `has_publications = True`, even though only `13` professors have human/audit-confirmed `verified` publication links (`84` links) and `628` professors have `pending` links (`4,008` links).
2. **`GET /professors/{professor_id}/publications` Endpoint Default Behavior**:
   - In [`backend/api/main.py`](file:///c:/Users/jyoti/OneDrive/MTP_2/backend/api/main.py#L146-L160), the `status` query parameter defaults to `None`, returning `verified`, `pending`, and `needs_review` relationships together unless the client explicitly filters by `?status=verified`.

---

### 1.3 Recommended Corrections (Publication Verification)
1. **Tighten `AuthorDisambiguator.calculate_name_similarity()`**:
   - Require the **last name (surname)** token to match AND the **first name (given name)** token to match (either exact token match or initial prefix match when one token has length `1`). Never return `0.85` when two multi-token names have different non-initial first names (e.g., `Gaurab Das Mahapatra` vs `Rita Das Mahapatra`, or `Amit Kumar Das` vs `Shyamal Kumar Das Mandal`) or different last names (`Nihar Ranjan Jana` vs `Nihar Ranjan Sahu`).
2. **Re-evaluate the `231` First/Last-Name Mismatch Links**:
   - Demote or reject the `78` `pending` links and `153` `needs_review` links where the matched paper author has a conflicting full first name or last name.
3. **Disambiguate the `3` Exact Homonym Professor Pairs (`27` shared publications)**:
   - Use department/venue/topic alignment and raw affiliation strings (`Computer Science` vs `Bioscience`, `Law` vs `Geology`, `Electronics/VLSI` vs `Rubber/Polymer`) to assign each of the `27` shared publications to the correct homonym professor and remove the cross-department false links.
4. **Separate `verified` vs `pending` in API & Flags**:
   - Add a `verified_only: bool = Query(False)` or default `status="verified"` filter option on public discovery endpoints, or expose `verified_publication_count` alongside `pending_publication_count` on `ProfessorDetailSchema` so downstream consumers never mistake `pending` candidates for `verified` authorship.

### 1.4 Potential Impact on Future Semantic Search (Phase 2)
- If `pending` or `needs_review` publications with middle+last name collisions are embedded into a professor's vector representation in Qdrant, a student searching for **Geophysics / Uranium Mineralization** would retrieve **Prof. Prakash Sharma (`IP` — Criminal & International Law)**, and a student searching for **Supramolecular Organogels** would retrieve **Prof. Gaurab Das Mahapatra (`AR` — Architecture)**.
- Similarly, embedding the `15` Cryptography papers under **Prof. Abhijit Das (`BT` — Cancer Biology)** would cause severe cross-disciplinary hallucination during RAG-based research summary and cover-letter generation.

---

## 2. Research Project Quality Audit

### 2.1 Actual Database Statistics

| Metric | Count | Share / Details |
| :--- | ---: | :--- |
| **Total Unique Research Projects (`research_projects`)** | **`7,790`** | `0` exact normalized-title duplicates |
| **Completed Projects (`status='completed'`)** | **`6,336`** | `81.3%` (extracted from `<div id="compleated_project">`) |
| **Current / Ongoing Projects (`status='current'`)** | **`1,454`** | `18.7%` (extracted from `<div id="current_projects">`) |
| **Projects with Sponsor / Funding Agency (`description` & `sponsor`)** | **`1,452`** | `99.86%` of `current` projects (`0` of `completed` projects, as IIT KGP HTML omits `<b>Sponsor</b>` in `<div id="compleated_project">`) |
| **Total Professor–Project Links (`professor_projects`)** | **`12,856`** | Across `789` professors (`0` duplicate `(professor_id, project_id)` pairs) |
| **Principal Investigator (`PI`) Links** | **`8,219`** | `63.9%` of links |
| **Co-Principal Investigator (`Co-PI`) Links** | **`4,637`** | `36.1%` of links |
| **Collaborative Projects Linked to $>1$ IIT KGP Professor** | **`3,042`** | `39.1%` of projects (shared across PIs and Co-PIs) |

---

### 2.2 Multi-Department Sample Verification Against Official IIT Kharagpur Sources

We verified extracted project records against the raw official HTML pages (`https://www.iitkgp.ac.in/department/<CODE>/faculty/<SLUG>`) across 10 departments (`AE`, `AG`, `BT`, `CE`, `CH`, `CS`, `EE`, `HS`, `ME`, `NA`):

1. **Aerospace Engineering (`AE`) — Prof. Arnab Roy** (https://www.iitkgp.ac.in/department/AE/faculty/ae-arnab):
   - Official HTML lists 21 completed PI/Co-PI projects (`"AERODYNAMIC INVESTIGATION OF SMART FLYING WING MAV"`, `"SPIC MACAY (MAC)"`, etc.). All 21 match the official HTML verbatim; no navigation text or research statements were misclassified as projects.
2. **Bioscience & Biotechnology (`BT`) — Prof. Arindam Mondal** (https://www.iitkgp.ac.in/department/BT/faculty/bt-arindam.mondal):
   - Official HTML lists 14 current projects (with `<b>Sponsor</b>` tags such as `Indian Council of Medical Research (ICMR)` and `DBT, NEW DELHI`) and 2 completed projects. All sponsor tags were cleanly separated into `ResearchProject.sponsor` / `description`.
3. **Civil Engineering (`CE`) — Prof. Ashok Kumar Gupta** (https://www.iitkgp.ac.in/department/CE/faculty/ce-agupta):
   - Official HTML lists large water-supply consultancy/vetting projects (some exceeding 450 characters).

---

### 2.3 Detected Quality Issues & Concrete Examples

#### Issue 2A: `30` Near-Duplicate Project Pairs (`60` Rows) Caused by Missing Spaces at Line Wraps or Hyphens
In the official IIT Kharagpur CMS, when a project moves from `current_projects` to `compleated_project` (or is entered separately by a PI and Co-PI), line breaks inside the ERP database occasionally stripped a space between two words (`"multiplexed lateral"` vs `"multiplexedlateral"`, `"Condensate Formation"` vs `"CondensateFormation"`) or dropped a hyphen (`"Photovoltaic-thermal"` vs `"Photovoltaicthermal"`, `"Multi-functional"` vs `"Multifunctional"`). Because `normalize_project_key` normalized hyphens to spaces (`"multi-functional"` -> `"multi functional"` != `"multifunctional"`), these **30 pairs (`60` rows)** remained as separate `ResearchProject` rows:

- **Pair 1 (`project_id=1254` vs `project_id=1255`)**:
  - `id=1254`: *"Differential diagnostics of infectious diseases on a **multiplexed lateral** flow assay platform using gargle samples"* (`Sponsor: Ministry of Electronics and Information Technology`)
  - `id=1255`: *"Differential diagnostics of infectious diseases on a **multiplexedlateral** flow assay platform using gargle samples"*
  - **Source URL**: https://www.iitkgp.ac.in/department/BT/faculty/bt-arindam.mondal
- **Pair 2 (`project_id=1438` vs `project_id=1439`)**:
  - `id=1438`: *"In Vitro And In Vivo Investigation Of Biomolecular **Condensate Formation** By HOX And TALE Transcription Factors And **Their Role** In Leukemia"*
  - `id=1439`: *"In Vitro And In Vivo Investigation Of Biomolecular **CondensateFormation** By HOX And TALE Transcription Factors And **TheirRole** In Leukemia"*
  - **Source URL**: https://www.iitkgp.ac.in/department/BT/faculty/bt-somde
- **Pair 3 (`project_id=1737` vs `project_id=1739`)**:
  - `id=1737`: *"Development of Nanoparticle Incorporated Polymeric High **Flux Hollow** Fiber Nanofilteration Prototype for Desalination **of Brackish** Water"*
  - `id=1739`: *"Development of Nanoparticle Incorporated Polymeric High **FluxHollow** Fiber Nanofilteration Prototype for Desalination **ofBrackish** Water"*
  - **Source URL**: https://www.iitkgp.ac.in/department/CH/faculty/ch-sde
- **Pair 4 (`project_id=642` vs `project_id=643`)**:
  - `id=642`: *"Development of an Unconventional Flapping-based **Sediment-aeration** System for the Brackish Water Aquaculture"*
  - `id=643`: *"Development of an Unconventional Flapping-based **Sedimentaeration** System for the Brackish Water Aquaculture"*
  - **Source URL**: https://www.iitkgp.ac.in/department/AE/faculty/ae-smdash
- **Pair 5 (`project_id=955` vs `project_id=956`)**:
  - `id=955`: *"Development of Self-sustained Modular Solar **Photovoltaicthermal** (PV-T) based Forced Convection Dryer for Agro-Crops"*
  - `id=956`: *"Development of Self-sustained Modular Solar **Photovoltaic-thermal** (PV-T) based Forced Convection Dryer for Agro-Crops"*
  - **Source URL**: https://www.iitkgp.ac.in/department/AG/faculty/ag-punam

#### Issue 2B: `12` CMS-Truncated Long Project Titles (`>= 380` to `500` Characters) & `1` Concatenated Numbered Project Entry
The IIT Kharagpur ERP/CMS truncates project titles at ~500 characters in the HTML source (`ResearchProject.title` is also `VARCHAR(500)`), cutting off mid-word or mid-clause on long civil/mining consultancy titles:
- **Example (`project_id=2377`, `499` chars, numbered list of 2 projects in a single `<li>`)**:
  - *"1. Hydraulic Design & Drawings and proof Checking & Technical Vetting of raw Water Mains for the work of Execution of Rural Piped Water Supply Project pertaining to 16GP of Jeypore block and 15 GP of Kundra Block in Koraput district including 05 years of operation and maintenance. 2. Hydraulic Design & Drawings and proof Checking & Technical Vetting of Raw Water Mains & Clear Water Mains for the work of Execution of Rural Piped Water Supply Project pertaining to 23GP of Kishore Nagar block & 03"*
  - **Source URL**: https://www.iitkgp.ac.in/department/CE/faculty/ce-agupta
- **Example (`project_id=7100`, `421` chars, truncated mid-phrase `"Perspective of"`)**:
  - *"Understanding the Mica-based Machinable Glass Ceramics Systems from an Unprecedented Perspective of"*
  - **Source URL**: https://www.iitkgp.ac.in/department/MT/faculty/mt-agrawal

#### Issue 2C: `14` Short / Cryptic Internal ERP Project Codes (`<= 12` Characters) & Administrative/Event Entries
Because the IIT Kharagpur SRIC (Sponsored Research & Industrial Consultancy) ERP logs internal grant codes, conference grants, and administrative accounts in the same project table, several entries are cryptic acronyms or non-research administrative grants:
- `project_id=5178`: `"ME DNC"` (https://www.iitkgp.ac.in/department/ME/faculty/me-skpal)
- `project_id=5176`: `"ALL LABS"` (https://www.iitkgp.ac.in/department/ME/faculty/me-skpal)
- `project_id=738`: `"IITKGP_SUB"` (`Sponsor: MHRD`, https://www.iitkgp.ac.in/department/AG/faculty/ag-mailapalli)
- `project_id=5166`: `"ICMR_ATTEND"` (`Sponsor: Indian Council of Medical Research (ICMR)`, https://www.iitkgp.ac.in/department/ME/faculty/me-kumar)
- `project_id=5440`: `"TRAVEL GRANT"` (https://www.iitkgp.ac.in/department/ME/faculty/me-suman)
- `project_id=7371`: `"Legal Opinion"` (https://www.iitkgp.ac.in/department/IP/faculty/ip-indrajit)
- `project_id=6`: `"SPIC MACAY (MAC)"` (Cultural society chapter account listed under completed projects on https://www.iitkgp.ac.in/department/AE/faculty/ae-arnab)

#### Issue 2D: `1,242` `ALL CAPS` Project Titles & `440` Routine Vetting/Testing Consultancy Entries
- **`1,242` projects (`15.9%`)** are stored in `ALL UPPERCASE` as entered into the IIT Kharagpur ERP (e.g., `project_id=3`: `"AERODYNAMIC INVESTIGATION OF SMART FLYING WING MAV"`).
- **`440` projects (`5.6%`)** are routine industrial testing, structural vetting, or calibration consultancies (e.g., `"Technical checking and vetting of process and hydraulic design and drawings..."`, `"Testing of Soil Samples..."`).

---

### 2.4 Recommended Corrections (Research Projects)
1. **Merge the `30` Alphanumeric Near-Duplicate Pairs (`60` -> `30` rows)**:
   - Use an alphanumeric key (`re.sub(r"[^a-z0-9]+", "", title.lower())`) during deduplication while keeping the better-spaced/hyphenated title as canonical and merging `ProfessorProject` links and sponsor descriptions.
2. **Restore Missing CamelCase / Line-Wrap Spaces**:
   - Apply a conservative regex cleaning rule (`re.sub(r"([a-z])([A-Z])", r"\1 \2", title)` for non-acronym words like `CondensateFormation` -> `Condensate Formation`, `TheirRole` -> `Their Role`, `FluxHollow` -> `Flux Hollow`, `ofBrackish` -> `of Brackish`).
3. **Normalize `ALL CAPS` Titles to Title/Sentence Case (Preserving Technical Acronyms)**:
   - Convert the `1,242` all-uppercase project titles into readable title case while preserving domain acronyms (`MAV`, `CFD`, `VLSI`, `UAV`, `ICMR`, `DRDO`, `ISRO`, `MHRD`, `AI`, `ML`, `IoT`).
4. **Flag Non-Research Administrative / Cryptic Grant Codes**:
   - Add a `project_type` classification or exclude non-informative administrative entries (`"ALL LABS"`, `"ME DNC"`, `"TRAVEL GRANT"`, `"SPIC MACAY (MAC)"`, `"IITKGP_SUB"`) from Phase 2 semantic indexing so they do not pollute professor research profiles.

### 2.5 Potential Impact on Future Semantic Search (Phase 2)
- Concatenated words (`CondensateFormation`, `multiplexedlateral`, `ofBrackish`) degrade subword tokenization in embedding models, reducing recall for exact technical terms (`"lateral flow assay"`, `"biomolecular condensate"`).
- Administrative entries (`"TRAVEL GRANT"`, `"ALL LABS"`, `"SPIC MACAY"`) and repetitive civil vetting boilerplate (`"Technical checking and vetting of hydraulic design..."` repeated 30+ times on a single profile) dilute a professor's core research signal when generating RAG context windows and research summaries.

---

## 3. Research Topic Normalization Audit

### 3.1 Actual Database Statistics

| Metric | Count | Notes |
| :--- | ---: | :--- |
| **Total Unique Research Topics (`research_topics`)** | **`6,553`** | `0` case-only duplicates (`get_or_create_topic` already performs case-insensitive lookup) |
| **Topics Linked Only to Professors (`professor_topics`)** | **`2,305`** | `35.2%` (extracted from IIT KGP profile `Research Areas` and `Area of Research:`) |
| **Topics Linked Only to Publications (`publication_topics`)** | **`4,088`** | `62.4%` (extracted from OpenAlex concepts and Crossref subjects) |
| **Topics Shared by Both Professors & Publications** | **`160`** | **`2.4%` overlap** — low overlap due to phrasing/granularity mismatch between faculty profiles and OpenAlex/Crossref subjects |
| **Orphan Topics (`0` links)** | **`0`** | `0.0%` |

---

### 3.2 Detected Quality Issues & Concrete Examples

#### Issue 3A: `36` Singular vs. Plural Duplicate Topic Pairs (`72` Rows)
Because `get_or_create_topic` matches exact case-insensitive strings without morphological singularization, singular and plural forms of the same research concept exist as separate rows in `research_topics`:
- `('algorithm', 'algorithms')`
- `('biosensor', 'biosensors')`
- `('boundary value problem', 'boundary value problems')`
- `('cellular network', 'cellular networks')`
- `('coating', 'coatings')`
- `('complex fluid', 'complex fluids')`
- `('computer network', 'computer networks')`
- `('control system', 'control systems')`
- `('decision support system', 'decision support systems')`
- `('electric vehicle', 'electric vehicles')`
- `('electrode', 'electrodes')`
- `('embedded system', 'embedded systems')`
- `('environmental law', 'environmental laws')`
- `('functionally graded material', 'functionally graded materials')`
- `('fuzzy control system', 'fuzzy control systems')`

#### Issue 3B: `19` Hyphen, En-Dash, Space, and Leading-Punctuation Variant Groups (`39` Rows)
Variations in hyphenation, Unicode en-dashes (`–`), and whitespace split identical concepts across multiple topic IDs:
- `['& analytics', 'analytics']` (leading `&` artifact from splitting `"Safety Engineering & Analytics"`)
- `['base flow', 'baseflow']`
- `['bio mechanics', 'biomechanics']`
- `['block chain', 'blockchain']`
- `['cognitive neuro-psychology', 'cognitive neuropsychology']`
- `['cyber physical systems', 'cyberphysical systems']`
- `['data analytics', 'dataanalytics']`
- `['fluid structure interaction', 'fluid–structure interaction']` (ASCII space vs. Unicode en-dash `U+2013`)
- `['health care', 'healthcare']` and `['health care management', 'healthcare management']`
- `['human computer interaction', 'human–computer interaction']`
- `['nano materials', 'nanomaterials']`

#### Issue 3C: Acronym vs. Expanded Full-Form Fragmentation
Professors and publication databases frequently use either the acronym, the full form, or `"Full Form (Acronym)"`, creating up to 3 separate topic entities for the same concept:
- **NLP**: `topic_id=227` (`'NLP'`) vs. `topic_id=231` (`'Natural Language Processing'`)
- **IoT**: `topic_id=237` (`'IOT'`) vs. `topic_id=3940` (`'Internet of Things'`) vs. `topic_id=1873` (`'Internet of Things (IoT)'`)
- **CFD**: `topic_id=32` (`'Computational Fluid Dynamics'`) vs. `topic_id=1844` (`'Computational Fluid Dynamics (CFD)'`) vs. `topic_id=2167` (`'CFD and Heat transfer'`)
- **AI**: `topic_id=225` (`'Artificial Intelligence'`) vs. 11 compound `'AI ...'` topics (`topic_id=54` `'AI and Computer Vision'`, `topic_id=256` `'AI and Deep Neural Networks'`, `topic_id=191` `'AI and ML in healthcare'`)

#### Issue 3D: `17` Sentence-Length Topics (`> 65` Chars), `14` Unsplit Colon/Slash Strings, and Typos
Several faculty profiles entered full descriptive sentences or colon-separated lists inside a single `<li>` under `<h2>Research Areas</h2>` (https://www.iitkgp.ac.in/department/AE/faculty/ae-amardip.ghosh, https://www.iitkgp.ac.in/department/AG/faculty/ag-hmachavaram):
- **Sentence-Length Topics (`> 65` chars)**:
  - `topic_id=6`: *"CFD of turbomachinery and multiphase flow in staged combustion cycle based rocket engine"*
  - `topic_id=297`: *"Computer Vision and Machine Learning Applications for Crop Maturity Determination"*
  - `topic_id=2325`: *"Artificial Intelligence for Algorithm or Product or Software Development"*
  - `topic_id=166`: *"Developing indicators for Quality Of Life in residential communities in an Indian context"*
- **Typos in Faculty-Entered Topics**:
  - `topic_id=21`: *"Elasto-plastic buckling and impact analysis of composite **structuress**"*
  - `topic_id=177`: *"Environmental sustainability along **tansportation** corridor of urban areas"*
  - `topic_id=3123`: *"AI and Machine Learning in Mineral **indus**"* (truncated at 40 chars in source ERP)
- **Unsplit Colon / Slash Compound Topics (`14` rows)**:
  - `topic_id=3459`: `"Cyber ethics : security and privacy"`
  - `topic_id=3520`: `"Electric Vehicles: Powertrain & Battery"`
  - `topic_id=3270`: `"Heat Exchanges: PlateFin, Minichannel"`
  - `topic_id=2312`: `"Hydraulic structures: design /operation"`
  - `topic_id=3517`: `"Metabolic Engineering: Synthetic Biology"`

#### Issue 3E: Overly Broad OpenAlex Level-0 Root Concepts vs. Specific Sub-Topics (Parent–Child Imbalance)
OpenAlex tags almost every publication with high-level Level-0/Level-1 discipline concepts that have `0` direct professor links (`prof_cnt = 0`) because professors list specific sub-areas rather than generic disciplines:
- `'Computer science'` (`pub_cnt = 458`, `prof_cnt = 0`)
- `'Engineering'` (`pub_cnt = 328`, `prof_cnt = 0`)
- `'Environmental science'` (`pub_cnt = 304`, `prof_cnt = 0`)
- `'Materials science'` (`pub_cnt = 254`, `prof_cnt = 0`)
- `'Chemistry'` (`pub_cnt = 235`, `prof_cnt = 0`)
- `'Physics'` (`pub_cnt = 230`, `prof_cnt = 0`)
- `'Biology'` (`pub_cnt = 199`, `prof_cnt = 0`)
- `'Mathematics'` (`pub_cnt = 185`, `prof_cnt = 0`)
- Plus noisy OpenAlex Wikipedia-disambiguation labels such as `'Object (grammar)'` and `'Pattern recognition (psychology)'`.

---

### 3.3 Proposed Normalized 3-Tier Topic Taxonomy (Without Modifying Existing Records)

To bridge the gap between broad OpenAlex concepts, faculty-declared research areas, and student search queries (`"NLP"`, `"Generative AI"`, `"Robotics"`, `"VLSI"`, `"Climate Change"`), we propose introducing a **non-destructive 3-Tier Canonical Topic Taxonomy** (`Domain` $\rightarrow$ `Area` $\rightarrow$ `Canonical Topic` + `Aliases/Synonyms`):

| Tier 1: Broad Domain (Level 0) | Tier 2: Research Area (Level 1) | Tier 3: Canonical Topic (Level 2) | Mapped Raw Topic Aliases / Variants in DB |
| :--- | :--- | :--- | :--- |
| **Computer Science & Artificial Intelligence** | **Artificial Intelligence & Machine Learning** | `Machine Learning` | `Machine Learning`, `Machine learning`, `ML`, `AI and ML in healthcare`, `Statistical Machine Learning` |
| **Computer Science & Artificial Intelligence** | **Natural Language Processing & LLMs** | `Natural Language Processing` | `NLP`, `Natural Language Processing`, `Natural language processing`, `Computational Linguistics`, `Advanced NLU` |
| **Computer Science & Artificial Intelligence** | **Computer Vision & Image Processing** | `Computer Vision` | `Computer Vision`, `Computer vision`, `Image Processing`, `Object detection`, `AI and Computer Vision` |
| **Computer Science & Artificial Intelligence** | **Cyber-Physical Systems & IoT** | `Internet of Things` | `IOT`, `Internet of Things`, `Internet of Things (IoT)`, `Intelligent Internet of Things (IoT)` |
| **Computer Science & Artificial Intelligence** | **Cyber-Physical Systems & IoT** | `Cyber-Physical Systems` | `Cyber physical systems`, `cyberphysical systems`, `Embedded system`, `Embedded systems` |
| **Computer Science & Artificial Intelligence** | **Human–Computer Interaction** | `Human-Computer Interaction` | `Human Computer Interaction`, `Human–computer interaction`, `HCI` |
| **Electrical, Electronics & Computing Systems** | **VLSI & Microelectronics** | `VLSI Design & Embedded Systems` | `VLSI`, `VLSI Architecture Design`, `VLSI Signal Processing`, `VLSI and Embedded Systems` |
| **Electrical, Electronics & Computing Systems** | **Control, Power & Electric Mobility** | `Electric Vehicles` | `Electric vehicle`, `Electric vehicles`, `Electric Vehicles: Powertrain & Battery` |
| **Mechanical, Aerospace & Ocean Engineering** | **Fluid & Thermal Sciences** | `Computational Fluid Dynamics` | `CFD`, `Computational Fluid Dynamics`, `Computational Fluid Dynamics (CFD)`, `CFD and Heat transfer` |
| **Mechanical, Aerospace & Ocean Engineering** | **Solid Mechanics & Structures** | `Fluid-Structure Interaction` | `Fluid structure interaction`, `Fluid–structure interaction` |
| **Materials, Chemical & Metallurgical Engg.** | **Nanotechnology & Advanced Materials** | `Nanomaterials & Nanocomposites` | `Nanomaterials`, `Nano materials`, `Functionally graded material`, `Functionally graded materials` |
| **Biosciences, Medical & Healthcare** | **Biomedical Engineering & Diagnostics** | `Biosensors & Bioelectronics` | `Biosensor`, `Biosensors`, `Bio mechanics`, `Biomechanics` |
| **Earth, Agriculture, Water & Sustainability** | **Geomatics & Hydrology** | `GIS & Remote Sensing` | `Geographic information system`, `GIS & Remote Sensing in Water Resources`, `GIS and MCDA`, `Base flow`, `Baseflow` |

#### Recommended Schema / Normalization Strategy for Phase 2 (Awaiting Approval):
1. **Non-Destructive Canonical Mapping**:
   - Add `canonical_name`, `parent_topic_id` (or `domain_category`), and `is_generic_root` columns to `research_topics` (or a `topic_aliases` mapping table) so raw extracted strings are preserved for provenance while queries normalize synonyms (`NLP` $\rightarrow$ `Natural Language Processing`, `IOT` $\rightarrow$ `Internet of Things`, `biosensors` $\rightarrow$ `Biosensor`, `fluid–structure interaction` $\rightarrow$ `Fluid-Structure Interaction`).
2. **Strip OpenAlex Disambiguation Suffixes & Down-Weight Level-0 Concepts**:
   - Strip parenthetical Wikipedia disambiguation suffixes from OpenAlex concepts (`"Object (grammar)"` $\rightarrow$ exclude; `"Pattern recognition (psychology)"` $\rightarrow$ `"Pattern Recognition"`).
   - Mark the ~15 Level-0 root discipline concepts (`Computer science`, `Engineering`, `Chemistry`, `Physics`, `Biology`, `Mathematics`) as `is_generic_root = True` so they are down-weighted during Phase 2 professor-topic matching and do not cause every professor in an engineering department to match generic `"Engineering"` queries equally.
3. **Decompose Compound / Sentence-Length Faculty Topics**:
   - Split compound faculty topics containing `"and"`, `":"`, `"/"`, or `"Applications in"` into atomic canonical topics while keeping the original phrase in `Professor.research_interests` for full-text semantic embedding.

### 3.4 Potential Impact on Future Semantic Search (Phase 2)
- Without synonym/acronym normalization (`NLP` $\leftrightarrow$ `Natural Language Processing`, `IOT` $\leftrightarrow$ `Internet of Things`, `CFD` $\leftrightarrow$ `Computational Fluid Dynamics`) and singular/plural unification, **hybrid keyword + metadata filtering** in Phase 2 will miss professors who used the acronym while the student searched the full phrase (or vice versa), since only `2.4%` (`160 / 6,553`) of raw topic strings currently overlap between `professor_topics` and `publication_topics`.
- Without down-weighting OpenAlex Level-0 root concepts (`Computer science`, `Engineering`), topic-based relevance scoring will artificially boost professors with higher paper counts regardless of sub-field specificity.
