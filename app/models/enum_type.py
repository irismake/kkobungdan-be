"""Non-native enum column type shared by every status column.

CLAUDE.md: DB 컬럼에는 MySQL native ENUM을 쓰지 않는다. 대신 non-native Enum 매핑으로
DB에는 VARCHAR + 이름 붙인 CHECK 제약으로 저장하고, 애플리케이션에는 Python Enum을 돌려준다.
native ENUM에 종속되지 않으면서 DB 무결성과 타입 안전성을 함께 가져가기 위해서다.
"""

from __future__ import annotations

import enum
from typing import TypeVar

from sqlalchemy import Enum

EnumT = TypeVar("EnumT", bound=enum.Enum)


def check_constraint_name(table_name: str, column_name: str) -> str:
    """CHECK 제약 이름 규약. 마이그레이션도 같은 이름을 써야 한다."""
    return f"ck_{table_name}_{column_name}_values"


def enum_column(enum_class: type[EnumT], length: int, *, table: str, column: str) -> Enum:
    """Map a Python enum onto a VARCHAR(length) column guarded by a named CHECK.

    native_enum=False라 DDL이 MySQL ENUM이 아니라 VARCHAR로 나가고,
    create_constraint=True + name으로 허용값을 이름 붙인 CHECK 제약에 고정한다.
    values_callable을 주어 멤버 이름이 아니라 값을 저장한다.

    상태값을 추가·제거·변경할 때는 이 CHECK 제약을 갱신하는 Alembic 마이그레이션을
    반드시 함께 작성해야 한다. 모델만 바꾸면 DB 제약이 옛 목록에 머문다.
    """
    return Enum(
        enum_class,
        native_enum=False,
        create_constraint=True,
        name=check_constraint_name(table, column),
        values_callable=lambda members: [member.value for member in members],
        length=length,
    )


__all__ = ["check_constraint_name", "enum_column"]
