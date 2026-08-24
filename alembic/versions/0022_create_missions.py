"""Create missions table and backfill from matched proposals and offers.

Revision ID: 0022_create_missions
Revises: 0021_seed_demo_login_user
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0022_create_missions"
down_revision = "0021_seed_demo_login_user"
branch_labels = None
depends_on = None


# 백필 시 지원 상태에서 미션 상태를 파생한다.
# 레거시 RESOLVED는 판정 결과를 기록하지 않은 채 해결된 건이라 지급 방향을 알 수 없다.
# 관리자가 완료/실패를 다시 판정하도록 DISPUTED로 되돌린다.
OFFER_STATUS_TO_MISSION_STATUS = {
    "ACCEPTED": "STARTED",
    "RUNNER_COMPLETED": "STARTED",
    "ALL_COMPLETED": "COMPLETED",
    "DISPUTED": "DISPUTED",
    "RESOLVED": "DISPUTED",
}


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("proposal_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.BigInteger(), nullable=False),
        sa.Column("orderer_id", sa.String(length=36), nullable=False),
        sa.Column("runner_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("errand_fee", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(length=20), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("settlement_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settlement_paid_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("payout_memo", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", name="uk_missions_proposal_id"),
        sa.UniqueConstraint("offer_id", name="uk_missions_offer_id"),
    )
    op.create_index("idx_missions_status", "missions", ["status"])
    op.create_index("idx_missions_orderer_id", "missions", ["orderer_id"])
    op.create_index("idx_missions_runner_id", "missions", ["runner_id"])

    _backfill(op.get_bind())


def _backfill(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("offers") or not inspector.has_table("proposals"):
        return

    rows = bind.execute(
        sa.text(
            """
            SELECT
                o.id AS offer_id,
                o.proposal_id AS proposal_id,
                o.runner_id AS runner_id,
                o.status AS offer_status,
                o.accepted_at AS accepted_at,
                o.disputed_at AS disputed_at,
                o.updated_at AS updated_at,
                p.orderer_id AS orderer_id,
                p.errand_fee AS errand_fee
            FROM offers o
            JOIN proposals p ON p.id = o.proposal_id
            WHERE o.status IN ('ACCEPTED', 'RUNNER_COMPLETED', 'ALL_COMPLETED', 'DISPUTED', 'RESOLVED')
            """
        )
    ).mappings().all()
    if not rows:
        return

    payload = []
    for row in rows:
        mission_status = OFFER_STATUS_TO_MISSION_STATUS[row["offer_status"]]
        started_at = row["accepted_at"] or row["updated_at"]
        payload.append(
            {
                "proposal_id": row["proposal_id"],
                "offer_id": row["offer_id"],
                "orderer_id": row["orderer_id"],
                "runner_id": row["runner_id"],
                "status": mission_status,
                "errand_fee": row["errand_fee"],
                "started_at": started_at,
                "disputed_at": row["disputed_at"] if mission_status == "DISPUTED" else None,
                "completed_at": row["updated_at"] if mission_status == "COMPLETED" else None,
                "created_at": started_at,
                "updated_at": started_at,
            }
        )

    op.bulk_insert(
        sa.table(
            "missions",
            sa.column("proposal_id", sa.BigInteger()),
            sa.column("offer_id", sa.BigInteger()),
            sa.column("orderer_id", sa.String()),
            sa.column("runner_id", sa.String()),
            sa.column("status", sa.String()),
            sa.column("errand_fee", sa.Integer()),
            sa.column("started_at", sa.DateTime()),
            sa.column("disputed_at", sa.DateTime()),
            sa.column("completed_at", sa.DateTime()),
            sa.column("created_at", sa.DateTime()),
            sa.column("updated_at", sa.DateTime()),
        ),
        payload,
    )


def downgrade() -> None:
    op.drop_index("idx_missions_runner_id", table_name="missions")
    op.drop_index("idx_missions_orderer_id", table_name="missions")
    op.drop_index("idx_missions_status", table_name="missions")
    op.drop_table("missions")
