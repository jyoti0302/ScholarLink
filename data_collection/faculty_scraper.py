import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup, Comment
from sqlalchemy.orm import Session

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from backend.database.models import (
    Department,
    Professor,
    ResearchProject,
    ProfessorProject,
    DataSource,
    VerificationRecord,
    VerificationStatus
)
from data_processing.cleaning import (
    clean_author_name,
    clean_designation,
    clean_text,
    infer_appointment_category,
    normalize_email,
    normalize_url
)
from data_processing.deduplication import find_existing_professor
from data_processing.topic_extraction import get_or_create_topic, extract_topics_from_text

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AcademicResearchBot/1.0"
PEOPLE_AJAX_URL = "https://www.iitkgp.ac.in/Departments/showPeopleFormerStaff"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
DEPT_PEOPLE_CACHE_DIR = RAW_DIR / "dept_people"
PROFILE_CACHE_DIR = RAW_DIR / "profiles"
DEPT_PEOPLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def normalize_project_key(title: Optional[str]) -> str:
    """Returns a normalized alphanumeric key for project deduplication."""
    if not title:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


_GENERIC_PROJECT_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"^(dst\s+)?fist(\s+project)?(\s+level\s*\d+)?$"),
    re.compile(r"^(travel|seed|contingency|equipment|research|institutional)\s+grant$"),
    re.compile(r"^(minor|major)\s+research\s+project$"),
    re.compile(r"^icmr\s+attend$"),
    re.compile(r"^(consultancy|sponsored)\s+project$"),
    re.compile(r"^testing\s+and\s+calibration$"),
    re.compile(r"^cent(re|er)\s+of\s+excellence$"),
)


def is_generic_project_title(title: Optional[str]) -> bool:
    """Returns True for generic/ambiguous project titles that must not be merged globally across professors."""
    norm_key = normalize_project_key(title)
    if not norm_key:
        return True
    tokens = norm_key.split()
    if len(tokens) <= 3 and len(norm_key) < 35:
        return True
    return any(pat.match(norm_key) for pat in _GENERIC_PROJECT_PATTERNS)


def make_project_identity_key(
    title: Optional[str],
    sponsor: Optional[str] = None,
    professor_id: Optional[int] = None,
) -> str:
    """
    Builds a conservative deduplication key.
    - Specific descriptive titles share `title:<norm_key>` so genuine collaborations link cleanly.
    - Generic/ambiguous titles are scoped to `(professor_id, sponsor, title)` and never merged globally.
    """
    norm_key = normalize_project_key(title)
    if not norm_key:
        return ""
    if not is_generic_project_title(title):
        return f"title:{norm_key}"
    sponsor_key = normalize_project_key(sponsor)
    prof_part = professor_id if professor_id is not None else "none"
    return f"prof:{prof_part}:sponsor:{sponsor_key}:title:{norm_key}"


def clean_project_title(title: Optional[str]) -> Optional[str]:
    """Cleans a project title and strips trailing punctuation."""
    cleaned = clean_text(title)
    if not cleaned:
        return None
    cleaned = cleaned.rstrip(".:;,- ").strip()
    return cleaned or None


