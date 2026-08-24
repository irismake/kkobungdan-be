"""Link every dispute evidence row to its mission.

Revision ID: 0025_link_disputes_to_missions
Revises: 0024_add_user_admin_columns
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0025_link_disputes_to_missions"
down_revision = "0024_add_user_admin_columns"
branch_labels = None
depends_on = None


INDEX_NAME = "idx_dispute_evidences_mission_id"
FOREIGN_KEY_NAME = "fk_dispute_evidences_mission_id"


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind)
    if "mission_id" not in columns:
        op.add_column("dispute_evidences", sa.Column("mission_id", sa.BigInteger(), nullable=True))

    bind.execute(
        sa.text(
            """
            UPDATE dispute_evidences de
            JOIN missions m ON m.offer_id = de.offer_id
            SET de.mission_id = m.id
            WHERE de.mission_id IS NULL
            """
        )
    )
    missing_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM dispute_evidences WHERE mission_id IS NULL")
    ).scalar_one()
    if missing_count:
        raise RuntimeError(
            f"dispute_evidences has {missing_count} row(s) without a mission; repair staging data first"
        )

    columns = _columns(bind)
    if columns["mission_id"]["nullable"]:
        op.alter_column(
            "dispute_evidences",
            "mission_id",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
    if INDEX_NAME not in _index_names(bind):
        op.create_index(INDEX_NAME, "dispute_evidences", ["mission_id"])
    if not _has_mission_foreign_key(bind):
        op.create_foreign_key(
            FOREIGN_KEY_NAME,
            "dispute_evidences",
            "missions",
            ["mission_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if FOREIGN_KEY_NAME in _foreign_key_names(bind):
        op.drop_constraint(FOREIGN_KEY_NAME, "dispute_evidences", type_="foreignkey")
    if INDEX_NAME in _index_names(bind):
        op.drop_index(INDEX_NAME, table_name="dispute_evidences")
    if "mission_id" in _columns(bind):
        op.drop_column("dispute_evidences", "mission_id")


def _columns(bind: sa.engine.Connection) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(bind).get_columns("dispute_evidences")}


def _index_names(bind: sa.engine.Connection) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes("dispute_evidences")}


def _foreign_key_names(bind: sa.engine.Connection) -> set[str]:
    return {
        foreign_key["name"]
        for foreign_key in sa.inspect(bind).get_foreign_keys("dispute_evidences")
        if foreign_key["name"]
    }


def _has_mission_foreign_key(bind: sa.engine.Connection) -> bool:
    return any(
        foreign_key.get("constrained_columns") == ["mission_id"]
        and foreign_key.get("referred_table") == "missions"
        for foreign_key in sa.inspect(bind).get_foreign_keys("dispute_evidences")
    )
