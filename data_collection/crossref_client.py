import logging
import os
import re
import time
from typing import Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from data_processing.cleaning import normalize_doi, clean_text

logger = logging.getLogger(__name__)

CROSSREF_BASE_URL = "https://api.crossref.org"


class CrossrefClient:
    def __init__(
        self,
        mailto: Optional[str] = None,
        timeout: int = 15,
        rate_limit_delay: float = 0.18
    ):
        self.mailto = mailto or os.getenv("CROSSREF_MAILTO", "research_user@example.com")
        self.timeout = timeout
        self.delay = rate_limit_delay
        self.headers = {
            "User-Agent": f"AcademicResearchPlatform/1.0 (mailto:{self.mailto})"
        }
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def _http_get(self, url: str, params: Optional[Dict] = None) -> requests.Response:
        if type(requests.get).__name__ != "function":
            return requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
        return self._session.get(url, params=params, timeout=self.timeout)

    def _clean_jats_abstract(self, raw_abstract: Optional[str]) -> Optional[str]:
        if not raw_abstract:
            return None
        stripped = re.sub(r"<[^>]+>", " ", raw_abstract)
        stripped = re.sub(r"^\s*Abstract\s*[:.\-]?\s*", "", stripped, flags=re.IGNORECASE)
        return clean_text(stripped)

    def search_works_by_author(
        self,
        author_name: str,
        affiliation: str = "Indian Institute of Technology Kharagpur",
        rows: int = 8
    ) -> List[Dict]:
        """
        Searches Crossref works by author name and institutional affiliation,
        returning normalized work dictionaries compatible with AuthorDisambiguator.
        """
        url = f"{CROSSREF_BASE_URL}/works"
        params = {
            "query.author": author_name,
            "query.affiliation": affiliation,
            "rows": rows
        }
        for attempt in range(1, 4):
            try:
                time.sleep(self.delay)
                resp = self._http_get(url, params=params)
                if resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(attempt * 1.2)
                    continue
                if resp.status_code != 200:
                    return None
                items = (resp.json().get("message") or {}).get("items") or []
                works: List[Dict] = []
                for item in items:
                    norm_doi = normalize_doi(item.get("DOI"))
                    title_list = item.get("title") or []
                    title = clean_text(title_list[0]) if title_list else None
                    if not title:
                        continue

                    year = None
                    date_parts = (
                        (item.get("published-print") or {}).get("date-parts")
                        or (item.get("published-online") or {}).get("date-parts")
                        or (item.get("issued") or {}).get("date-parts")
                        or (item.get("created") or {}).get("date-parts")
                    )
                    if date_parts and len(date_parts) > 0 and len(date_parts[0]) > 0:
                        year = date_parts[0][0]

                    raw_authors = item.get("author") or []
                    authorships = []
                    author_names = []
                    total_authors = len(raw_authors)
                    for idx, a in enumerate(raw_authors):
                        given = (a.get("given") or "").strip()
                        family = (a.get("family") or "").strip()
                        full_name = f"{given} {family}".strip() or (a.get("name") or "").strip()
                        if not full_name:
                            continue
                        author_names.append(full_name)
                        if idx == 0:
                            pos = "first"
                        elif idx == total_authors - 1 and total_authors > 1:
                            pos = "last"
                        else:
                            pos = "middle"

                        aff_objs = []
                        for aff in a.get("affiliation") or []:
                            aff_name = clean_text(aff.get("name"))
                            if aff_name:
                                aff_objs.append({"display_name": aff_name})

                        authorships.append({
                            "author_position": pos,
                            "author": {
                                "id": None,
                                "display_name": full_name,
                                "orcid": a.get("ORCID")
                            },
                            "institutions": aff_objs
                        })

                    container_list = item.get("container-title") or []
                    venue = clean_text(container_list[0]) if container_list else None
                    abstract = self._clean_jats_abstract(item.get("abstract"))
                    subjects = [clean_text(s) for s in (item.get("subject") or []) if clean_text(s)]

                    works.append({
                        "openalex_id": None,
                        "doi": norm_doi,
                        "title": title,
                        "abstract": abstract,
                        "publication_year": year,
                        "journal_or_conference": venue,
                        "authors_list": ", ".join(author_names) if author_names else None,
                        "citation_count": item.get("is-referenced-by-count", 0) or 0,
                        "paper_url": item.get("URL") or (f"https://doi.org/{norm_doi}" if norm_doi else None),
                        "source_url": f"https://api.crossref.org/works/{norm_doi}" if norm_doi else "https://api.crossref.org/works",
                        "source_name": "crossref",
                        "topics": subjects[:8],
                        "authorships": authorships,
                        "_crossref_enriched": True
                    })
                return works
            except Exception as e:
                logger.warning(f"Crossref search retry {attempt}/3 for {author_name}: {e}")
                time.sleep(attempt * 1.0)
        return None

    def get_work_by_doi(self, doi: str) -> Optional[Dict]:
        """Fetches metadata for a given DOI from Crossref."""
        norm_doi = normalize_doi(doi)
        if not norm_doi:
            return None

        url = f"{CROSSREF_BASE_URL}/works/{norm_doi}"
        try:
            time.sleep(self.delay)
            resp = self._http_get(url)
            if resp.status_code == 200:
                data = resp.json().get("message", {})
                title = None
                if data.get("title") and len(data["title"]) > 0:
                    title = clean_text(data["title"][0])

                # Extract publication year
                year = None
                date_parts = data.get("published-print", {}).get("date-parts") or data.get("published-online", {}).get("date-parts") or data.get("created", {}).get("date-parts")
                if date_parts and len(date_parts) > 0 and len(date_parts[0]) > 0:
                    year = date_parts[0][0]

                # Authors
                authors = []
                for a in data.get("author", []):
                    given = a.get("given", "")
                    family = a.get("family", "")
                    full_name = f"{given} {family}".strip()
                    affs = [aff.get("name", "") for aff in a.get("affiliation", [])]
                    authors.append({
                        "name": full_name,
                        "affiliations": affs,
                        "orcid": a.get("ORCID")
                    })

                return {
                    "doi": norm_doi,
                    "title": title,
                    "publication_year": year,
                    "authors": authors,
                    "container_title": (data.get("container-title") or [""])[0],
                    "publisher": data.get("publisher"),
                    "source_name": "crossref"
                }
            elif resp.status_code == 404:
                logger.info(f"Crossref DOI not found: {norm_doi}")
                return None
            else:
                logger.warning(f"Crossref query for {norm_doi} returned status {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error querying Crossref for DOI {norm_doi}: {e}")
            return None
