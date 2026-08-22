"""Seed the production-capable demo login user.

Revision ID: 0021_seed_demo_login_user
Revises: 0020_fix_withdrawal_reason_spelling
Create Date: 2026-08-21
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "0021_seed_demo_login_user"
down_revision = "0020_fix_withdrawal_reason_spelling"
branch_labels = None
depends_on = None


DEMO_LOGIN_USER_ID = "00000000-0000-4000-8000-000000000000"
DEMO_LOGIN_PHONE = "01000000000"
DEMO_LOGIN_NAME = "오더런 데모"


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("users"):
        return

    users = sa.table(
        "users",
        sa.column("id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("phone", sa.String()),
        sa.column("phone_verified_at", sa.DateTime()),
        sa.column("last_login_at", sa.DateTime()),
        sa.column("alarm_enabled", sa.Boolean()),
        sa.column("level", sa.Integer()),
        sa.column("deleted", sa.Boolean()),
        sa.column("deleted_at", sa.DateTime()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    existing_id = bind.execute(
        sa.select(users.c.id).where(users.c.phone == DEMO_LOGIN_PHONE).limit(1)
    ).scalar_one_or_none()
    if existing_id is not None:
        return

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        users,
        [
            {
                "id": DEMO_LOGIN_USER_ID,
                "name": DEMO_LOGIN_NAME,
                "phone": DEMO_LOGIN_PHONE,
                "phone_verified_at": now,
                "last_login_at": None,
                "alarm_enabled": True,
                "level": 0,
                "deleted": False,
                "deleted_at": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("users"):
        return
    bind.execute(
        sa.text("DELETE FROM users WHERE id = :user_id AND phone = :phone"),
        {"user_id": DEMO_LOGIN_USER_ID, "phone": DEMO_LOGIN_PHONE},
    )
