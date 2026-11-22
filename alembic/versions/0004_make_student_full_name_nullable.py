"""Make students.full_name nullable for minimal email+password registration.

Revision ID: 0004_student_full_name_nullable
Revises: 0003_student_profile_tables
Create Date: 2026-11-22 21:21:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_student_full_name_nullable"
down_revision: Union[str, None] = "0003_student_profile_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("students") as batch_op:
        batch_op.alter_column(
            "full_name",
            existing_type=sa.String(length=255),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("students") as batch_op:
        batch_op.alter_column(
            "full_name",
            existing_type=sa.String(length=255),
            nullable=False,
        )
