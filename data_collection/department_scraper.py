import logging
import time
from pathlib import Path
from typing import Dict, List, Tuple
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from backend.database.models import University, Department, DataSource, VerificationStatus
from data_processing.cleaning import clean_text, normalize_url

logger = logging.getLogger(__name__)

IIT_KGP_NAME = "Indian Institute of Technology Kharagpur"
IIT_KGP_ACADEMICS_URL = "https://www.iitkgp.ac.in/navpage/academics"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AcademicResearchBot/1.0"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


class DepartmentScraper:
    def __init__(self, timeout: int = 35):
        self.timeout = timeout
        self.headers = {"User-Agent": DEFAULT_USER_AGENT}
        self.cache_file = RAW_DIR / "academics.html"

    def fetch_departments_html(self, url: str = IIT_KGP_ACADEMICS_URL, max_retries: int = 3) -> str:
        """Fetches the HTML of the academics navigation page with retry and cache fallback."""
        logger.info(f"Fetching departments from {url}")
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, headers=self.headers, timeout=self.timeout)
                if resp.status_code == 200:
                    html = resp.text
                    with open(self.cache_file, "w", encoding="utf-8") as f:
                        f.write(html)
                    return html
            except Exception as e:
                logger.warning(f"Attempt {attempt}/{max_retries} failed to fetch {url}: {e}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)

        if self.cache_file.exists():
            logger.info("Using cached academics HTML due to server timeout")
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return f.read()

        raise requests.exceptions.RequestException(f"Failed to fetch {url} after {max_retries} attempts.")

    def parse_departments(self, html: str) -> List[Dict[str, str]]:
        """Parses department names, codes, academic_unit categories, and URLs from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        departments: List[Dict[str, str]] = []
        seen_codes = set()

        # First map each code to its specific division from accordion items
        code_to_unit: Dict[str, str] = {}
        for item in soup.find_all("div", class_="accordion-item"):
            header = item.find("h2")
            unit_name = clean_text(header.get_text(" ", strip=True)) if header else None
            if not unit_name or unit_name == "Academic Units":
                continue
            for a in item.find_all("a", href=True):
                href = a["href"].strip()
                if "/department/" in href:
                    c = href.rstrip("/").split("/")[-1].upper()
                    if c:
                        code_to_unit[c] = unit_name

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            name = clean_text(a.get_text(strip=True))

            if "/department/" in href and name and name != "Departmental Webpage":
                code = href.rstrip("/").split("/")[-1].upper()
                full_url = normalize_url(href)

                if code and code not in seen_codes and full_url:
                    seen_codes.add(code)
                    academic_unit = code_to_unit.get(code)
                    if not academic_unit:
                        if "School" in name:
                            academic_unit = "Schools (S)"
                        elif "Centre of Excellence" in name or "Center of Excellence" in name:
                            academic_unit = "Centres of Excellence (CoE)"
                        elif "Centre" in name or "Cell" in name:
                            academic_unit = "Centres (C)"
                        elif "Academy" in name:
                            academic_unit = "Academies (A)"
                        else:
                            academic_unit = "Departments (D)"

                    departments.append({
                        "name": name,
                        "code": code,
                        "academic_unit": academic_unit,
                        "official_url": full_url
                    })

        logger.info(f"Parsed {len(departments)} departments from page")
        return departments

    def scrape_and_save(self, db: Session) -> Tuple[int, int]:
        """Scrapes departments and saves or updates them in the database."""
        university = db.query(University).filter(University.name == IIT_KGP_NAME).first()
        if not university:
            university = University(
                name=IIT_KGP_NAME,
                country="India",
                region="West Bengal",
                city="Kharagpur",
                website="https://www.iitkgp.ac.in/"
            )
            db.add(university)
            db.commit()
            db.refresh(university)

        html = self.fetch_departments_html()
        parsed = self.parse_departments(html)

        added_count = 0
        updated_count = 0

        for item in parsed:
            dept = db.query(Department).filter(
                Department.university_id == university.id,
                Department.name == item["name"]
            ).first()

            if not dept:
                dept = db.query(Department).filter(
                    Department.university_id == university.id,
                    Department.code == item["code"]
                ).first()

            if not dept:
                dept = Department(
                    university_id=university.id,
                    name=item["name"],
                    code=item["code"],
                    academic_unit=item.get("academic_unit"),
                    official_url=item["official_url"],
                    collection_status="discovered"
                )
                db.add(dept)
                db.flush()
                added_count += 1

                ds = DataSource(
                    entity_type="department",
                    entity_id=dept.id,
                    source_name="iitkgp_website",
                    source_url=IIT_KGP_ACADEMICS_URL,
                    http_status=200,
                    verification_status=VerificationStatus.VERIFIED.value
                )
                db.add(ds)
            else:
                dept.official_url = item["official_url"]
                dept.code = item["code"]
                if item.get("academic_unit"):
                    dept.academic_unit = item["academic_unit"]
                updated_count += 1

        db.commit()
        logger.info(f"Departments saved: {added_count} added, {updated_count} updated")
        return added_count, updated_count
