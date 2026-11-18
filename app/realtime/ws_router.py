"""채팅 실시간 연결 `GET /v1/chat/ws` (CHAT-REQ-015·016).

- `Authorization: Bearer <access token>`으로 인증한다. 없거나 만료·잘못된 토큰이면 close code 4401로 거부한다.
- 받기 전용이다. 서버는 30초마다 `{"type": "ping"}`을 보내고, 토큰 만료 시각이 되면 4401로 닫는다.
- 앱은 4401을 받으면 토큰을 갱신하고 다시 연결한 뒤, 놓친 것을 REST로 복구한다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.core.database import get_db
from app.core.security import verify_token
from app.models.user import User
from app.realtime.hub import chat_hub

router = APIRouter(tags=["채팅"])

#: 토큰이 없거나 만료·잘못됨 (HTTP 401에 대응)
CLOSE_UNAUTHORIZED = 4401
PING_INTERVAL_SECONDS = 30.0


def _authenticate(websocket: WebSocket, db: Session) -> tuple[str, datetime] | None:
    header = websocket.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = verify_token(token, token_type="access")
    except Exception:  # noqa: BLE001 - 만료·위조 모두 같은 거부 코드
        return None
    user_id = payload.get("sub")
    expires_at = payload.get("exp")
    if not user_id or expires_at is None:
        return None
    user = db.query(User.id).filter(User.id == str(user_id), User.deleted.is_(False)).first()
    # 연결이 열려 있는 동안 DB 연결을 잡고 있지 않게 트랜잭션을 끝낸다.
    db.rollback()
    if user is None:
        return None
    return str(user_id), datetime.fromtimestamp(expires_at, tz=timezone.utc)


@router.websocket("/chat/ws")
async def chat_websocket(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    authenticated = _authenticate(websocket, db)
    if authenticated is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    user_id, expires_at = authenticated

    connection = chat_hub.register(user_id, websocket)
    try:
        await websocket.accept()
        while True:
            remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                await websocket.close(code=CLOSE_UNAUTHORIZED)
                return
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=min(PING_INTERVAL_SECONDS, remaining))
            except asyncio.TimeoutError:
                if (expires_at - datetime.now(timezone.utc)).total_seconds() > 0:
                    await connection.send_json({"type": "ping"})
                continue
            if message["type"] == "websocket.disconnect":
                return
    except WebSocketDisconnect:
        return
    finally:
        chat_hub.unregister(connection)
