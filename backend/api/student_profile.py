"""
Stage 5.3: Authenticated Student Academic Profile CRUD API (`backend/api/student_profile.py`).

Security & Ownership Guarantees:
- Every endpoint requires `Depends(get_current_student)` (Bearer JWT).
- `student_id` is NEVER accepted from request bodies; POST endpoints assign
  `student_id = current_student.id` exclusively from the verified token.
- Every PUT and DELETE filters by BOTH `Model.id == record_id` and
  `Model.student_id == current_student.id`, returning 404 for missing or
  non-owned records.
- `password_hash` is never serialized in any response.
- `email` is read-only through `/student/profile`.
- Profile completion is recalculated deterministically on the backend after
  every profile mutation and returned as the single source of truth.
"""
import logging
from typing import Type, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from backend.api.auth import get_current_student
from backend.api.schemas import (
    ProfileCompletionItemSchema,
    ProfileCompletionSchema,
    StudentAchievementInputSchema,
    StudentAchievementMutationResponseSchema,
    StudentAchievementSchema,
    StudentCompleteProfileSchema,
    StudentDeleteResponseSchema,
    StudentEducationInputSchema,
    StudentEducationMutationResponseSchema,
    StudentEducationSchema,
    StudentExperienceInputSchema,
    StudentExperienceMutationResponseSchema,
    StudentExperienceSchema,
    StudentPersonalInfoUpdateSchema,
    StudentProjectInputSchema,
    StudentProjectMutationResponseSchema,
    StudentProjectSchema,
    StudentPublicationInputSchema,
    StudentPublicationMutationResponseSchema,
    StudentPublicationSchema,
    StudentSkillInputSchema,
    StudentSkillMutationResponseSchema,
    StudentSkillSchema,
)
from backend.database.connection import get_db
from backend.database.models import (
    Student,
    StudentAchievement,
    StudentEducation,
    StudentExperience,
    StudentProject,
    StudentPublication,
    StudentSkill,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student/profile", tags=["Student Profile"])

TModel = TypeVar("TModel")

_TECHNICAL_SKILL_CATEGORIES = {"technical", "tool", "language"}


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def calculate_profile_completion(student: Student) -> ProfileCompletionSchema:
    """
    Deterministic 100-point student profile completion formula:
      - Full name (15%): students.full_name non-empty
      - Academic affiliation (15%): institution, department, and degree_program all non-empty
      - Education history (15%): >= 1 student_educations record
      - Technical skills (15%): >= 1 student_skills record in ('technical', 'tool', 'language')
      - Research interests & skills (15%): research_interests_summary non-empty OR >= 1 'research' skill
      - Projects or research experience (15%): >= 1 student_projects record
      - Supporting credentials (10%): >= 1 record in experiences, achievements, or publications
    """
    educations = list(student.educations or [])
    skills = list(student.skills or [])
    projects = list(student.projects or [])
    experiences = list(student.experiences or [])
    achievements = list(student.achievements or [])
    publications = list(student.publications or [])

    has_full_name = _non_empty(student.full_name)
    has_affiliation = (
        _non_empty(student.institution)
        and _non_empty(student.department)
        and _non_empty(student.degree_program)
    )
    has_education = len(educations) > 0
    has_technical_skills = any((s.category or "").lower() in _TECHNICAL_SKILL_CATEGORIES for s in skills)
    has_research_profile = _non_empty(student.research_interests_summary) or any(
        (s.category or "").lower() == "research" for s in skills
    )
    has_projects_or_research = len(projects) > 0
    has_supporting_credentials = (len(experiences) + len(achievements) + len(publications)) > 0

    items = [
        ProfileCompletionItemSchema(
            key="full_name",
            label="Full name",
            weight=15,
            completed=has_full_name,
            section="personal",
        ),
        ProfileCompletionItemSchema(
            key="academic_affiliation",
            label="Academic affiliation (institution, department, degree)",
            weight=15,
            completed=has_affiliation,
            section="personal",
        ),
        ProfileCompletionItemSchema(
            key="education",
            label="Education history",
            weight=15,
            completed=has_education,
            section="education",
        ),
        ProfileCompletionItemSchema(
            key="technical_skills",
            label="Technical skills",
            weight=15,
            completed=has_technical_skills,
            section="technical_skills",
        ),
        ProfileCompletionItemSchema(
            key="research_profile",
            label="Research interests or research skills",
            weight=15,
            completed=has_research_profile,
            section="research",
        ),
        ProfileCompletionItemSchema(
            key="projects_or_research",
            label="Projects or research experience",
            weight=15,
            completed=has_projects_or_research,
            section="projects",
        ),
        ProfileCompletionItemSchema(
            key="supporting_credentials",
            label="Experience, achievements, or publications",
            weight=10,
            completed=has_supporting_credentials,
            section="experiences",
        ),
    ]

    percentage = sum(item.weight for item in items if item.completed)
    completed_count = sum(1 for item in items if item.completed)
    return ProfileCompletionSchema(
        percentage=percentage,
        completed_count=completed_count,
        total_count=len(items),
        items=items,
    )


def _load_complete_student(db: Session, student_id: int) -> Student:
    try:
        student = (
            db.query(Student)
            .options(
                selectinload(Student.educations),
                selectinload(Student.skills),
                selectinload(Student.projects),
                selectinload(Student.experiences),
                selectinload(Student.achievements),
                selectinload(Student.publications),
            )
            .filter(Student.id == student_id)
            .first()
        )
    except SQLAlchemyError as exc:
        logger.exception("Database error loading student profile: %s", exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc

    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student profile not found.")
    return student


def _serialize_complete_profile(student: Student) -> StudentCompleteProfileSchema:
    return StudentCompleteProfileSchema(
        id=student.id,
        email=student.email,
        full_name=student.full_name,
        phone=student.phone,
        institution=student.institution,
        department=student.department,
        degree_program=student.degree_program,
        graduation_year=student.graduation_year,
        current_year_or_semester=student.current_year_or_semester,
        research_interests_summary=student.research_interests_summary,
        github_url=student.github_url,
        linkedin_url=student.linkedin_url,
        portfolio_url=student.portfolio_url,
        created_at=student.created_at,
        updated_at=student.updated_at,
        educations=[
            StudentEducationSchema.model_validate(item)
            for item in sorted(student.educations, key=lambda x: x.id, reverse=True)
        ],
        skills=[
            StudentSkillSchema.model_validate(item)
            for item in sorted(student.skills, key=lambda x: x.id, reverse=True)
        ],
        projects=[
            StudentProjectSchema.model_validate(item)
            for item in sorted(student.projects, key=lambda x: x.id, reverse=True)
        ],
        experiences=[
            StudentExperienceSchema.model_validate(item)
            for item in sorted(student.experiences, key=lambda x: x.id, reverse=True)
        ],
        achievements=[
            StudentAchievementSchema.model_validate(item)
            for item in sorted(student.achievements, key=lambda x: x.id, reverse=True)
        ],
        publications=[
            StudentPublicationSchema.model_validate(item)
            for item in sorted(student.publications, key=lambda x: x.id, reverse=True)
        ],
        completion=calculate_profile_completion(student),
    )


def _get_owned_record(
    db: Session,
    model: Type[TModel],
    record_id: int,
    student_id: int,
    label: str,
) -> TModel:
    try:
        record = (
            db.query(model)
            .filter(model.id == record_id, model.student_id == student_id)
            .first()
        )
    except SQLAlchemyError as exc:
        logger.exception("Database error loading %s record: %s", label, exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} record not found.")
    return record


def _commit_and_refresh(db: Session, record: object, label: str) -> None:
    try:
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error saving %s record: %s", label, exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc


def _delete_owned_record(
    db: Session,
    model: Type[TModel],
    record_id: int,
    student_id: int,
    label: str,
) -> StudentDeleteResponseSchema:
    record = _get_owned_record(db, model, record_id, student_id, label)
    try:
        db.delete(record)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error deleting %s record: %s", label, exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc

    refreshed = _load_complete_student(db, student_id)
    return StudentDeleteResponseSchema(
        deleted_id=record_id,
        completion=calculate_profile_completion(refreshed),
    )


# -------------------------------------------------------------------------
# Complete Profile & Personal/Academic Info
# -------------------------------------------------------------------------

@router.get("", response_model=StudentCompleteProfileSchema)
def get_student_profile(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    student = _load_complete_student(db, current_student.id)
    return _serialize_complete_profile(student)


@router.put("", response_model=StudentCompleteProfileSchema)
def update_student_personal_info(
    payload: StudentPersonalInfoUpdateSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(current_student, field_name, value)

    _commit_and_refresh(db, current_student, "student profile")
    student = _load_complete_student(db, current_student.id)
    return _serialize_complete_profile(student)


# -------------------------------------------------------------------------
# Education CRUD
# -------------------------------------------------------------------------

@router.post("/educations", response_model=StudentEducationMutationResponseSchema, status_code=status.HTTP_201_CREATED)
def create_education(
    payload: StudentEducationInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = StudentEducation(student_id=current_student.id, **payload.model_dump())
    db.add(record)
    _commit_and_refresh(db, record, "education")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentEducationMutationResponseSchema(
        item=StudentEducationSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.put("/educations/{education_id}", response_model=StudentEducationMutationResponseSchema)
def update_education(
    education_id: int,
    payload: StudentEducationInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = _get_owned_record(db, StudentEducation, education_id, current_student.id, "Education")
    for field_name, value in payload.model_dump().items():
        setattr(record, field_name, value)
    _commit_and_refresh(db, record, "education")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentEducationMutationResponseSchema(
        item=StudentEducationSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.delete("/educations/{education_id}", response_model=StudentDeleteResponseSchema)
def delete_education(
    education_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    return _delete_owned_record(db, StudentEducation, education_id, current_student.id, "Education")


# -------------------------------------------------------------------------
# Skills CRUD (technical, research, tool, language)
# -------------------------------------------------------------------------

@router.post("/skills", response_model=StudentSkillMutationResponseSchema, status_code=status.HTTP_201_CREATED)
def create_skill(
    payload: StudentSkillInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = StudentSkill(student_id=current_student.id, **payload.model_dump())
    db.add(record)
    _commit_and_refresh(db, record, "skill")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentSkillMutationResponseSchema(
        item=StudentSkillSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.put("/skills/{skill_id}", response_model=StudentSkillMutationResponseSchema)
def update_skill(
    skill_id: int,
    payload: StudentSkillInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = _get_owned_record(db, StudentSkill, skill_id, current_student.id, "Skill")
    for field_name, value in payload.model_dump().items():
        setattr(record, field_name, value)
    _commit_and_refresh(db, record, "skill")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentSkillMutationResponseSchema(
        item=StudentSkillSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.delete("/skills/{skill_id}", response_model=StudentDeleteResponseSchema)
def delete_skill(
    skill_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    return _delete_owned_record(db, StudentSkill, skill_id, current_student.id, "Skill")


# -------------------------------------------------------------------------
# Projects & Research Experience CRUD (entry_type: project | research_experience)
# -------------------------------------------------------------------------

@router.post("/projects", response_model=StudentProjectMutationResponseSchema, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: StudentProjectInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = StudentProject(student_id=current_student.id, **payload.model_dump())
    db.add(record)
    _commit_and_refresh(db, record, "project")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentProjectMutationResponseSchema(
        item=StudentProjectSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.put("/projects/{project_id}", response_model=StudentProjectMutationResponseSchema)
def update_project(
    project_id: int,
    payload: StudentProjectInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = _get_owned_record(db, StudentProject, project_id, current_student.id, "Project")
    for field_name, value in payload.model_dump().items():
        setattr(record, field_name, value)
    _commit_and_refresh(db, record, "project")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentProjectMutationResponseSchema(
        item=StudentProjectSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.delete("/projects/{project_id}", response_model=StudentDeleteResponseSchema)
def delete_project(
    project_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    return _delete_owned_record(db, StudentProject, project_id, current_student.id, "Project")


# -------------------------------------------------------------------------
# Internships & Work Experience CRUD
# -------------------------------------------------------------------------

@router.post("/experiences", response_model=StudentExperienceMutationResponseSchema, status_code=status.HTTP_201_CREATED)
def create_experience(
    payload: StudentExperienceInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = StudentExperience(student_id=current_student.id, **payload.model_dump())
    db.add(record)
    _commit_and_refresh(db, record, "experience")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentExperienceMutationResponseSchema(
        item=StudentExperienceSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.put("/experiences/{experience_id}", response_model=StudentExperienceMutationResponseSchema)
def update_experience(
    experience_id: int,
    payload: StudentExperienceInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = _get_owned_record(db, StudentExperience, experience_id, current_student.id, "Experience")
    for field_name, value in payload.model_dump().items():
        setattr(record, field_name, value)
    _commit_and_refresh(db, record, "experience")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentExperienceMutationResponseSchema(
        item=StudentExperienceSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.delete("/experiences/{experience_id}", response_model=StudentDeleteResponseSchema)
def delete_experience(
    experience_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    return _delete_owned_record(db, StudentExperience, experience_id, current_student.id, "Experience")


# -------------------------------------------------------------------------
# Achievements & Certifications CRUD (entry_type: achievement | certification)
# -------------------------------------------------------------------------

@router.post("/achievements", response_model=StudentAchievementMutationResponseSchema, status_code=status.HTTP_201_CREATED)
def create_achievement(
    payload: StudentAchievementInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = StudentAchievement(student_id=current_student.id, **payload.model_dump())
    db.add(record)
    _commit_and_refresh(db, record, "achievement")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentAchievementMutationResponseSchema(
        item=StudentAchievementSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.put("/achievements/{achievement_id}", response_model=StudentAchievementMutationResponseSchema)
def update_achievement(
    achievement_id: int,
    payload: StudentAchievementInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = _get_owned_record(db, StudentAchievement, achievement_id, current_student.id, "Achievement")
    for field_name, value in payload.model_dump().items():
        setattr(record, field_name, value)
    _commit_and_refresh(db, record, "achievement")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentAchievementMutationResponseSchema(
        item=StudentAchievementSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.delete("/achievements/{achievement_id}", response_model=StudentDeleteResponseSchema)
def delete_achievement(
    achievement_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    return _delete_owned_record(db, StudentAchievement, achievement_id, current_student.id, "Achievement")


# -------------------------------------------------------------------------
# Publications CRUD
# -------------------------------------------------------------------------

@router.post("/publications", response_model=StudentPublicationMutationResponseSchema, status_code=status.HTTP_201_CREATED)
def create_publication(
    payload: StudentPublicationInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = StudentPublication(student_id=current_student.id, **payload.model_dump())
    db.add(record)
    _commit_and_refresh(db, record, "publication")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentPublicationMutationResponseSchema(
        item=StudentPublicationSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.put("/publications/{publication_id}", response_model=StudentPublicationMutationResponseSchema)
def update_publication(
    publication_id: int,
    payload: StudentPublicationInputSchema,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    record = _get_owned_record(db, StudentPublication, publication_id, current_student.id, "Publication")
    for field_name, value in payload.model_dump().items():
        setattr(record, field_name, value)
    _commit_and_refresh(db, record, "publication")
    refreshed = _load_complete_student(db, current_student.id)
    return StudentPublicationMutationResponseSchema(
        item=StudentPublicationSchema.model_validate(record),
        completion=calculate_profile_completion(refreshed),
    )


@router.delete("/publications/{publication_id}", response_model=StudentDeleteResponseSchema)
def delete_publication(
    publication_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    return _delete_owned_record(db, StudentPublication, publication_id, current_student.id, "Publication")
