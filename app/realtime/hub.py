"""사용자별 WebSocket 연결 보관소 (프로세스 메모리, TD-026).

DB를 모른다. 사용자 ID와 이벤트만 받는다. 연결은 이벤트 루프(웹 서버)에 있고, 보내는 쪽(outbox 전달 처리)은
다른 스레드에서 돌기 때문에 `run_coroutine_threadsafe`로 그 연결의 루프에 넘기고 결과를 기다린다.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any

from starlette.websockets import WebSocket

#: 연결 하나에 보내기를 기다리는 최대 시간. 넘기면 전송 오류로 본다.
SEND_TIMEOUT_SECONDS = 2.0


@dataclass(eq=False)
class Connection:
    user_id: str
    websocket: WebSocket
    loop: asyncio.AbstractEventLoop
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send_json(self, event: dict[str, Any]) -> None:
        # 주기 ping과 hub 전송이 겹쳐도 프레임이 섞이지 않게 한 번에 하나만 보낸다.
        async with self.lock:
            await self.websocket.send_json(event)


class RealtimeHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: dict[str, set[Connection]] = {}

    def register(self, user_id: str, websocket: WebSocket) -> Connection:
        """연결을 등록한다. 연결의 이벤트 루프 안에서 부른다."""
        connection = Connection(user_id, websocket, asyncio.get_running_loop())
        with self._lock:
            self._connections.setdefault(user_id, set()).add(connection)
        return connection

    def unregister(self, connection: Connection) -> None:
        with self._lock:
            connections = self._connections.get(connection.user_id)
            if connections is None:
                return
            connections.discard(connection)
            if not connections:
                del self._connections[connection.user_id]

    def is_connected(self, user_id: str) -> bool:
        with self._lock:
            return bool(self._connections.get(user_id))

    def send(self, user_id: str, event: dict[str, Any]) -> int:
        """그 사용자의 모든 연결(기기)에 보낸다. 보낸 연결 수를 돌려주고, 전송 오류는 예외로 던진다.

        이벤트 루프 밖의 스레드에서 부른다(루프 안에서 부르면 결과를 기다리다 멈춘다).
        """
        with self._lock:
            connections = list(self._connections.get(user_id, ()))
        sent = 0
        errors: list[Exception] = []
        for connection in connections:
            future = asyncio.run_coroutine_threadsafe(connection.send_json(event), connection.loop)
            try:
                future.result(timeout=SEND_TIMEOUT_SECONDS)
                sent += 1
            except Exception as exc:  # noqa: BLE001 - 끊긴 연결 하나 때문에 다른 기기 전송을 멈추지 않는다
                future.cancel()
                errors.append(exc)
        if errors and sent == 0:
            raise ConnectionError(f"실시간 전송 실패: {errors[0]!r}")
        return sent


#: 앱 전체에서 쓰는 채팅 hub
chat_hub = RealtimeHub()
