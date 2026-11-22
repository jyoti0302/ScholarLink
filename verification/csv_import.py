import logging
from pathlib import Path
from typing import Dict, Union
import pandas as pd
from sqlalchemy.orm import Session

from backend.database.models import (
    Professor,
    Publication,
    ProfessorPublication,
    VerificationRecord,
    VerificationStatus
)

logger = logging.getLogger(__name__)

VALID_STATUSES = {s.value for s in VerificationStatus}


class CSVImporter:
    @staticmethod
    def import_reviewed_faculty(
        db: Session,
        csv_file_path: Union[str, Path]
    ) -> Dict[str, int]:
        """
        Reads reviewed faculty CSV, updates verification_status in database,
        and logs a VerificationRecord for auditability.
        """
        path = Path(csv_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Review CSV not found: {path}")

        df = pd.read_csv(path)
        stats = {"updated": 0, "skipped": 0, "errors": 0}

        for _, row in df.iterrows():
            prof_id = row.get("professor_id")
            new_status = str(row.get("new_status", "")).strip().lower()
            raw_notes = row.get("review_notes")
            notes = str(raw_notes).strip() if pd.notna(raw_notes) else None

            if not prof_id or pd.isna(prof_id) or new_status not in VALID_STATUSES:
                stats["skipped"] += 1
                continue

            prof = db.query(Professor).filter(Professor.id == int(prof_id)).first()
            if prof:
                if prof.verification_status != new_status:
                    prev_status = prof.verification_status
                    prof.verification_status = new_status
                    vr = VerificationRecord(
                        entity_type="professor",
                        entity_id=prof.id,
                        previous_status=prev_status,
                        new_status=new_status,
                        verified_by="csv_review",
                        evidence_or_notes=notes or "Updated via faculty CSV review import",
                        source_url=prof.source_url or prof.profile_url
                    )
                    db.add(vr)
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
            else:
                stats["errors"] += 1

        db.commit()
        logger.info(f"Imported faculty reviews: {stats}")
        return stats

    @staticmethod
    def import_reviewed_publications(
        db: Session,
        csv_file_path: Union[str, Path]
    ) -> Dict[str, int]:
        """
        Reads reviewed publication links CSV, updates verification_status in database,
        and logs a VerificationRecord for auditability.
        """
        path = Path(csv_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Review CSV not found: {path}")

        df = pd.read_csv(path)
        stats = {"updated": 0, "skipped": 0, "errors": 0}

        for _, row in df.iterrows():
            link_id = row.get("link_id")
            new_status = str(row.get("new_status", "")).strip().lower()
            raw_notes = row.get("review_notes")
            notes = str(raw_notes).strip() if pd.notna(raw_notes) else None

            if not link_id or pd.isna(link_id) or new_status not in VALID_STATUSES:
                stats["skipped"] += 1
                continue

            link = db.query(ProfessorPublication).filter(ProfessorPublication.id == int(link_id)).first()
            if link:
                if link.verification_status != new_status:
                    prev_status = link.verification_status
                    link.verification_status = new_status
                    if new_status == VerificationStatus.VERIFIED.value:
                        link.publication.verification_status = VerificationStatus.VERIFIED.value
                    elif new_status == VerificationStatus.REJECTED.value:
                        # Only mark the publication rejected if no other link still supports it
                        others = [
                            l for l in link.publication.professor_publications
                            if l.id != link.id and l.verification_status != VerificationStatus.REJECTED.value
                        ]
                        if not others:
                            link.publication.verification_status = VerificationStatus.REJECTED.value
                    if link.professor:
                        # has_publications means VERIFIED publication links only
                        link.professor.has_publications = any(
                            l.verification_status == VerificationStatus.VERIFIED.value
                            for l in link.professor.professor_publications
                        )

                    vr = VerificationRecord(
                        entity_type="professor_publication",
                        entity_id=link.id,
                        previous_status=prev_status,
                        new_status=new_status,
                        verified_by="csv_review",
                        evidence_or_notes=notes or link.affiliation_evidence,
                        source_url=link.publication.source_url or link.publication.openalex_id
                    )
                    db.add(vr)
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
            else:
                stats["errors"] += 1

        db.commit()
        logger.info(f"Imported publication reviews: {stats}")
        return stats
