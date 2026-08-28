"""Dedupe user_fcm_tokens and enforce token uniqueness.

Revision ID: 0034_dedupe_fcm_tokens
Revises: 0033_admin_login_lockout
Create Date: 2026-08-27

`user_fcm_tokens`는 `user_id`에만 unique가 걸려 있어, 한 기기 토큰이 여러 유저 row에
동시에 남을 수 있었다(계정을 바꿔가며 로그인). 그 결과 알림 레코드는 정상 유저 앞으로
쌓이는데, 실제 푸시는 그 유저 row가 가리키는(다른 사람의) 기기로 발송돼 "푸시는 왔는데
히스토리에는 없다"는 증상이 생겼다.

`fcm_token`은 VARCHAR(4096)이라 그대로 유니크 인덱스를 걸 수 없어(utf8mb4 인덱스 길이
한도 초과), SHA2 생성 컬럼 `fcm_token_hash`를 추가하고 여기에 유니크 인덱스를 건다.
기존 중복 행은 토큰별로 가장 최근 것만 남기고 정리한다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0034_dedupe_fcm_tokens"
down_revision = "0033_admin_login_lockout"
branch_labels = None
depends_on = None


TABLE = "user_fcm_tokens"
HASH_COLUMN = "fcm_token_hash"
UNIQUE_CONSTRAINT = "uk_user_fcm_tokens_fcm_token_hash"


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        return

    # 토큰별로 가장 최근 updated_at(동률이면 더 큰 id) 1건만 남기고 나머지 삭제.
    # 중복이 없으면 0 rows affected.
    op.execute(
        """
        DELETE t1 FROM user_fcm_tokens t1
        JOIN user_fcm_tokens t2
          ON t1.fcm_token = t2.fcm_token
         AND (t1.updated_at < t2.updated_at
              OR (t1.updated_at = t2.updated_at AND t1.id < t2.id))
        """
    )

    existing = _column_names(bind)
    if HASH_COLUMN not in existing:
        op.execute(
            f"""
            ALTER TABLE {TABLE}
            ADD COLUMN {HASH_COLUMN} CHAR(64)
                GENERATED ALWAYS AS (SHA2(fcm_token, 256)) STORED NOT NULL
            """
        )

    existing_constraints = _unique_constraint_names(bind)
    if UNIQUE_CONSTRAINT not in existing_constraints:
        op.create_unique_constraint(UNIQUE_CONSTRAINT, TABLE, [HASH_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        return

    existing_constraints = _unique_constraint_names(bind)
    if UNIQUE_CONSTRAINT in existing_constraints:
        op.drop_constraint(UNIQUE_CONSTRAINT, TABLE, type_="unique")

    existing = _column_names(bind)
    if HASH_COLUMN in existing:
        op.drop_column(TABLE, HASH_COLUMN)

    # 주의: upgrade에서 삭제한 중복 행은 복구하지 않는다.


def _has_table(bind: sa.engine.Connection) -> bool:
    return sa.inspect(bind).has_table(TABLE)


def _column_names(bind: sa.engine.Connection) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(TABLE)}


def _unique_constraint_names(bind: sa.engine.Connection) -> set[str]:
    inspector = sa.inspect(bind)
    names = {uc["name"] for uc in inspector.get_unique_constraints(TABLE)}
    # MySQL은 unique constraint를 unique index로 구현하므로 index 목록도 함께 본다.
    names |= {ix["name"] for ix in inspector.get_indexes(TABLE) if ix.get("unique")}
    return names
