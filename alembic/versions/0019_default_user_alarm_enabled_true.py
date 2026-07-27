"""Default new users to alarm enabled.

Revision ID: 0019_default_user_alarm_enabled_true
Revises: 0018_create_user_withdrawal_reasons
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0019_default_user_alarm_enabled_true"
down_revision = "0018_create_user_withdrawal_reasons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "alarm_enabled" not in columns:
        return

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "alarm_enabled",
            existing_type=sa.Boolean(),
            existing_nullable=True,
            server_default="1",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "alarm_enabled" not in columns:
        return

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "alarm_enabled",
            existing_type=sa.Boolean(),
            existing_nullable=True,
            server_default="0",
        )
