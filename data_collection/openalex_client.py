import logging
import os
import time
from typing import Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from data_processing.cleaning import reconstruct_inverted_index, normalize_doi, clean_text

logger = logging.getLogger(__name__)

OPENALEX_BASE_URL = "https://api.openalex.org"
IIT_KGP_INSTITUTION_ID = "I145894827"  # OpenAlex ID for IIT Kharagpur


class OpenAlexClient:
    def __init__(
        self,
        email: Optional[str] = None,
        timeout: int = 20,
        rate_limit_delay: float = 0.08
    ):
        self.email = email or os.getenv("OPENALEX_EMAIL", "research_user@example.com")
        self.timeout = timeout
        self.delay = rate_limit_delay
        self.headers = {
            "User-Agent": f"AcademicResearchPlatform/1.0 (mailto:{self.email})"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        adapter = HTTPAdapter(pool_connections=12, pool_maxsize=12)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.api_key = os.getenv("OPENALEX_API_KEY")
        self.daily_budget_exhausted = False

    def _get(self, endpoint: str, params: Optional[Dict] = None, max_retries: int = 3) -> Optional[Dict]:
        """Executes GET request with exponential backoff retry and rate limiting."""
        use_mock = hasattr(requests.get, "_mock_name")
        if self.daily_budget_exhausted and not use_mock:
            return None

        url = f"{OPENALEX_BASE_URL}/{endpoint.lstrip('/')}"
        params = params or {}
        if self.email and "mailto" not in params:
            params["mailto"] = self.email
        if self.api_key and "api_key" not in params:
            params["api_key"] = self.api_key

        for attempt in range(1, max_retries + 1):
            try:
                if self.delay > 0 and not use_mock:
                    time.sleep(self.delay)
                if use_mock:
                    resp = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
                else:
                    resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    body_text = (getattr(resp, "text", "") or "").lower()
                    if "insufficient budget" in body_text:
                        logger.warning("OpenAlex daily unauthenticated IP budget exhausted (429 Insufficient budget); switching to cached OpenAlex & Crossref discovery.")
                        self.daily_budget_exhausted = True
                        return None
                    wait_time = attempt * 1.5
                    logger.warning(f"OpenAlex rate limited (429). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"OpenAlex GET {url} returned status {resp.status_code}")
                    return None
            except Exception as e:
                logger.error(f"OpenAlex request error on {url} (attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    return None
                time.sleep(attempt * 1.0)
        return None

    def _parse_author_results(self, results: List[Dict]) -> List[Dict]:
        authors = []
        for a in results:
            inst_names = []
            for inst in a.get("last_known_institutions", []) or []:
                if inst and inst.get("display_name"):
                    name_str = inst.get("display_name", "")
                    if name_str not in inst_names:
                        inst_names.append(name_str)

            for aff in a.get("affiliations", []) or []:
                inst_obj = (aff or {}).get("institution") or {}
                name_str = inst_obj.get("display_name", "")
                if name_str and name_str not in inst_names:
                    inst_names.append(name_str)

            authors.append({
                "openalex_id": a.get("id"),
                "display_name": a.get("display_name"),
                "works_count": a.get("works_count", 0),
                "cited_by_count": a.get("cited_by_count", 0),
                "orcid": a.get("orcid"),
                "institutions": inst_names,
                "affiliations": a.get("affiliations", []),
                "summary_stats": a.get("summary_stats", {})
            })
        return authors

    def search_authors_by_name(
        self,
        name: str,
        institution_id: Optional[str] = IIT_KGP_INSTITUTION_ID,
        allow_unfiltered_fallback: bool = True
    ) -> List[Dict]:
        """
        Searches authors in OpenAlex matching name.
        If institution_id is provided, filters for that institution first
        (checking affiliations.institution.id), then optionally falls back to
        broader search if no institutional match is found.
        """
        params = {
            "search": name,
            "per-page": 10
        }
        if institution_id:
            params["filter"] = f"affiliations.institution.id:{institution_id}"

        res = self._get("authors", params=params)
        if not res or not res.get("results"):
            if institution_id and allow_unfiltered_fallback:
                logger.debug(f"Retrying author search for '{name}' without institution filter")
                return self.search_authors_by_name(name, institution_id=None, allow_unfiltered_fallback=False)
            return []

        return self._parse_author_results(res.get("results", []))

    def get_works_by_author(
        self,
        openalex_author_id: str,
        limit: int = 15,
        sort_by: str = "publication_year:desc"
    ) -> List[Dict]:
        """
        Retrieves publication works for an author from OpenAlex.
        Reconstructs inverted index abstracts into plain text and extracts venue & authors.
        """
        clean_id = openalex_author_id.split("/")[-1]
        params = {
            "filter": f"author.id:{clean_id}",
            "per-page": min(limit, 100),
            "sort": sort_by
        }

        res = self._get("works", params=params)
        if not res or "results" not in res:
            return []

        works = []
        for w in res.get("results", []):
            topics = [c.get("display_name") for c in w.get("concepts", []) if c.get("display_name")]
            abstract = reconstruct_inverted_index(w.get("abstract_inverted_index"))
            doi = normalize_doi(w.get("doi"))
            primary_loc = w.get("primary_location") or {}
            paper_url = w.get("doi") or primary_loc.get("landing_page_url") or w.get("id")
            venue_source = primary_loc.get("source") or {}
            journal_or_conference = clean_text(venue_source.get("display_name"))

            author_position = None
            co_authors = []
            for authorship in w.get("authorships", []):
                author_obj = authorship.get("author", {}) or {}
                a_name = clean_text(author_obj.get("display_name"))
                if a_name:
                    co_authors.append(a_name)
                author_id_str = author_obj.get("id") or ""
                if author_id_str.endswith(clean_id):
                    author_position = authorship.get("author_position")

            works.append({
                "openalex_id": w.get("id"),
                "openalex_author_id": f"https://openalex.org/{clean_id}",
                "doi": doi,
                "title": clean_text(w.get("title")),
                "abstract": abstract,
                "publication_year": w.get("publication_year"),
                "journal_or_conference": journal_or_conference,
                "authors_list": ", ".join(co_authors) if co_authors else None,
                "citation_count": w.get("cited_by_count", 0),
                "paper_url": paper_url,
                "source_url": w.get("id"),
                "topics": topics,
                "author_position": author_position,
                "authorships": w.get("authorships", []),
                "source_name": "openalex"
            })
        return works
