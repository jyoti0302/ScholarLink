import csv
from pathlib import Path
from typing import Optional
import pandas as pd
from sqlalchemy.orm import Session

from backend.database.models import Professor, Publication, ProfessorPublication, Department


class CSVExporter:
    def __init__(self, export_dir: Optional[str] = None):
        if export_dir:
            self.export_dir = Path(export_dir)
        else:
            self.export_dir = Path(__file__).resolve().parent.parent / "data" / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_faculty_candidates(
        self,
        db: Session,
        status_filter: Optional[str] = None,
        filename: str = "faculty_review_queue.csv"
    ) -> Path:
        """
        Exports faculty records needing review to CSV with full source and availability fields.
        """
        query = db.query(Professor).join(Department)
        if status_filter:
            query = query.filter(Professor.verification_status == status_filter)

        professors = query.order_by(Professor.id.asc()).all()

        rows = []
        for p in professors:
            rows.append({
                "professor_id": p.id,
                "name": p.name,
                "department": p.department.name if p.department else "",
                "department_code": p.department.code if p.department else "",
                "academic_unit": p.academic_unit or (p.department.academic_unit if p.department else ""),
                "designation": p.designation or "",
                "appointment_category": p.appointment_category or "Regular Faculty",
                "educational_background": p.educational_background or "",
                "email": p.email or "",
                "profile_url": p.profile_url or "",
                "source_url": p.source_url or "",
                "research_interests": p.research_interests or "",
                "has_publications": bool(p.has_publications),
                "has_research_interests": bool(p.has_research_interests),
                "has_biography": bool(p.has_biography),
                "has_projects": bool(p.has_projects),
                "current_status": p.verification_status,
                "new_status": p.verification_status,
                "review_notes": ""
            })

        df = pd.DataFrame(rows)
        out_path = self.export_dir / filename
        df.to_csv(out_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
        return out_path

    def export_publication_candidates(
        self,
        db: Session,
        status_filter: Optional[str] = None,
        filename: str = "publication_review_queue.csv"
    ) -> Path:
        """
        Exports publication records and professor links to CSV for manual review.
        Includes professor name, department, profile_url, source_url, publication title,
        author list, DOI, affiliation evidence, and matching confidence.
        """
        query = (
            db.query(ProfessorPublication)
            .join(Professor)
            .join(Publication)
        )
        if status_filter:
            query = query.filter(ProfessorPublication.verification_status == status_filter)

        links = query.order_by(ProfessorPublication.id.asc()).all()

        rows = []
        for link in links:
            prof = link.professor
            pub = link.publication
            rows.append({
                "link_id": link.id,
                "professor_id": link.professor_id,
                "professor_name": prof.name if prof else "",
                "department": prof.department.name if (prof and prof.department) else "",
                "profile_url": prof.profile_url if prof else "",
                "source_url": pub.source_url or pub.openalex_id or "",
                "publication_id": link.publication_id,
                "title": pub.title if pub else "",
                "authors_list": pub.authors_list or "",
                "journal_or_conference": pub.journal_or_conference or "",
                "doi": pub.doi or "",
                "publication_year": pub.publication_year or "",
                "author_position": link.author_position or "",
                "confidence_score": link.confidence_score,
                "affiliation_evidence": link.affiliation_evidence or "",
                "current_status": link.verification_status,
                "new_status": link.verification_status,
                "review_notes": ""
            })

        df = pd.DataFrame(rows)
        out_path = self.export_dir / filename
        df.to_csv(out_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
        return out_path
