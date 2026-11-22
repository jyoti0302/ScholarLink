"""Phase 1 + Pre-Phase 2 baseline schema (12 existing tables).

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-11-17 02:13:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.sql import expression

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BASELINE_TABLES = [
    "universities",
    "departments",
    "professors",
    "publications",
    "research_projects",
    "research_topics",
    "professor_publications",
    "professor_projects",
    "professor_topics",
    "publication_topics",
    "data_sources",
    "verification_records",
]


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing = set(insp.get_table_names())

    # If the 12 migrated tables already exist in PostgreSQL, preserve them untouched.
    if "universities" not in existing:
        op.create_table(
            "universities",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("country", sa.String(length=100), nullable=False),
            sa.Column("region", sa.String(length=100), nullable=True),
            sa.Column("city", sa.String(length=100), nullable=False),
            sa.Column("website", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_universities_country", "universities", ["country"], unique=False)
        op.create_index("ix_universities_name", "universities", ["name"], unique=True)

    if "departments" not in existing:
        op.create_table(
            "departments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("university_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=True),
            sa.Column("academic_unit", sa.String(length=150), nullable=True),
            sa.Column("official_url", sa.String(length=500), nullable=True),
            sa.Column("collection_status", sa.String(length=50), nullable=True),
            sa.Column("source_access_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("university_id", "name", name="uq_university_department_name"),
        )
        op.create_index("ix_departments_code", "departments", ["code"], unique=False)
        op.create_index("ix_departments_university_id", "departments", ["university_id"], unique=False)

    if "professors" not in existing:
        op.create_table(
            "professors",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("department_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("designation", sa.String(length=150), nullable=True),
            sa.Column("academic_unit", sa.String(length=150), nullable=True),
            sa.Column("appointment_category", sa.String(length=100), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("educational_background", sa.Text(), nullable=True),
            sa.Column("biography", sa.Text(), nullable=True),
            sa.Column("research_interests", sa.Text(), nullable=True),
            sa.Column("research_group", sa.Text(), nullable=True),
            sa.Column("profile_url", sa.String(length=500), nullable=True),
            sa.Column("source_url", sa.String(length=500), nullable=True),
            sa.Column("verification_status", sa.String(length=50), nullable=False),
            sa.Column("has_publications", sa.Boolean(), server_default=expression.false(), nullable=False),
            sa.Column("has_research_interests", sa.Boolean(), server_default=expression.false(), nullable=False),
            sa.Column("has_biography", sa.Boolean(), server_default=expression.false(), nullable=False),
            sa.Column("has_projects", sa.Boolean(), server_default=expression.false(), nullable=False),
            sa.Column("openalex_author_id", sa.String(length=100), nullable=True),
            sa.Column("orcid", sa.String(length=100), nullable=True),
            sa.Column("irins_id", sa.String(length=100), nullable=True),
            sa.Column("last_updated", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("department_id", "name", name="uq_department_professor_name"),
        )
        op.create_index("ix_professors_department_id", "professors", ["department_id"], unique=False)
        op.create_index("ix_professors_email", "professors", ["email"], unique=False)
        op.create_index("ix_professors_irins_id", "professors", ["irins_id"], unique=False)
        op.create_index("ix_professors_name", "professors", ["name"], unique=False)
        op.create_index("ix_professors_openalex_author_id", "professors", ["openalex_author_id"], unique=False)
        op.create_index("ix_professors_orcid", "professors", ["orcid"], unique=False)
        op.create_index("ix_professors_verification_status", "professors", ["verification_status"], unique=False)

    if "publications" not in existing:
        op.create_table(
            "publications",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("openalex_id", sa.String(length=150), nullable=True),
            sa.Column("doi", sa.String(length=255), nullable=True),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("abstract", sa.Text(), nullable=True),
            sa.Column("publication_year", sa.Integer(), nullable=True),
            sa.Column("journal_or_conference", sa.String(length=500), nullable=True),
            sa.Column("authors_list", sa.Text(), nullable=True),
            sa.Column("paper_url", sa.String(length=500), nullable=True),
            sa.Column("source_url", sa.String(length=500), nullable=True),
            sa.Column("source_name", sa.String(length=100), nullable=False),
            sa.Column("verification_status", sa.String(length=50), nullable=False),
            sa.Column("citation_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_publications_doi", "publications", ["doi"], unique=True)
        op.create_index("ix_publications_openalex_id", "publications", ["openalex_id"], unique=True)
        op.create_index("ix_publications_publication_year", "publications", ["publication_year"], unique=False)
        op.create_index("ix_publications_title", "publications", ["title"], unique=False)
        op.create_index("ix_publications_verification_status", "publications", ["verification_status"], unique=False)

    if "research_projects" not in existing:
        op.create_table(
            "research_projects",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("original_title", sa.Text(), nullable=True),
            sa.Column("project_category", sa.String(length=50), server_default="sponsored_research", nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sponsor", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=True),
            sa.Column("source_url", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_research_projects_project_category", "research_projects", ["project_category"], unique=False)
        op.create_index("ix_research_projects_title", "research_projects", ["title"], unique=False)

    if "research_topics" not in existing:
        op.create_table(
            "research_topics",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("topic_name", sa.String(length=200), nullable=False),
            sa.Column("canonical_topic_name", sa.String(length=255), nullable=True),
            sa.Column("domain_name", sa.String(length=150), nullable=True),
            sa.Column("area_name", sa.String(length=150), nullable=True),
            sa.Column("parent_topic_id", sa.Integer(), nullable=True),
            sa.Column("is_generic_root", sa.Boolean(), server_default=expression.false(), nullable=False),
            sa.Column("is_noisy_artifact", sa.Boolean(), server_default=expression.false(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["parent_topic_id"], ["research_topics.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_research_topics_area_name", "research_topics", ["area_name"], unique=False)
        op.create_index("ix_research_topics_canonical_topic_name", "research_topics", ["canonical_topic_name"], unique=False)
        op.create_index("ix_research_topics_domain_name", "research_topics", ["domain_name"], unique=False)
        op.create_index("ix_research_topics_parent_topic_id", "research_topics", ["parent_topic_id"], unique=False)
        op.create_index("ix_research_topics_topic_name", "research_topics", ["topic_name"], unique=True)

    if "professor_publications" not in existing:
        op.create_table(
            "professor_publications",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("professor_id", sa.Integer(), nullable=False),
            sa.Column("publication_id", sa.Integer(), nullable=False),
            sa.Column("author_position", sa.String(length=50), nullable=True),
            sa.Column("openalex_author_id", sa.String(length=100), nullable=True),
            sa.Column("affiliation_evidence", sa.Text(), nullable=True),
            sa.Column("confidence_score", sa.Float(), nullable=False),
            sa.Column("verification_status", sa.String(length=50), nullable=False),
            sa.ForeignKeyConstraint(["professor_id"], ["professors.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("professor_id", "publication_id", name="uq_professor_publication"),
        )
        op.create_index("ix_professor_publications_professor_id", "professor_publications", ["professor_id"], unique=False)
        op.create_index("ix_professor_publications_publication_id", "professor_publications", ["publication_id"], unique=False)
        op.create_index("ix_professor_publications_verification_status", "professor_publications", ["verification_status"], unique=False)

    if "professor_projects" not in existing:
        op.create_table(
            "professor_projects",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("professor_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=100), nullable=True),
            sa.ForeignKeyConstraint(["professor_id"], ["professors.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("professor_id", "project_id", "role", name="uq_professor_project_role"),
        )
        op.create_index("ix_professor_projects_professor_id", "professor_projects", ["professor_id"], unique=False)
        op.create_index("ix_professor_projects_project_id", "professor_projects", ["project_id"], unique=False)

    if "professor_topics" not in existing:
        op.create_table(
            "professor_topics",
            sa.Column("professor_id", sa.Integer(), nullable=False),
            sa.Column("topic_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["professor_id"], ["professors.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["topic_id"], ["research_topics.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("professor_id", "topic_id"),
        )

    if "publication_topics" not in existing:
        op.create_table(
            "publication_topics",
            sa.Column("publication_id", sa.Integer(), nullable=False),
            sa.Column("topic_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["topic_id"], ["research_topics.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("publication_id", "topic_id"),
        )

    if "data_sources" not in existing:
        op.create_table(
            "data_sources",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("source_name", sa.String(length=100), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("retrieved_at", sa.DateTime(), nullable=False),
            sa.Column("verification_status", sa.String(length=50), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_data_sources_entity_id", "data_sources", ["entity_id"], unique=False)
        op.create_index("ix_data_sources_entity_type", "data_sources", ["entity_type"], unique=False)

    if "verification_records" not in existing:
        op.create_table(
            "verification_records",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("previous_status", sa.String(length=50), nullable=True),
            sa.Column("new_status", sa.String(length=50), nullable=False),
            sa.Column("verified_by", sa.String(length=100), nullable=False),
            sa.Column("evidence_or_notes", sa.Text(), nullable=True),
            sa.Column("source_url", sa.Text(), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_verification_records_entity_id", "verification_records", ["entity_id"], unique=False)
        op.create_index("ix_verification_records_entity_type", "verification_records", ["entity_type"], unique=False)


def downgrade() -> None:
    # Refuses to drop baseline source tables automatically to protect production data.
    pass
