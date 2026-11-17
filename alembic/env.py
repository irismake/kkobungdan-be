from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from alembic.ddl.mysql import MySQLImpl
from sqlalchemy import Column, MetaData, PrimaryKeyConstraint, String, Table
from sqlalchemy import engine_from_config, event, pool

from app.core.config import settings
from app.core.database import Base

# Import models so Base.metadata is populated for autogenerate.
from app.models import (  # noqa: F401
    chat,
    dispute_evidence,
    dispute_survey,
    mission,
    notification,
    outbox,
    offer,
    proposal,
    refund,
    settlement,
    terms,
    user,
)


config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# MySQL `lock_wait_timeout` 기본값은 31536000초(365일)라, 메타데이터 락을 기다리는 DDL이
# 에러 없이 사실상 영원히 멈춰 있는다. 2026-08-27 staging 배포가 7행짜리 테이블에 컬럼을
# 추가하다 2시간 11분 매달린 원인이다(구 앱이 뜬 채로 마이그레이션이 도는 배포 순서 탓에
# 앱 커넥션이 락을 쥐고 있었다). 락 대기는 짧게 끊고 명확한 에러로 실패시킨다.
# `innodb_lock_wait_timeout`(행 락, 기본 50초)은 MDL에 적용되지 않아 이 상황을 구제하지 못한다.
LOCK_WAIT_TIMEOUT_SECONDS = int(os.getenv("MIGRATION_LOCK_WAIT_TIMEOUT_SECONDS", "60"))


def mysql_version_table_impl(
    self,
    *,
    version_table: str,
    version_table_schema: str | None,
    version_table_pk: bool,
    **kw,
) -> Table:
    """Use staging-compatible width for descriptive Alembic revision IDs."""
    _ = self, kw
    version_table_object = Table(
        version_table,
        MetaData(),
        Column("version_num", String(255), nullable=False),
        schema=version_table_schema,
    )
    if version_table_pk:
        version_table_object.append_constraint(
            PrimaryKeyConstraint("version_num", name=f"{version_table}_pkc")
        )

    return version_table_object


MySQLImpl.version_table_impl = mysql_version_table_impl


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # 커넥션이 열리는 시점에 DBAPI 커서로 직접 건다. `Connection.exec_driver_sql()`로 걸면
    # SQLAlchemy 2.x가 암묵적 트랜잭션을 시작하고, 그 위에서 alembic의 `begin_transaction()`이
    # 중첩되면서 마이그레이션 결과가 커밋되지 않는다(`alembic_version` UPDATE가 유실된다).
    # 락 획득 대기만 제한하므로, 락을 잡은 뒤 실제 DDL이 오래 걸리는 것은 자르지 않는다.
    if connectable.dialect.name == "mysql":

        @event.listens_for(connectable, "connect")
        def set_lock_wait_timeout(dbapi_connection, connection_record) -> None:
            _ = connection_record
            with dbapi_connection.cursor() as cursor:
                cursor.execute(f"SET SESSION lock_wait_timeout = {LOCK_WAIT_TIMEOUT_SECONDS}")

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
