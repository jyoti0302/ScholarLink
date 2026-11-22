"""Add Phase 2A derived search and indexing tables.

Revision ID: 0002_phase2a_search_tables
Revises: 0001_baseline
Create Date: 2026-11-17 02:13:30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0002_phase2a_search_tables"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())

    if "search_documents" not in existing:
        op.create_table(
            "search_documents",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("document_id", sa.String(length=64), nullable=False),
            sa.Column("professor_id", sa.Integer(), nullable=True),
            sa.Column("university_id", sa.Integer(), nullable=False),
            sa.Column("department_id", sa.Integer(), nullable=False),
            sa.Column("evidence_type", sa.String(length=50), nullable=False),
            sa.Column("source_table", sa.String(length=50), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("link_id", sa.Integer(), nullable=True),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("chunk_count", sa.Integer(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("text_content", sa.Text(), nullable=False),
            sa.Column("canonical_topics_json", sa.Text(), nullable=False),
            sa.Column("topic_domains_json", sa.Text(), nullable=False),
            sa.Column("topic_areas_json", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False),
            sa.Column("source_url", sa.String(length=500), nullable=True),
            sa.Column("verification_status", sa.String(length=50), nullable=False),
            sa.Column("confidence_score", sa.Float(), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["professor_id"], ["professors.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_search_documents_content_hash", "search_documents", ["content_hash"], unique=False)
        op.create_index("ix_search_documents_department_id", "search_documents", ["department_id"], unique=False)
        op.create_index("ix_search_documents_document_id", "search_documents", ["document_id"], unique=True)
        op.create_index("ix_search_documents_evidence_type", "search_documents", ["evidence_type"], unique=False)
        op.create_index("ix_search_documents_link_id", "search_documents", ["link_id"], unique=False)
        op.create_index("ix_search_documents_professor_id", "search_documents", ["professor_id"], unique=False)
        op.create_index("ix_search_documents_source_id", "search_documents", ["source_id"], unique=False)
        op.create_index("ix_search_documents_university_id", "search_documents", ["university_id"], unique=False)
        op.create_index("ix_search_documents_verification_status", "search_documents", ["verification_status"], unique=False)

    if "index_sync_state" not in existing:
        op.create_table(
            "index_sync_state",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("document_id", sa.String(length=64), nullable=False),
            sa.Column("collection_name", sa.String(length=100), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("embedding_model", sa.String(length=100), nullable=False),
            sa.Column("qdrant_status", sa.String(length=50), nullable=False),
            sa.Column("indexed_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_index_sync_state_collection_name", "index_sync_state", ["collection_name"], unique=False)
        op.create_index("ix_index_sync_state_content_hash", "index_sync_state", ["content_hash"], unique=False)
        op.create_index("ix_index_sync_state_document_id", "index_sync_state", ["document_id"], unique=True)
        op.create_index("ix_index_sync_state_qdrant_status", "index_sync_state", ["qdrant_status"], unique=False)

    if "embedding_cache" not in existing:
        op.create_table(
            "embedding_cache",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("embedding_model", sa.String(length=100), nullable=False),
            sa.Column("dense_vector_json", sa.Text(), nullable=False),
            sa.Column("sparse_indices_json", sa.Text(), nullable=True),
            sa.Column("sparse_values_json", sa.Text(), nullable=True),
            sa.Column("vector_dim", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("content_hash", "embedding_model", name="uq_embedding_cache_hash_model"),
        )
        op.create_index("ix_embedding_cache_content_hash", "embedding_cache", ["content_hash"], unique=False)
        op.create_index("ix_embedding_cache_embedding_model", "embedding_cache", ["embedding_model"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    if "embedding_cache" in existing:
        op.drop_table("embedding_cache")
    if "index_sync_state" in existing:
        op.drop_table("index_sync_state")
    if "search_documents" in existing:
        op.drop_table("search_documents")
