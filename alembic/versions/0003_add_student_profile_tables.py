"""Add Stage 5.2 student identity and academic profile tables.

Revision ID: 0003_student_profile_tables
Revises: 0002_phase2a_search_tables
Create Date: 2026-11-22 20:33:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0003_student_profile_tables"
down_revision: Union[str, None] = "0002_phase2a_search_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(inspect(bind).get_table_names())

    if "students" not in existing_tables:
        op.create_table(
            "students",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("phone", sa.String(length=50), nullable=True),
            sa.Column("institution", sa.String(length=255), nullable=True),
            sa.Column("department", sa.String(length=255), nullable=True),
            sa.Column("degree_program", sa.String(length=150), nullable=True),
            sa.Column("graduation_year", sa.Integer(), nullable=True),
            sa.Column("current_year_or_semester", sa.String(length=100), nullable=True),
            sa.Column("research_interests_summary", sa.Text(), nullable=True),
            sa.Column("github_url", sa.String(length=500), nullable=True),
            sa.Column("linkedin_url", sa.String(length=500), nullable=True),
            sa.Column("portfolio_url", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email", name="uq_students_email"),
        )
        op.create_index("ix_students_email", "students", ["email"], unique=True)

    if "student_educations" not in existing_tables:
        op.create_table(
            "student_educations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("institution", sa.String(length=255), nullable=False),
            sa.Column("degree", sa.String(length=150), nullable=False),
            sa.Column("department_major", sa.String(length=255), nullable=True),
            sa.Column("start_year", sa.Integer(), nullable=True),
            sa.Column("graduation_year", sa.Integer(), nullable=True),
            sa.Column("cgpa_or_percentage", sa.String(length=50), nullable=True),
            sa.Column("relevant_coursework", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_student_educations_student_id", "student_educations", ["student_id"], unique=False)

    if "student_skills" not in existing_tables:
        op.create_table(
            "student_skills",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("category", sa.String(length=50), nullable=False, server_default="technical"),
            sa.Column("proficiency_level", sa.String(length=50), nullable=True),
            sa.Column("experience_context", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "category IN ('technical', 'research', 'tool', 'language')",
                name="ck_student_skills_category",
            ),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_student_skills_student_id", "student_skills", ["student_id"], unique=False)

    if "student_projects" not in existing_tables:
        op.create_table(
            "student_projects",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("entry_type", sa.String(length=50), nullable=False, server_default="project"),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("problem_statement", sa.Text(), nullable=True),
            sa.Column("methodology", sa.Text(), nullable=True),
            sa.Column("technologies_tools", sa.Text(), nullable=True),
            sa.Column("outcomes_results", sa.Text(), nullable=True),
            sa.Column("start_date", sa.String(length=50), nullable=True),
            sa.Column("end_date", sa.String(length=50), nullable=True),
            sa.Column("project_url", sa.String(length=500), nullable=True),
            sa.Column("github_url", sa.String(length=500), nullable=True),
            sa.Column("associated_skills", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "entry_type IN ('project', 'research_experience')",
                name="ck_student_projects_entry_type",
            ),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_student_projects_student_id", "student_projects", ["student_id"], unique=False)

    if "student_experiences" not in existing_tables:
        op.create_table(
            "student_experiences",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("organization", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=150), nullable=False),
            sa.Column("start_date", sa.String(length=50), nullable=True),
            sa.Column("end_date", sa.String(length=50), nullable=True),
            sa.Column("responsibilities", sa.Text(), nullable=True),
            sa.Column("achievements", sa.Text(), nullable=True),
            sa.Column("technologies_used", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_student_experiences_student_id", "student_experiences", ["student_id"], unique=False)

    if "student_achievements" not in existing_tables:
        op.create_table(
            "student_achievements",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("entry_type", sa.String(length=50), nullable=False, server_default="achievement"),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("issuing_organization", sa.String(length=255), nullable=True),
            sa.Column("date_awarded", sa.String(length=50), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("credential_url", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "entry_type IN ('achievement', 'certification')",
                name="ck_student_achievements_entry_type",
            ),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_student_achievements_student_id", "student_achievements", ["student_id"], unique=False)

    if "student_publications" not in existing_tables:
        op.create_table(
            "student_publications",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("authors", sa.Text(), nullable=True),
            sa.Column("journal_or_conference", sa.String(length=500), nullable=True),
            sa.Column("publication_date", sa.String(length=50), nullable=True),
            sa.Column("doi_or_url", sa.String(length=500), nullable=True),
            sa.Column("abstract", sa.Text(), nullable=True),
            sa.Column("verification_or_source", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_student_publications_student_id", "student_publications", ["student_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(inspect(bind).get_table_names())

    for table_name in (
        "student_publications",
        "student_achievements",
        "student_experiences",
        "student_projects",
        "student_skills",
        "student_educations",
        "students",
    ):
        if table_name in existing_tables:
            op.drop_table(table_name)