class FacultyScraper:
    def __init__(self, timeout: int = 30, delay: float = 0.05):
        self.timeout = timeout
        self.delay = delay
        self.headers = {"User-Agent": DEFAULT_USER_AGENT}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        adapter = HTTPAdapter(pool_connections=12, pool_maxsize=12)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_profile_cache_path(self, url: str) -> Path:
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", url.split("//")[-1])[:120]
        return PROFILE_CACHE_DIR / f"{slug}.html"

    def fetch_url(self, url: str, max_retries: int = 2, use_cache: bool = True) -> Optional[str]:
        """Fetches URL with rate limiting, error handling, retries, and optional local caching."""
        cache_file = self.get_profile_cache_path(url)
        if use_cache and cache_file.exists() and cache_file.stat().st_size > 100:
            try:
                return cache_file.read_text(encoding="utf-8")
            except Exception:
                pass

        for attempt in range(1, max_retries + 1):
            try:
                if self.delay > 0:
                    time.sleep(self.delay)
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    html = resp.text
                    html_compact = re.sub(r'src="data:image/[^"]+"', 'src=""', html)
                    try:
                        cache_file.write_text(html_compact, encoding="utf-8")
                    except Exception:
                        pass
                    return html_compact
                else:
                    logger.warning(f"Failed to fetch {url}: status {resp.status_code}")
                    return None
            except Exception as e:
                logger.warning(f"Error fetching {url} (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(attempt * 1.0)
        return None

    def fetch_department_directory_ajax(
        self,
        dept_code: str,
        category: str = "faculty",
        use_cache: bool = True,
        max_retries: int = 2
    ) -> Tuple[Optional[str], int, Optional[str]]:
        """
        Queries IIT Kharagpur's official department people AJAX endpoint:
        POST https://www.iitkgp.ac.in/Departments/showPeopleFormerStaff
        Returns (html_message, http_status, error_message).
        """
        cache_file = DEPT_PEOPLE_CACHE_DIR / f"{dept_code}_{category}.html"
        if use_cache and cache_file.exists():
            try:
                return cache_file.read_text(encoding="utf-8"), 200, None
            except Exception:
                pass

        for attempt in range(1, max_retries + 1):
            try:
                if self.delay > 0:
                    time.sleep(self.delay)
                resp = self.session.post(
                    PEOPLE_AJAX_URL,
                    data={
                        "show_people_former_staff": category,
                        "dept_code": dept_code,
                        "head": ""
                    },
                    timeout=self.timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data.get("message", "") or ""
                    msg_clean = re.sub(r'src="data:image/[^"]+"', 'src=""', msg)
                    try:
                        cache_file.write_text(msg_clean, encoding="utf-8")
                    except Exception:
                        pass
                    return msg_clean, 200, None
                else:
                    err = f"HTTP {resp.status_code}"
                    logger.warning(f"AJAX directory for {dept_code} ({category}) returned {err}")
                    return None, resp.status_code, err
            except Exception as e:
                logger.warning(f"AJAX error for {dept_code} ({category}) attempt {attempt}/{max_retries}: {e}")
                if attempt < max_retries:
                    time.sleep(attempt * 1.5)
                else:
                    return None, 0, str(e)
        return None, 0, "Max retries exceeded"

    def parse_directory_cards(self, html: str, dept_code: str, category: str = "faculty") -> List[Dict]:
        """
        Parses faculty cards returned by showPeopleFormerStaff AJAX endpoint.
        Extracts name, educational_background, designation, appointment_category,
        email, and profile_url.
        """
        if not html or not html.strip():
            return []

        soup = BeautifulSoup(html, "html.parser")
        candidates: List[Dict] = []
        seen_urls: Set[str] = set()

        for a in soup.find_all("a", href=True):
            href = normalize_url(a["href"])
            if not href or "/faculty/" not in href:
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            name_span = a.find("span", class_="hndg")
            raw_name = name_span.get_text(" ", strip=True) if name_span else a.get_text(" ", strip=True)
            cleaned_name = clean_author_name(raw_name)
            if not cleaned_name:
                continue

            education = None
            designation = None
            email = None

            tx22_spans = a.find_all("span", class_="tx22")
            for sp in tx22_spans:
                txt = clean_text(sp.get_text(" ", strip=True))
                if not txt:
                    continue
                if "@" in txt:
                    m = re.search(r"([a-zA-Z0-9_.\-]+@[a-zA-Z0-9_.\-]+)", txt)
                    if m:
                        email = normalize_email(m.group(1))
                elif sp.find("i") and any(
                    k in txt.lower() for k in ["professor", "lecturer", "faculty", "chair", "fellow"]
                ):
                    designation = clean_designation(txt)
                elif not sp.find("i") and not education and not re.match(r"^[\d\s+\-]+$", txt):
                    education = txt

            if not email:
                full_txt = a.get_text(" ", strip=True)
                m = re.search(r"([a-zA-Z0-9_.\-]+@[a-zA-Z0-9_.\-]+)", full_txt)
                if m:
                    email = normalize_email(m.group(1))

            appointment_cat = infer_appointment_category(designation, raw_category=category)

            url_dept_code = dept_code
            m_dept = re.search(r"/department/([A-Za-z0-9]+)/faculty/", href)
            if m_dept:
                url_dept_code = m_dept.group(1).upper()

            candidates.append({
                "name": cleaned_name,
                "designation": designation or "Faculty Member",
                "appointment_category": appointment_cat,
                "educational_background": education,
                "email": email,
                "profile_url": href,
                "source_url": f"https://www.iitkgp.ac.in/department/{dept_code}",
                "url_dept_code": url_dept_code,
                "biography": None,
                "research_interests": None,
                "research_group": None,
                "topics": [],
                "projects": []
            })

        return candidates

    def discover_department_faculty_urls(self, dept_code: str, max_research_areas: Optional[int] = None) -> Set[str]:
        """
        Discovers faculty profile URLs for a given department code by exploring
        the department page and its research area links.
        """
        faculty_urls: Set[str] = set()
        dept_url = f"https://www.iitkgp.ac.in/department/{dept_code}"
        html = self.fetch_url(dept_url)
        if not html:
            return faculty_urls

        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = normalize_url(a["href"])
            if href and "/faculty/" in href:
                faculty_urls.add(href)

        ra_links = []
        for a in soup.find_all("a", href=True):
            href = normalize_url(a["href"])
            if href and f"/research-area/{dept_code.lower()}/" in href.lower():
                if href not in ra_links:
                    ra_links.append(href)

        logger.info(f"Department {dept_code}: found {len(ra_links)} research areas")
        if max_research_areas is not None:
            ra_links = ra_links[:max_research_areas]

        for ra_url in ra_links:
            ra_html = self.fetch_url(ra_url)
            if not ra_html:
                continue
            ra_soup = BeautifulSoup(ra_html, "html.parser")
            for a in ra_soup.find_all("a", href=True):
                href = normalize_url(a["href"])
                if href and "/faculty/" in href:
                    faculty_urls.add(href)

        return faculty_urls

    def parse_faculty_profile(self, url: str, html: str) -> Optional[Dict]:
        """
        Parses a faculty profile page to extract:
        - name
        - designation
        - appointment_category
        - educational_background
        - department
        - email
        - biography (from div#research_statement or explicit Bio Sketch paragraph)
        - research_interests & topics
        - research_group (Personal Webpage / lab URL)
        - projects (Principal Investigator / Co-Principal Investigator projects with separated sponsor descriptions)
        """
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Check if profile page returned "Data not found."
        h2_texts = [clean_text(h.get_text(" ", strip=True)) or "" for h in soup.find_all("h2")]
        if any("data not found" in t.lower() for t in h2_texts):
            logger.info(f"Profile URL {url} returned 'Data not found.' — skipping.")
            return None

        h1_tags = [clean_text(h.get_text(" ", strip=True)) for h in soup.find_all("h1") if clean_text(h.get_text(" ", strip=True))]
        raw_name = None
        dept_name_from_page = None

        if len(h1_tags) >= 2:
            dept_name_from_page = h1_tags[0]
            raw_name = h1_tags[1]
        elif len(h1_tags) == 1:
            single_h1 = h1_tags[0]
            if any(k in single_h1.lower() for k in ["department", "centre", "center", "school", "academy", "engineering", "sciences"]):
                return None
            raw_name = single_h1
        else:
            return None

        cleaned_name = clean_author_name(raw_name)
        if not cleaned_name:
            return None

        designation = None
        email = None
        education = None
        research_group = None
        bio_parts = []

        # Extract research statement tab if available
        rs_div = soup.find("div", id="research_statement")
        if rs_div:
            rs_text = clean_text(rs_div.get_text(" ", strip=True))
            if rs_text and "no record found" not in rs_text.lower() and len(rs_text) > 15:
                bio_parts.append(rs_text)

        # Exclude PhD student sections when scanning top-level paragraphs
        student_div_ids = {"group_members", "alumni_members"}

        for p in soup.find_all("p"):
            if p.find_parent("div", id=lambda x: x in student_div_ids):
                continue
            text = clean_text(p.get_text(" ", strip=True))
            if not text:
                continue

            if not designation and any(
                d in text for d in ["Professor", "Assistant Professor", "Associate Professor", "Lecturer", "Emeritus"]
            ):
                if len(text) < 60:
                    designation = clean_designation(text)

            if not education and any(deg in text for deg in ["Ph.D", "PhD", "M.Tech", "M.S.", "B.Tech", "D.Sc", "FNAE"]):
                if len(text) < 120 and "Bio Sketch" not in text:
                    education = text

            if "@" in text and not email:
                m = re.search(r"([a-zA-Z0-9_.\-]+@[a-zA-Z0-9_.\-]+)", text)
                if m and "contact.iic" not in m.group(1):
                    email = normalize_email(m.group(1))

            if text.startswith("Bio Sketch:") and len(text) > 15 and text not in bio_parts:
                bio_parts.append(text)

        if not email:
            for a in soup.find_all("a", href=True):
                if "mailto:" in a["href"]:
                    potential_email = a["href"].replace("mailto:", "").strip()
                    if "@" in potential_email and "contact.iic" not in potential_email:
                        email = normalize_email(potential_email)
                        break

        # Personal Webpage / Lab link
        invalid_webpages = {"#", "javascript:;", "http://.", "http://a", "http://none", "http://nil", "http://------"}
        for a in soup.find_all("a", href=True):
            txt = clean_text(a.get_text(" ", strip=True)) or ""
            if "personal webpage" in txt.lower():
                href = a["href"].strip()
                if href and href.lower() not in invalid_webpages and not href.lower().endswith("/none") and len(href) > 10:
                    research_group = href
                    break

        # Extract official research interests and areas
        areas: List[str] = []
        for h2 in soup.find_all("h2"):
            if "research area" in (h2.get_text(" ", strip=True) or "").lower():
                ul = h2.find_next("ul")
                if ul:
                    for li in ul.find_all("li"):
                        li_txt = clean_text(li.get_text(" ", strip=True))
                        if li_txt and len(li_txt) < 120 and li_txt not in areas:
                            areas.append(li_txt)

        for a in soup.find_all("a", href=True):
            if "/research-area/" in a["href"]:
                area_text = clean_text(a.get_text(" ", strip=True))
                if area_text and area_text not in areas:
                    areas.append(area_text)

        for el in soup.find_all(["p", "div", "li"]):
            if el.get("id") in student_div_ids or el.find_parent("div", id=lambda x: x in student_div_ids):
                continue
            t = el.get_text(" ", strip=True)
            if t.startswith("Area of Research:"):
                val = t.replace("Area of Research:", "").strip()
                for part in val.split(","):
                    p_clean = clean_text(part)
                    if p_clean and p_clean not in areas:
                        areas.append(p_clean)

        # Extract Research Projects (from div#current_projects and div#compleated_project)
        projects: List[Dict[str, Optional[str]]] = []
        seen_proj_keys_in_profile: Set[Tuple[str, str]] = set()

        for proj_div_id, proj_status in [("current_projects", "current"), ("compleated_project", "completed")]:
            proj_div = soup.find("div", id=proj_div_id)
            if not proj_div:
                continue

            for ul in proj_div.find_all("ul"):
                # Determine role from HTML comment inside ul or preceding h4
                role_txt = "Principal Investigator"
                prev_h4 = ul.find_previous_sibling("h4")
                if prev_h4:
                    h4_text = clean_text(prev_h4.get_text(" ", strip=True)) or ""
                    if "co-principal" in h4_text.lower():
                        role_txt = "Co-Principal Investigator"
                    elif "principal" in h4_text.lower():
                        role_txt = "Principal Investigator"

                for comment in ul.find_all(string=lambda text: isinstance(text, Comment)):
                    c_lower = comment.lower()
                    if "co-principal investigator" in c_lower:
                        role_txt = "Co-Principal Investigator"
                        break
                    elif "principal investigator" in c_lower:
                        role_txt = "Principal Investigator"
                        break

                for li in ul.find_all("li"):
                    # Direct text nodes of this <li> (excludes nested <li> and <b> sponsor tags)
                    direct_text = clean_project_title(
                        "".join(
                            t for t in li.find_all(string=True, recursive=False)
                            if not isinstance(t, Comment)
                        )
                    )
                    if not direct_text or len(direct_text) <= 5:
                        continue
                    low_direct = direct_text.lower()
                    if any(
                        skip_kw in low_direct
                        for skip_kw in ["principal investigator", "no record", "completed projects", "personal webpage"]
                    ):
                        continue

                    # Extract sponsor / funding agency from direct <b> or <strong> tag if present
                    b_tag = li.find(["b", "strong"], recursive=False)
                    sponsor_txt = clean_text(b_tag.get_text(" ", strip=True)) if b_tag else None
                    description = f"Sponsor: {sponsor_txt}" if sponsor_txt else None

                    norm_key = normalize_project_key(direct_text)
                    if not norm_key or (norm_key, role_txt) in seen_proj_keys_in_profile:
                        continue
                    seen_proj_keys_in_profile.add((norm_key, role_txt))

                    projects.append({
                        "title": direct_text,
                        "description": description,
                        "role": role_txt,
                        "status": proj_status
                    })

        biography = " ".join(bio_parts) if bio_parts else None
        norm_profile_url = normalize_url(url)
        url_dept_code = None
        if norm_profile_url:
            m_dept = re.search(r"/department/([A-Za-z0-9]+)/faculty/", norm_profile_url)
            if m_dept:
                url_dept_code = m_dept.group(1).upper()

        return {
            "name": cleaned_name,
            "designation": designation or "Faculty Member",
            "appointment_category": infer_appointment_category(designation),
            "educational_background": education,
            "email": email,
            "biography": biography,
            "research_interests": ", ".join(areas) if areas else None,
            "research_group": research_group,
            "profile_url": norm_profile_url or url,
            "source_url": norm_profile_url or url,
            "dept_name_from_page": dept_name_from_page,
            "url_dept_code": url_dept_code,
            "topics": areas,
            "projects": projects
        }

    def upsert_professor_candidate(
        self,
        db: Session,
        default_department: Department,
        parsed: Dict,
        code_to_dept: Optional[Dict[str, Department]] = None,
        project_key_cache: Optional[Dict[str, ResearchProject]] = None
    ) -> Tuple[Professor, bool]:
        """
        Inserts or updates a Professor record and associated topics/projects/sources.
        Returns (professor, is_newly_added).
        """
        target_dept = default_department
        url_dept_code = parsed.get("url_dept_code")
        if url_dept_code and code_to_dept and url_dept_code in code_to_dept:
            target_dept = code_to_dept[url_dept_code]

        existing = find_existing_professor(
            db=db,
            department_id=target_dept.id,
            name=parsed["name"],
            email=parsed.get("email"),
            profile_url=parsed.get("profile_url")
        )

        is_new = False
        if not existing:
            prof = Professor(
                department_id=target_dept.id,
                name=parsed["name"],
                designation=parsed.get("designation") or "Faculty Member",
                academic_unit=target_dept.academic_unit,
                appointment_category=parsed.get("appointment_category") or "Regular Faculty",
                educational_background=parsed.get("educational_background"),
                email=parsed.get("email"),
                biography=parsed.get("biography"),
                research_interests=parsed.get("research_interests"),
                research_group=parsed.get("research_group"),
                profile_url=parsed.get("profile_url"),
                source_url=parsed.get("source_url"),
                verification_status=VerificationStatus.PENDING.value,
                has_biography=bool(parsed.get("biography")),
                has_research_interests=bool(parsed.get("research_interests")),
                has_projects=bool(parsed.get("projects")),
                has_publications=False
            )
            db.add(prof)
            db.flush()
            is_new = True

            ds = DataSource(
                entity_type="professor",
                entity_id=prof.id,
                source_name="iitkgp_website",
                source_url=parsed.get("source_url") or parsed.get("profile_url") or "",
                http_status=200,
                verification_status=VerificationStatus.PENDING.value
            )
            db.add(ds)
        else:
            prof = existing
            if not prof.academic_unit and target_dept.academic_unit:
                prof.academic_unit = target_dept.academic_unit
            if parsed.get("email") and not prof.email:
                prof.email = parsed["email"]
            if parsed.get("designation") and (not prof.designation or prof.designation == "Faculty Member"):
                prof.designation = parsed["designation"]
            if parsed.get("appointment_category") and not prof.appointment_category:
                prof.appointment_category = parsed["appointment_category"]
            if parsed.get("educational_background") and not prof.educational_background:
                prof.educational_background = parsed["educational_background"]
            if parsed.get("biography") and (not prof.biography or "Personal Webpage" in prof.biography):
                prof.biography = parsed["biography"]
            if parsed.get("research_interests") and not prof.research_interests:
                prof.research_interests = parsed["research_interests"]
            if parsed.get("research_group") and not prof.research_group:
                prof.research_group = parsed["research_group"]
            if parsed.get("profile_url") and not prof.profile_url:
                prof.profile_url = parsed["profile_url"]

            prof.last_updated = datetime.now(timezone.utc)
            prof.has_biography = bool(prof.biography and "Personal Webpage" not in prof.biography)
            prof.has_research_interests = bool(prof.research_interests)

        # Associate topics
        for topic_name in parsed.get("topics", []):
            topic = get_or_create_topic(db, topic_name)
            if topic and topic not in prof.topics:
                prof.topics.append(topic)

        # Associate projects with normalized deduplication
        if project_key_cache is None:
            project_key_cache = {}
            for p in db.query(ResearchProject).all():
                if not p.title:
                    continue
                if not is_generic_project_title(p.title):
                    k = make_project_identity_key(p.title)
                    if k:
                        project_key_cache[k] = p
                else:
                    for pp in p.professor_projects:
                        k = make_project_identity_key(p.title, p.sponsor, professor_id=pp.professor_id)
                        if k:
                            project_key_cache[k] = p

        seen_proj_keys = set()
        for proj_data in parsed.get("projects", []):
            title = clean_project_title(proj_data.get("title"))
            role = proj_data.get("role", "Principal Investigator")
            desc = proj_data.get("description")
            sponsor_val = desc.replace("Sponsor: ", "").strip()[:255] if desc and desc.startswith("Sponsor: ") else None
            norm_key = make_project_identity_key(title, sponsor_val, professor_id=prof.id)
            if not title or not norm_key or (norm_key, role) in seen_proj_keys:
                continue
            seen_proj_keys.add((norm_key, role))

            proj = project_key_cache.get(norm_key)
            if not proj:
                proj = ResearchProject(
                    title=title,
                    description=desc,
                    sponsor=sponsor_val,
                    status=proj_data.get("status", "completed"),
                    source_url=parsed.get("profile_url")
                )
                db.add(proj)
                db.flush()
                project_key_cache[norm_key] = proj
            else:
                if desc and not proj.description:
                    proj.description = desc
                elif desc and proj.description and desc not in proj.description:
                    proj.description = f"{proj.description}; {desc}"
                if sponsor_val and not proj.sponsor:
                    proj.sponsor = sponsor_val

            existing_link = db.query(ProfessorProject).filter(
                ProfessorProject.professor_id == prof.id,
                ProfessorProject.project_id == proj.id
            ).first()
            if not existing_link:
                db.add(ProfessorProject(professor_id=prof.id, project_id=proj.id, role=role))
                db.flush()
            elif role == "Principal Investigator" and existing_link.role != "Principal Investigator":
                existing_link.role = role
            prof.has_projects = True

        return prof, is_new

    def validate_and_clean_existing_projects(self, db: Session) -> Dict[str, int]:
        """
        Part 3 validation & deduplication of ResearchProject and ProfessorProject records:
        1. Re-parses cached HTML profiles to separate concatenated <b>Sponsor</b> tags
           from 'current' project titles into ResearchProject.description.
        2. Strips trailing punctuation from project titles.
        3. Merges duplicate ResearchProject rows that share the same normalize_project_key,
           preserving ProfessorProject links and deduplicating role assignments.
        """
        stats = {"titles_cleaned": 0, "descriptions_populated": 0, "duplicate_projects_merged": 0}

        # Build mapping of concatenated (title + sponsor) -> (clean_title, sponsor_desc) from cached profiles
        concat_to_clean: Dict[str, Tuple[str, Optional[str]]] = {}
        for html_file in PROFILE_CACHE_DIR.glob("*.html"):
            try:
                soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
                for div_id in ["current_projects", "compleated_project"]:
                    pdiv = soup.find("div", id=div_id)
                    if not pdiv:
                        continue
                    for li in pdiv.find_all("li"):
                        if li.find("li"):
                            continue
                        b_tag = li.find(["b", "strong"], recursive=False)
                        if b_tag:
                            full_leaf = clean_text(li.get_text(" ", strip=True))
                            direct_title = clean_project_title(
                                "".join(
                                    t for t in li.find_all(string=True, recursive=False)
                                    if not isinstance(t, Comment)
                                )
                            )
                            sponsor_txt = clean_text(b_tag.get_text(" ", strip=True))
                            if full_leaf and direct_title:
                                concat_to_clean[normalize_project_key(full_leaf)] = (
                                    direct_title,
                                    f"Sponsor: {sponsor_txt}" if sponsor_txt else None
                                )
            except Exception:
                pass

        all_projects = db.query(ResearchProject).order_by(ResearchProject.id.asc()).all()
        canonical_by_key: Dict[str, ResearchProject] = {}

        for proj in all_projects:
            raw_key = normalize_project_key(proj.title)
            if raw_key in concat_to_clean:
                clean_t, sponsor_d = concat_to_clean[raw_key]
                if proj.title != clean_t:
                    proj.title = clean_t
                    stats["titles_cleaned"] += 1
                if sponsor_d and not proj.description:
                    proj.description = sponsor_d
                    stats["descriptions_populated"] += 1
            else:
                cleaned_t = clean_project_title(proj.title)
                if cleaned_t and cleaned_t != proj.title:
                    proj.title = cleaned_t
                    stats["titles_cleaned"] += 1

            if proj.description and proj.description.startswith("Sponsor: ") and not proj.sponsor:
                proj.sponsor = proj.description.replace("Sponsor: ", "").strip()[:255]

            norm_key = normalize_project_key(proj.title)
            if not norm_key or is_generic_project_title(proj.title):
                continue

            if norm_key in canonical_by_key:
                canon = canonical_by_key[norm_key]
                if canon.id != proj.id:
                    if proj.description and not canon.description:
                        canon.description = proj.description
                    elif proj.description and canon.description and proj.description not in canon.description:
                        canon.description = f"{canon.description}; {proj.description}"

                    # Re-point professor_projects links from duplicate proj to canon
                    dup_links = db.query(ProfessorProject).filter(ProfessorProject.project_id == proj.id).all()
                    for dl in dup_links:
                        existing_canon_link = db.query(ProfessorProject).filter(
                            ProfessorProject.professor_id == dl.professor_id,
                            ProfessorProject.project_id == canon.id
                        ).first()
                        if not existing_canon_link:
                            dl.project_id = canon.id
                        else:
                            db.delete(dl)
                    db.flush()
                    db.delete(proj)
                    stats["duplicate_projects_merged"] += 1
            else:
                canonical_by_key[norm_key] = proj

        # Also deduplicate any repeated (professor_id, project_id) pairs in professor_projects
        seen_prof_proj = set()
        for pp in db.query(ProfessorProject).order_by(ProfessorProject.id.asc()).all():
            pair = (pp.professor_id, pp.project_id)
            if pair in seen_prof_proj:
                db.delete(pp)
            else:
                seen_prof_proj.add(pair)

        db.commit()
        logger.info(f"Project validation & deduplication complete: {stats}")
        return stats

    def scrape_department_faculty(
        self,
        db: Session,
        department: Department,
        max_research_areas: Optional[int] = None,
        max_faculty: Optional[int] = None,
        enrich_profiles: bool = False
    ) -> Tuple[int, int]:
        """
        Scrapes all faculty for a department using:
        1. Official department people directory AJAX endpoint (showPeopleFormerStaff)
           for 'faculty', 'inspired_faculty', and 'adjunct_faculty'.
        2. Fallback to department page and research area links if directory returns 0.
        3. Optional profile enrichment for biography, research interests, and projects.
        """
        dept_code = (department.code or department.name).upper()
        logger.info(f"Scraping faculty for department [{dept_code}] {department.name}")

        all_depts = db.query(Department).all()
        code_to_dept = {d.code.upper(): d for d in all_depts if d.code}
        project_key_cache = {
            normalize_project_key(p.title): p
            for p in db.query(ResearchProject).all()
            if p.title
        }

        added_count = 0
        updated_count = 0
        discovered_candidates: List[Dict] = []

        ajax_error = None
        html, status_code, err = self.fetch_department_directory_ajax(dept_code, category="faculty")
        if err:
            ajax_error = err
        if html:
            cards = self.parse_directory_cards(html, dept_code=dept_code, category="faculty")
            discovered_candidates.extend(cards)

        if discovered_candidates:
            for cat in ["inspired_faculty", "adjunct_faculty"]:
                html_extra, _, _ = self.fetch_department_directory_ajax(dept_code, category=cat)
                if html_extra:
                    cards_extra = self.parse_directory_cards(html_extra, dept_code=dept_code, category=cat)
                    discovered_candidates.extend(cards_extra)

        if not discovered_candidates and max_research_areas != 0:
            urls = self.discover_department_faculty_urls(dept_code, max_research_areas=max_research_areas)
            if max_faculty:
                urls = set(list(urls)[:max_faculty])
            for url in urls:
                html = self.fetch_url(url)
                if not html:
                    continue
                parsed = self.parse_faculty_profile(url, html)
                if parsed and parsed.get("name"):
                    discovered_candidates.append(parsed)

        if max_faculty:
            discovered_candidates = discovered_candidates[:max_faculty]

        for cand in discovered_candidates:
            if enrich_profiles and cand.get("profile_url") and not cand.get("research_interests"):
                prof_html = self.fetch_url(cand["profile_url"])
                if prof_html:
                    enriched = self.parse_faculty_profile(cand["profile_url"], prof_html)
                    if enriched:
                        for k, v in enriched.items():
                            if v and not cand.get(k):
                                cand[k] = v

            _, is_new = self.upsert_professor_candidate(
                db=db,
                default_department=department,
                parsed=cand,
                code_to_dept=code_to_dept,
                project_key_cache=project_key_cache
            )
            if is_new:
                added_count += 1
            else:
                updated_count += 1

        if ajax_error and not discovered_candidates:
            department.collection_status = "error"
            department.source_access_notes = f"AJAX endpoint error: {ajax_error}"
        elif discovered_candidates:
            department.collection_status = "completed"
            department.source_access_notes = f"Collected {len(discovered_candidates)} faculty entries from official directory"
        else:
            department.collection_status = "completed_empty_roster"
            department.source_access_notes = "HTTP 200 (0 direct faculty listed on central unit roster; interdisciplinary/centre unit)"

        db.commit()
        logger.info(f"Department [{dept_code}]: {added_count} faculty added, {updated_count} updated")
        return added_count, updated_count

    def enrich_existing_professors(
        self,
        db: Session,
        professors: List[Professor],
        max_workers: int = 6,
        batch_size: int = 50
    ) -> int:
        """
        Fetches individual profile pages for a list of professors in parallel batches,
        populates biography, research_interests, topics, educational_background,
        research_group, and research_projects, and records 'iitkgp_profile_page' DataSource provenance.
        """
        all_depts = db.query(Department).all()
        code_to_dept = {d.code.upper(): d for d in all_depts if d.code}
        project_key_cache = {
            normalize_project_key(p.title): p
            for p in db.query(ResearchProject).all()
            if p.title
        }
        # Remove any transient error records from failed network attempts before enriching
        db.query(DataSource).filter(
            DataSource.entity_type == "professor",
            DataSource.source_name == "iitkgp_profile_page",
            DataSource.http_status != 200
        ).delete(synchronize_session=False)
        db.commit()

        existing_profile_sources = {
            r[0] for r in db.query(DataSource.entity_id).filter(
                DataSource.entity_type == "professor",
                DataSource.source_name == "iitkgp_profile_page",
                DataSource.http_status == 200
            ).all()
        }

        enriched_count = 0
        total = len(professors)

        for start_idx in range(0, total, batch_size):
            batch = professors[start_idx:start_idx + batch_size]
            url_to_html: Dict[str, Optional[str]] = {}

            # Fetch HTML pages concurrently using thread pool
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_url = {
                    executor.submit(self.fetch_url, prof.profile_url): prof.profile_url
                    for prof in batch
                    if prof.profile_url
                }
                for future in as_completed(future_to_url):
                    u = future_to_url[future]
                    try:
                        url_to_html[u] = future.result()
                    except Exception as e:
                        logger.warning(f"Error fetching profile {u}: {e}")
                        url_to_html[u] = None

            for prof in batch:
                if not prof.profile_url:
                    continue
                html = url_to_html.get(prof.profile_url)
                if not html:
                    if prof.id not in existing_profile_sources:
                        db.add(DataSource(
                            entity_type="professor",
                            entity_id=prof.id,
                            source_name="iitkgp_profile_page",
                            source_url=prof.profile_url,
                            http_status=404,
                            error_message="Profile page unreachable or empty",
                            verification_status=prof.verification_status
                        ))
                        existing_profile_sources.add(prof.id)
                    continue

                parsed = self.parse_faculty_profile(prof.profile_url, html)
                if not parsed:
                    if prof.id not in existing_profile_sources:
                        db.add(DataSource(
                            entity_type="professor",
                            entity_id=prof.id,
                            source_name="iitkgp_profile_page",
                            source_url=prof.profile_url,
                            http_status=200,
                            error_message="Profile page returned Data not found or non-faculty content",
                            verification_status=prof.verification_status
                        ))
                        existing_profile_sources.add(prof.id)
                    continue

                self.upsert_professor_candidate(
                    db=db,
                    default_department=prof.department,
                    parsed=parsed,
                    code_to_dept=code_to_dept,
                    project_key_cache=project_key_cache
                )
                if prof.id not in existing_profile_sources:
                    db.add(DataSource(
                        entity_type="professor",
                        entity_id=prof.id,
                        source_name="iitkgp_profile_page",
                        source_url=prof.profile_url,
                        http_status=200,
                        verification_status=prof.verification_status
                    ))
                    existing_profile_sources.add(prof.id)
                enriched_count += 1

            db.commit()
            logger.info(
                f"Profile enrichment progress: {min(start_idx + batch_size, total)}/{total} processed "
                f"({enriched_count} enriched)"
            )

        return enriched_count
