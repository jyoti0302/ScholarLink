"""
Stage 6.2: Authenticated Professor-Specific Resume Generation & Export Router
(`backend/api/resume_generation.py`).

Security guarantees:
- Requires `Depends(get_current_student)` (JWT Bearer authentication).
- Loads the student's master profile directly from PostgreSQL using `current_student.id`
  (never trusts student_id or fabricated profile records from the client).
- Loads the professor's research profile directly from PostgreSQL by `professor_id`.
- AI provider credentials (`GEMINI_API_KEY`) remain strictly server-side.
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.api.auth import get_current_student
from backend.api.schemas import (
    TailoredResumeExportRequestSchema,
    TailoredResumeGenerateRequestSchema,
    TailoredResumeGenerateResponseSchema,
)
from backend.api.student_profile import _load_complete_student
from backend.database.connection import get_db
from backend.database.models import (
    Department,
    Professor,
    ProfessorProject,
    ProfessorPublication,
    Student,
)
from backend.services.resume_exporter import export_resume_docx, export_resume_pdf
from backend.services.resume_generator import generate_tailored_resume

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student/applications", tags=["Student Applications - Resumes"])


def _safe_filename(raw: str, ext: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", (raw or "").strip()).strip("_")[:80]
    if not stem:
        stem = "tailored_resume"
    return f"{stem}.{ext}"


def _load_professor_for_tailoring(db: Session, professor_id: int) -> Professor:
    try:
        prof = (
            db.query(Professor)
            .options(
                joinedload(Professor.department).joinedload(Department.university),
                selectinload(Professor.professor_projects).joinedload(ProfessorProject.project),
                selectinload(Professor.professor_publications).joinedload(ProfessorPublication.publication),
            )
            .filter(Professor.id == professor_id)
            .first()
        )
    except SQLAlchemyError as exc:
        logger.exception("Database error loading professor for resume generation: %s", exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc

    if not prof:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor not found.")
    return prof


@router.post("/{professor_id}/resumes/generate", response_model=TailoredResumeGenerateResponseSchema)
def generate_professor_tailored_resume(
    professor_id: int,
    payload: TailoredResumeGenerateRequestSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    student = _load_complete_student(db, current_student.id)
    prof = _load_professor_for_tailoring(db, professor_id)
    return generate_tailored_resume(
        student=student,
        prof=prof,
        dept=prof.department,
        selected=payload.selected_items,
        prefs=payload.preferences,
    )


@router.post("/{professor_id}/resumes/export")
def export_professor_tailored_resume(
    professor_id: int,
    payload: TailoredResumeExportRequestSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    # Verify professor exists and requester is authenticated
    _ = current_student.id
    prof = _load_professor_for_tailoring(db, professor_id)

    base_name = payload.filename or f"{payload.content.title}_{prof.name}"
    if payload.format == "pdf":
        data = export_resume_pdf(payload.content, template=payload.template)
        filename = _safe_filename(base_name, "pdf")
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    data = export_resume_docx(payload.content, template=payload.template)
    filename = _safe_filename(base_name, "docx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
