"""
Verified Professor Contact Information Builder (`backend/api/professor_contact.py`).

Builds structured, verified public contact information for a professor profile
strictly from:
1. Existing PostgreSQL `Professor`, `Department`, and `University` records.
2. Cached official institutional HTML pages already collected in `data/raw/profiles/`
   (matched strictly by the professor's official `profile_url` / `source_url`).

Never fabricates phone numbers, office rooms, addresses, or email addresses.
"""
from functools import lru_cache
import html as html_lib
import os
from pathlib import Path
import re
from typing import Dict, List, Optional

from backend.api.schemas import ProfessorContactInfoSchema, ProfessorContactLinkSchema
from backend.database.models import Department, Professor, University

_DEFAULT_PROFILES_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "profiles"

_CON_BK_RE = re.compile(r'<div[^>]*class=["\'][^"\']*\bcon_bk\b[^"\']*["\'][^>]*>(.*?)</div>', re.I | re.S)
_PS_RIGHT_RE = re.compile(r'<div[^>]*class=["\'][^"\']*\bps_right\b[^"\']*["\'][^>]*>(.*?)</div>', re.I | re.S)
_PHONE_RE = re.compile(r'fa-phone-alt["\'][^>]*>\s*</i>\s*([^<\r\n]+)', re.I)
_ANCHOR_RE = re.compile(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _is_valid_http_url(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = html_lib.unescape(raw).strip()
    if not cleaned:
        return None
    if not re.match(r"^https?://[^\s]+$", cleaned, re.I):
        return None
    # Reject bare placeholder anchors or javascript links
    if cleaned.rstrip("/") in ("http://", "https://"):
        return None
    return cleaned


def _clean_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = html_lib.unescape(raw).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 6 or len(digits) > 20:
        return None
    # Reject obviously placeholder numbers like 000000
    if len(set(digits)) == 1:
        return None
    return cleaned


def parse_cached_faculty_html_contact(html_content: str) -> Dict[str, Optional[str]]:
    """
    Extracts verified office phone, personal webpage, and official bio sketch URL
    from an official IIT Kharagpur faculty profile HTML document.
    """
    result: Dict[str, Optional[str]] = {
        "office_phone": None,
        "personal_webpage": None,
        "bio_sketch_url": None,
    }
    if not html_content:
        return result

    con_match = _CON_BK_RE.search(html_content)
    if con_match:
        phone_match = _PHONE_RE.search(con_match.group(1))
        if phone_match:
            result["office_phone"] = _clean_phone(phone_match.group(1))

    right_match = _PS_RIGHT_RE.search(html_content)
    if right_match:
        right_block = right_match.group(1)
        for href, inner_html in _ANCHOR_RE.findall(right_block):
            label = re.sub(r"\s+", " ", _TAG_RE.sub(" ", html_lib.unescape(inner_html))).strip().lower()
            if "personal webpage" in label and not result["personal_webpage"]:
                result["personal_webpage"] = _is_valid_http_url(href)
            elif "bio sketch" in label and not result["bio_sketch_url"]:
                result["bio_sketch_url"] = _is_valid_http_url(href)

    return result


def _url_to_cached_filename(url: str) -> Optional[str]:
    cleaned = _is_valid_http_url(url)
    if not cleaned:
        return None
    without_scheme = re.sub(r"^https?://", "", cleaned, flags=re.I).rstrip("/")
    safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", without_scheme)
    if not safe_stem:
        return None
    return f"{safe_stem}.html"


@lru_cache(maxsize=1024)
def _read_cached_contact_by_path(file_path: str, mtime_ns: int) -> Dict[str, Optional[str]]:
    _ = mtime_ns  # part of cache key for invalidation if file changes
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {"office_phone": None, "personal_webpage": None, "bio_sketch_url": None}
    return parse_cached_faculty_html_contact(content)


def load_cached_faculty_contact(
    profile_url: Optional[str],
    source_url: Optional[str] = None,
    profiles_dir: Optional[Path] = None,
) -> Dict[str, Optional[str]]:
    base_dir = profiles_dir or _DEFAULT_PROFILES_DIR
    if not base_dir.is_dir():
        return {"office_phone": None, "personal_webpage": None, "bio_sketch_url": None}

    for candidate_url in (profile_url, source_url):
        if not candidate_url:
            continue
        filename = _url_to_cached_filename(candidate_url)
        if not filename:
            continue
        candidate_path = (base_dir / filename).resolve()
        # Prevent path traversal outside profiles_dir
        try:
            candidate_path.relative_to(base_dir.resolve())
        except ValueError:
            continue
        if candidate_path.is_file():
            try:
                stat = os.stat(candidate_path)
                return _read_cached_contact_by_path(str(candidate_path), stat.st_mtime_ns)
            except OSError:
                continue

    return {"office_phone": None, "personal_webpage": None, "bio_sketch_url": None}


def build_professor_contact_info(
    prof: Professor,
    dept: Optional[Department],
    univ: Optional[University],
    profiles_dir: Optional[Path] = None,
) -> ProfessorContactInfoSchema:
    """
    Assembles verified contact details for `GET /professors/{professor_id}/profile`.
    """
    profile_url = _is_valid_http_url(prof.profile_url)
    source_url = _is_valid_http_url(prof.source_url) or profile_url
    department_url = _is_valid_http_url(dept.official_url if dept else None)

    cached = load_cached_faculty_contact(
        profile_url=profile_url,
        source_url=source_url,
        profiles_dir=profiles_dir,
    )

    research_group_website = _is_valid_http_url(prof.research_group)
    personal_webpage = cached.get("personal_webpage")
    bio_sketch_url = cached.get("bio_sketch_url")
    office_phone = cached.get("office_phone")

    # Institutional department address from existing verified DB records only
    address_parts: List[str] = []
    if dept and dept.name and dept.name.strip():
        address_parts.append(dept.name.strip())
    if univ and univ.name and univ.name.strip():
        address_parts.append(univ.name.strip())
    if univ and univ.city and univ.city.strip():
        if not address_parts or univ.city.strip().lower() not in address_parts[-1].lower():
            address_parts.append(univ.city.strip())
    if univ and univ.country and univ.country.strip():
        address_parts.append(univ.country.strip())
    department_address = ", ".join(address_parts) if address_parts else None

    # Deduplicated verified public academic links
    academic_links: List[ProfessorContactLinkSchema] = []
    seen_urls = set()

    def _add_link(label: str, url: Optional[str], src: Optional[str]) -> None:
        valid = _is_valid_http_url(url)
        if not valid:
            return
        norm = valid.rstrip("/").lower()
        if norm in seen_urls:
            return
        seen_urls.add(norm)
        academic_links.append(ProfessorContactLinkSchema(label=label, url=valid, source_url=src))

    if personal_webpage:
        _add_link("Personal Webpage", personal_webpage, profile_url or source_url)
    if bio_sketch_url:
        _add_link("Official Bio Sketch (PDF)", bio_sketch_url, profile_url or source_url)
    if prof.orcid and prof.orcid.strip():
        orcid_val = prof.orcid.strip()
        orcid_url = orcid_val if orcid_val.lower().startswith("http") else f"https://orcid.org/{orcid_val}"
        _add_link("ORCID Profile", orcid_url, orcid_url)
    if prof.irins_id and prof.irins_id.strip():
        irins_val = prof.irins_id.strip()
        irins_url = irins_val if irins_val.lower().startswith("http") else f"https://iitkgp.irins.org/profile/{irins_val}"
        _add_link("IRINS Profile", irins_url, irins_url)
    if prof.openalex_author_id and prof.openalex_author_id.strip():
        oa_val = prof.openalex_author_id.strip()
        oa_url = oa_val if oa_val.lower().startswith("http") else f"https://openalex.org/{oa_val}"
        _add_link("OpenAlex Author Profile", oa_url, oa_url)

    email = (prof.email or "").strip() or None

    return ProfessorContactInfoSchema(
        email=email,
        office_phone=office_phone,
        office_room=None,  # Never fabricated; populated only if a verified room source exists
        department_address=department_address,
        department_office_contact=None,
        department_url=department_url,
        research_group_website=research_group_website,
        personal_webpage=personal_webpage,
        bio_sketch_url=bio_sketch_url,
        profile_url=profile_url,
        academic_links=academic_links,
        source_url=source_url,
    )
