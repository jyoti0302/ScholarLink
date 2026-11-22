import re
from typing import Dict, List, Optional
from urllib.parse import urlparse, urlunparse


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """
    Normalizes a DOI string to lowercase '10.xxxx/yyyy' format.
    Strips 'https://doi.org/', 'http://dx.doi.org/', and whitespace.
    """
    if not doi:
        return None
    cleaned = doi.strip()
    # Strip URL prefixes
    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", cleaned, flags=re.IGNORECASE)
    # Strip leading doi:
    cleaned = re.sub(r"^doi:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip().lower()
    if not cleaned.startswith("10.") or "/" not in cleaned:
        return None
    return cleaned


def normalize_url(url: Optional[str]) -> Optional[str]:
    """Normalizes a URL by stripping trailing slashes and whitespace."""
    if not url:
        return None
    cleaned = url.strip()
    if not cleaned:
        return None
    if cleaned.startswith("/"):
        cleaned = f"https://www.iitkgp.ac.in{cleaned}"
    if not cleaned.startswith(("http://", "https://")):
        return None
    parsed = urlparse(cleaned)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if "iitkgp.ac.in" in netloc and scheme == "http":
        scheme = "https"
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def clean_text(text: Optional[str]) -> Optional[str]:
    """Clean whitespace and unwanted characters from text."""
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    return text.strip() or None


def normalize_department_name(name: Optional[str]) -> Optional[str]:
    """Normalizes department/academic unit name."""
    cleaned = clean_text(name)
    if not cleaned:
        return None
    # Expand common abbreviations consistently if needed, strip excess spaces
    cleaned = re.sub(r"\s*&\s*", " and ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def clean_author_name(name: Optional[str]) -> str:
    """
    Normalizes author name by removing honorifics (Prof., Prof, Dr., Dr, Shri, etc.)
    and stripping excess whitespace.
    """
    if not name:
        return ""
    honorifics = r"^(?:Professor|Doctor|Prof|Dr|Mr|Ms|Mrs|Shri|Smt)(?:\.|\b)\s*"
    cleaned = re.sub(honorifics, "", name.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(honorifics, "", cleaned.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Validates and lowercases email address."""
    if not email:
        return None
    email = email.strip().lower()
    # Handle common obfuscations like [at] or (at) if present
    email = re.sub(r"\s*(\[at\]|\(at\))\s*", "@", email, flags=re.IGNORECASE)
    email = re.sub(r"\s*(\[dot\]|\(dot\))\s*", ".", email, flags=re.IGNORECASE)
    if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        return email
    return None


def clean_designation(designation: Optional[str]) -> Optional[str]:
    """Cleans designation string while preserving official rank."""
    if not designation:
        return None
    cleaned = clean_text(designation)
    if not cleaned:
        return None
    for title in [
        "Assistant Professor Grade-I",
        "Assistant Professor Grade-II",
        "Assistant Professor",
        "Associate Professor",
        "Emeritus Professor",
        "Visiting Professor",
        "Adjunct Professor",
        "Chair Professor",
        "Professor (HAG)",
        "Professor",
        "Lecturer",
    ]:
        if title.lower() in cleaned.lower():
            return title
    return cleaned


def infer_appointment_category(designation: Optional[str], raw_category: Optional[str] = None) -> str:
    """
    Infers the appointment category (Regular Faculty, Emeritus Faculty, Visiting Faculty,
    Adjunct Faculty, Inspire Faculty, Affiliated Faculty) from designation or directory category.
    """
    if raw_category:
        rc = raw_category.lower()
        if "inspire" in rc:
            return "Inspire Faculty"
        if "adjunct" in rc:
            return "Adjunct Faculty"
        if "visiting" in rc:
            return "Visiting Faculty"
        if "emeritus" in rc:
            return "Emeritus Faculty"
        if "former" in rc or "retired" in rc:
            return "Former Faculty"

    if designation:
        dl = designation.lower()
        if "emeritus" in dl:
            return "Emeritus Faculty"
        if "visiting" in dl:
            return "Visiting Faculty"
        if "adjunct" in dl:
            return "Adjunct Faculty"
        if "inspire" in dl:
            return "Inspire Faculty"

    return "Regular Faculty"


def reconstruct_inverted_index(inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
    """
    Reconstructs an abstract from OpenAlex inverted index format:
    {"word": [pos1, pos2], ...} -> "word1 word2 ..."
    """
    if not inverted_index or not isinstance(inverted_index, dict):
        return None

    word_positions = []
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for pos in positions:
                word_positions.append((pos, word))

    if not word_positions:
        return None

    word_positions.sort(key=lambda x: x[0])
    words = [w for _, w in word_positions]
    return clean_text(" ".join(words))
