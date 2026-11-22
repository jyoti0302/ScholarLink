from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from backend.database.models import Professor, Publication, ProfessorPublication, VerificationStatus


class ReviewQueue:
    @staticmethod
    def get_pending_professors(
        db: Session,
        status: str = VerificationStatus.PENDING.value,
        limit: int = 100,
        offset: int = 0
    ) -> List[Professor]:
        """Retrieves professors by verification status."""
        return (
            db.query(Professor)
            .filter(Professor.verification_status == status)
            .order_by(Professor.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_pending_publications(
        db: Session,
        status: str = VerificationStatus.PENDING.value,
        limit: int = 100,
        offset: int = 0
    ) -> List[Publication]:
        """Retrieves publications by verification status."""
        return (
            db.query(Publication)
            .filter(Publication.verification_status == status)
            .order_by(Publication.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def update_professor_status(
        db: Session,
        professor_id: int,
        new_status: str
    ) -> Optional[Professor]:
        """Updates verification status for a professor."""
        if new_status not in [v.value for v in VerificationStatus]:
            raise ValueError(f"Invalid verification status: {new_status}")

        prof = db.query(Professor).filter(Professor.id == professor_id).first()
        if prof:
            prof.verification_status = new_status
            db.commit()
            db.refresh(prof)
        return prof

    @staticmethod
    def update_publication_status(
        db: Session,
        publication_id: int,
        new_status: str
    ) -> Optional[Publication]:
        """Updates verification status for a publication."""
        if new_status not in [v.value for v in VerificationStatus]:
            raise ValueError(f"Invalid verification status: {new_status}")

        pub = db.query(Publication).filter(Publication.id == publication_id).first()
        if pub:
            pub.verification_status = new_status
            db.commit()
            db.refresh(pub)
        return pub

    @staticmethod
    def get_summary_statistics(db: Session) -> Dict[str, Dict[str, int]]:
        """Returns verification status counts across entities."""
        stats = {
            "professors": {},
            "publications": {},
            "professor_publications": {}
        }
        for st in VerificationStatus:
            stats["professors"][st.value] = db.query(Professor).filter(Professor.verification_status == st.value).count()
            stats["publications"][st.value] = db.query(Publication).filter(Publication.verification_status == st.value).count()
            stats["professor_publications"][st.value] = db.query(ProfessorPublication).filter(ProfessorPublication.verification_status == st.value).count()

        return stats
