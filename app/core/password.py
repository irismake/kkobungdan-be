"""Password hashing helpers.

passlib 1.7.4는 설치된 bcrypt 5.x와 호환되지 않아(`__about__` 제거) 직접 bcrypt를 쓴다.
"""

from __future__ import annotations

import bcrypt


#: bcrypt는 72바이트를 넘는 입력을 거부한다. 초과분은 잘라서 넘긴다.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_encode(password), password_hash.encode())
    except ValueError:
        # 해시 형식이 깨진 경우. 검증 실패로 처리한다.
        return False


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:MAX_PASSWORD_BYTES]


__all__ = ["hash_password", "verify_password"]
