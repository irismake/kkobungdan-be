"""Create refunds and expose refund lifecycle proposal states.

Revision ID: 0026_create_refunds
Revises: 0025_link_disputes_to_missions
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0026_create_refunds"
down_revision = "0025_link_disputes_to_missions"
branch_labels = None
depends_on = None


OLD_PROPOSAL_STATUSES = (
    "HOLDING",
    "POSTED",
    "OFFERED",
    "MATCHED",
    "ORDER_COMPLETED",
    "ALL_COMPLETED",
    "DISPUTED",
    "RESOLVED",
    "REPORTED",
    "CANCELLED",
)
EXPANDED_PROPOSAL_STATUSES = (
    "HOLDING",
    "POSTED",
    "OFFERED",
    "MATCHED",
    "ORDER_COMPLETED",
    "ALL_COMPLETED",
    "DISPUTED",
    "RESOLVED",
    "REFUND_PENDING",
    "REFUNDED",
    "REPORTED",
    "CANCELLED",
)
PROPOSAL_STATUSES = tuple(status for status in EXPANDED_PROPOSAL_STATUSES if status != "RESOLVED")
OLD_OFFER_STATUSES = (
    "WAITING",
    "ACCEPTED",
    "RUNNER_COMPLETED",
    "ALL_COMPLETED",
    "DISPUTED",
    "RESOLVED",
    "REJECTED",
    "CANCELLED",
)
OFFER_STATUSES = tuple(status for status in OLD_OFFER_STATUSES if status != "RESOLVED")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        _alter_mysql_enum("proposals", EXPANDED_PROPOSAL_STATUSES)

    if not sa.inspect(bind).has_table("refunds"):
        op.create_table(
            "refunds",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("proposal_id", sa.BigInteger(), nullable=False),
            sa.Column("mission_id", sa.BigInteger(), nullable=True),
            sa.Column("orderer_id", sa.String(length=36), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(length=30), nullable=False),
            sa.Column("reason_detail", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("processed_by_admin_id", sa.String(length=36), nullable=True),
            sa.Column("admin_note", sa.String(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("mission_id", name="uk_refunds_mission_id"),
            sa.UniqueConstraint("proposal_id", name="uk_refunds_proposal_id"),
        )
        op.create_index("ix_refunds_orderer_id", "refunds", ["orderer_id"])
        op.create_index("ix_refunds_status", "refunds", ["status"])
        op.create_index("idx_refunds_status_requested", "refunds", ["status", "requested_at", "id"])

    # 기존 미션 환불 처리 내역을 새 정본으로 옮긴다. 분쟁 증빙이 없으면 관리자 직접 취소로 본다.
    op.execute(
        sa.text(
            """
            INSERT INTO refunds (
                proposal_id, mission_id, orderer_id, amount, reason, reason_detail, status,
                requested_at, processed_at, processed_by_admin_id, admin_note, created_at, updated_at
            )
            SELECT
                m.proposal_id,
                m.id,
                m.orderer_id,
                m.errand_fee,
                CASE WHEN EXISTS (
                    SELECT 1 FROM dispute_evidences de WHERE de.mission_id = m.id
                ) THEN 'DISPUTE_FAILED' ELSE 'ADMIN_CANCELLED' END,
                COALESCE(
                    (SELECT de.reason FROM dispute_evidences de
                     WHERE de.mission_id = m.id ORDER BY de.created_at DESC, de.id DESC LIMIT 1),
                    p.admin_note
                ),
                CASE WHEN m.refunded_at IS NOT NULL OR m.status = 'REFUNDED'
                    THEN 'COMPLETED' ELSE 'PENDING' END,
                COALESCE(m.failed_at, m.started_at),
                m.refunded_at,
                m.refunded_by_admin_id,
                m.payout_memo,
                COALESCE(m.failed_at, m.started_at),
                COALESCE(m.refunded_at, m.failed_at, m.started_at)
            FROM missions m
            JOIN proposals p ON p.id = m.proposal_id
            WHERE m.status IN ('FAILED', 'REFUNDED')
              AND NOT EXISTS (SELECT 1 FROM refunds r WHERE r.proposal_id = m.proposal_id)
            """
        )
    )

    # 기존 RESOLVED는 미션 판정 결과를 앱 최종 상태로 드러내도록 변환한다.
    op.execute(
        sa.text(
            """
            UPDATE proposals p
            SET status = CASE
                WHEN EXISTS (SELECT 1 FROM missions m WHERE m.proposal_id = p.id AND m.status = 'REFUNDED')
                    THEN 'REFUNDED'
                WHEN EXISTS (SELECT 1 FROM missions m WHERE m.proposal_id = p.id AND m.status = 'FAILED')
                    THEN 'REFUND_PENDING'
                WHEN EXISTS (SELECT 1 FROM missions m WHERE m.proposal_id = p.id AND m.status IN ('COMPLETED', 'PAID'))
                    THEN 'ALL_COMPLETED'
                WHEN EXISTS (SELECT 1 FROM missions m WHERE m.proposal_id = p.id AND m.status = 'DISPUTED')
                    THEN 'DISPUTED'
                ELSE 'CANCELLED'
            END
            WHERE status IN ('RESOLVED', 'CANCELLED')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE offers o
            SET status = CASE
                WHEN EXISTS (SELECT 1 FROM missions m WHERE m.offer_id = o.id AND m.status IN ('FAILED', 'REFUNDED'))
                    THEN 'CANCELLED'
                WHEN EXISTS (SELECT 1 FROM missions m WHERE m.offer_id = o.id AND m.status IN ('COMPLETED', 'PAID'))
                    THEN 'ALL_COMPLETED'
                WHEN EXISTS (SELECT 1 FROM missions m WHERE m.offer_id = o.id AND m.status = 'DISPUTED')
                    THEN 'DISPUTED'
                ELSE 'CANCELLED'
            END
            WHERE status = 'RESOLVED'
            """
        )
    )

    # 환불 여부는 Refund가 정본이다. Mission은 실행 판정 결과인 FAILED를 유지한다.
    op.execute(sa.text("UPDATE missions SET status = 'FAILED' WHERE status = 'REFUNDED'"))

    mission_columns = _column_names(bind, "missions")
    for column_name in (
        "refund_rejected_by_admin_id",
        "refund_rejected_at",
        "refunded_by_admin_id",
        "refunded_at",
    ):
        if column_name in mission_columns:
            op.drop_column("missions", column_name)

    if bind.dialect.name == "mysql":
        _alter_mysql_enum("proposals", PROPOSAL_STATUSES)
        _alter_mysql_enum("offers", OFFER_STATUSES)


def downgrade() -> None:
    bind = op.get_bind()
    mission_columns = _column_names(bind, "missions")
    legacy_columns = (
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("refund_rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refund_rejected_by_admin_id", sa.String(length=36), nullable=True),
    )
    for column in legacy_columns:
        if column.name not in mission_columns:
            op.add_column("missions", column)

    if bind.dialect.name == "mysql":
        _alter_mysql_enum("proposals", EXPANDED_PROPOSAL_STATUSES)
        _alter_mysql_enum("offers", OLD_OFFER_STATUSES)

    if sa.inspect(bind).has_table("refunds"):
        op.execute(
            sa.text(
                """
                UPDATE missions m
                SET status = 'REFUNDED',
                    refunded_at = (SELECT r.processed_at FROM refunds r WHERE r.mission_id = m.id),
                    refunded_by_admin_id = (
                        SELECT r.processed_by_admin_id FROM refunds r WHERE r.mission_id = m.id
                    )
                WHERE EXISTS (
                    SELECT 1 FROM refunds r
                    WHERE r.mission_id = m.id AND r.status = 'COMPLETED'
                )
                """
            )
        )
    op.execute(
        sa.text(
            """
            UPDATE proposals p
            SET status = CASE
                WHEN EXISTS (SELECT 1 FROM missions m WHERE m.proposal_id = p.id) THEN 'RESOLVED'
                ELSE 'CANCELLED'
            END
            WHERE status IN ('REFUND_PENDING', 'REFUNDED')
            """
        )
    )
    if sa.inspect(bind).has_table("refunds"):
        op.drop_table("refunds")
    if bind.dialect.name == "mysql":
        _alter_mysql_enum("proposals", OLD_PROPOSAL_STATUSES)


def _alter_mysql_enum(table_name: str, statuses: tuple[str, ...]) -> None:
    enum_values = ", ".join(f"'{status}'" for status in statuses)
    op.execute(sa.text(f"ALTER TABLE {table_name} MODIFY status ENUM({enum_values}) NOT NULL"))


def _column_names(bind: sa.engine.Connection, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
