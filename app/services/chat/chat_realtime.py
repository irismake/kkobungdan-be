"""채팅 실시간 전달 대상 `chat.realtime` (CHAT-REQ-015~017·028, docs/design-docs/chat-architecture.md "실시간").

채팅 이벤트 3종을 받아 받는 사람을 정하고 hub로 WebSocket 이벤트를 보낸다.

| 받은 이벤트 | 보내는 실시간 이벤트 |
|-------------|----------------------|
| `chat.message.created` | 두 참여자에게 `chat.message.created`(보는 사람 기준 문구), 보낸 사람이 아닌 쪽에 `chat.unread.updated` |
| `chat.room.updated` | 두 참여자에게 `chat.room.updated` |
| `chat.read.updated` | 상대방에게 `chat.read.updated`, 읽은 사람에게 `chat.unread.updated` |

다시 시도하지 않는다. 받을 연결이 없거나 전송 오류면 `SKIPPED`로 끝내고, 앱은 재연결 후 REST로 복구한다.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatMessageType, ChatRole, ChatRoom
from app.services.chat.chat_events import MESSAGE_CREATED, READ_UPDATED, ROOM_UPDATED
from app.services.chat.chat_message_service import to_message_response
from app.services.chat.chat_read_service import ChatReadService
from app.services.chat.unread import unread_count
from app.services.outbox.consumers import SkipDelivery
from app.services.outbox.envelope import EventEnvelope
from app.services.outbox.policy import RetryPolicy

#: 재시도 없음 (event-delivery.md 전달 대상별 정책)
CHAT_REALTIME_RETRY_POLICY = RetryPolicy(max_retries=0, backoff=(), expires_after=None)


class Hub(Protocol):
    def is_connected(self, user_id: str) -> bool: ...

    def send(self, user_id: str, event: dict[str, Any]) -> int: ...


class ChatRealtimeConsumer:
    name = "chat.realtime"
    event_types = frozenset({MESSAGE_CREATED, ROOM_UPDATED, READ_UPDATED})
    retry_policy = CHAT_REALTIME_RETRY_POLICY

    def __init__(self, session_factory: Callable[[], Session], hub: Hub) -> None:
        self._session_factory = session_factory
        self._hub = hub

    def handle(self, envelope: EventEnvelope) -> None:
        payload = envelope.payload
        participants = _participants(payload)
        if participants is None:
            with self._session_factory() as db:
                room = db.get(ChatRoom, payload["roomId"])
                if room is None:
                    raise SkipDelivery("room_not_found")
                participants = {ChatRole.ORDERER: room.orderer_id, ChatRole.RUNNER: room.runner_id}

        # 받을 연결이 하나도 없으면 DB를 보지 않고 끝낸다(대부분의 경우).
        connected = {role: user_id for role, user_id in participants.items() if self._hub.is_connected(user_id)}
        if not connected:
            raise SkipDelivery("not_connected")

        outgoing = self._outgoing(envelope, participants, connected)
        sent = 0
        try:
            for user_id, event in outgoing:
                sent += self._hub.send(user_id, event)
        except Exception as exc:  # noqa: BLE001 - 실시간 전달은 다시 시도하지 않는다
            raise SkipDelivery("send_error") from exc
        if sent == 0:
            raise SkipDelivery("not_connected")

    def _outgoing(
        self,
        envelope: EventEnvelope,
        participants: dict[ChatRole, str],
        connected: dict[ChatRole, str],
    ) -> list[tuple[str, dict[str, Any]]]:
        payload = envelope.payload
        room_id = payload["roomId"]
        if envelope.event_type == ROOM_UPDATED:
            event = {"type": ROOM_UPDATED, **_room_state(payload)}
            return [(user_id, event) for user_id in connected.values()]

        with self._session_factory() as db:
            room = db.get(ChatRoom, room_id)
            if room is None:
                raise SkipDelivery("room_not_found")
            if envelope.event_type == MESSAGE_CREATED:
                return self._message_events(db, room, payload, connected)
            return self._read_events(db, room, payload, connected)

    @staticmethod
    def _message_events(db: Session, room: ChatRoom, payload: dict, connected: dict[ChatRole, str]) -> list:
        message = db.get(ChatMessage, payload["messageId"])
        if message is None:
            raise SkipDelivery("message_not_found")
        events = []
        for role, user_id in connected.items():
            body = to_message_response(message, role).model_dump(by_alias=True, mode="json")
            events.append((user_id, {"type": MESSAGE_CREATED, "roomId": room.id, "message": body}))
        for role, user_id in connected.items():
            if message.type == ChatMessageType.USER and message.sender_id == user_id:
                continue  # 내가 보낸 채팅은 내 안읽음 수를 바꾸지 않는다
            events.append((user_id, _unread_event(db, room, user_id, role)))
        return events

    @staticmethod
    def _read_events(db: Session, room: ChatRoom, payload: dict, connected: dict[ChatRole, str]) -> list:
        reader = ChatRole(payload["readerRole"])
        partner = ChatRole.RUNNER if reader == ChatRole.ORDERER else ChatRole.ORDERER
        events = []
        if partner in connected:
            events.append((
                connected[partner],
                {"type": READ_UPDATED, "roomId": room.id, "lastReadSeq": payload["lastReadSeq"], "version": payload["version"]},
            ))
        if reader in connected:
            events.append((connected[reader], _unread_event(db, room, connected[reader], reader)))
        return events


def _participants(payload: dict) -> dict[ChatRole, str] | None:
    if "ordererId" not in payload or "runnerId" not in payload:
        return None  # 참여자를 담기 전에 기록된 이벤트
    return {ChatRole.ORDERER: payload["ordererId"], ChatRole.RUNNER: payload["runnerId"]}


def _room_state(payload: dict) -> dict[str, Any]:
    keys = ("roomId", "status", "statusReason", "proposalStatus", "offerStatus", "version")
    return {key: payload.get(key) for key in keys}


def _unread_event(db: Session, room: ChatRoom, user_id: str, role: ChatRole) -> dict[str, Any]:
    return {
        "type": "chat.unread.updated",
        "roomId": room.id,
        "unreadCount": unread_count(db, room, user_id, role),
        "totalUnreadCount": ChatReadService.unread_summary(db, user_id).total_unread_count,
    }
