"""Add role/organization to student_projects and location to student_experiences.

Revision ID: 0005_student_profile_detail_cols
Revises: 0004_student_full_name_nullable
Create Date: 2026-11-22 21:35:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0005_student_profile_detail_cols"
down_revision: Union[str, None] = "0004_student_full_name_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    project_cols = {c["name"] for c in inspector.get_columns("student_projects")}
    with op.batch_alter_table("student_projects") as batch_op:
        if "role" not in project_cols:
            batch_op.add_column(sa.Column("role", sa.String(length=150), nullable=True))
        if "organization" not in project_cols:
            batch_op.add_column(sa.Column("organization", sa.String(length=255), nullable=True))

    experience_cols = {c["name"] for c in inspector.get_columns("student_experiences")}
    with op.batch_alter_table("student_experiences") as batch_op:
        if "location" not in experience_cols:
            batch_op.add_column(sa.Column("location", sa.String(length=150), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    experience_cols = {c["name"] for c in inspector.get_columns("student_experiences")}
    with op.batch_alter_table("student_experiences") as batch_op:
        if "location" in experience_cols:
            batch_op.drop_column("location")

    project_cols = {c["name"] for c in inspector.get_columns("student_projects")}
    with op.batch_alter_table("student_projects") as batch_op:
        if "organization" in project_cols:
            batch_op.drop_column("organization")
        if "role" in project_cols:
            batch_op.drop_column("role")
