from typing import Optional
from sqlalchemy.orm import Session
from backend.database.models import Professor, Publication
from data_processing.cleaning import normalize_doi, clean_author_name, normalize_url, normalize_email


def find_existing_professor(
    db: Session,
    department_id: int,
    name: str,
    email: Optional[str] = None,
    profile_url: Optional[str] = None
) -> Optional[Professor]:
    """
    Finds an existing professor by official profile_url, institutional email,
    or exact (department_id, name) match.
    Does not merge professors merely because names are similar across different departments.
    """
    norm_url = normalize_url(profile_url)
    if norm_url:
        by_url = db.query(Professor).filter(Professor.profile_url == norm_url).first()
        if by_url:
            return by_url

    norm_email = normalize_email(email)
    if norm_email:
        by_email = db.query(Professor).filter(Professor.email == norm_email).first()
        if by_email:
            return by_email

    cleaned_name = clean_author_name(name)
    if cleaned_name and department_id:
        by_dept_name = db.query(Professor).filter(
            Professor.department_id == department_id,
            Professor.name.ilike(cleaned_name)
        ).first()
        if by_dept_name:
            return by_dept_name

    return None


def find_existing_publication(
    db: Session,
    openalex_id: Optional[str] = None,
    doi: Optional[str] = None
) -> Optional[Publication]:
    """Finds an existing publication by OpenAlex ID or normalized DOI."""
    if openalex_id:
        by_openalex = db.query(Publication).filter(Publication.openalex_id == openalex_id).first()
        if by_openalex:
            return by_openalex

    norm_doi = normalize_doi(doi)
    if norm_doi:
        by_doi = db.query(Publication).filter(Publication.doi == norm_doi).first()
        if by_doi:
            return by_doi

    return None
