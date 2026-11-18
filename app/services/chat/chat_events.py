"""채팅 이벤트 기록 (CHAT-REQ-029, docs/design-docs/chat-architecture.md "채팅 이벤트").

채팅 서비스는 WebSocket·FCM을 직접 부르지 않고 여기서 Outbox에 기록만 한다. 실제 전달은
전달 대상(chat.realtime, chat.push)이 한다. 모두 aggregate = 채팅방이라 채팅방 안 순서가 지켜진다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatRole, ChatRoom
from app.models.offer import Offer
from app.models.proposal import Proposal
from app.services.outbox.writer import record_event

AGGREGATE_TYPE = "chat_room"
MESSAGE_CREATED = "chat.message.created"
ROOM_UPDATED = "chat.room.updated"
READ_UPDATED = "chat.read.updated"


def _participants(room: ChatRoom) -> dict:
    # 받을 사람을 이벤트에 담아 두면, 받을 연결이 없을 때 전달 대상이 DB를 보지 않고 건너뛸 수 있다.
    return {"roomId": room.id, "ordererId": room.orderer_id, "runnerId": room.runner_id}


def record_message_created(db: Session, room: ChatRoom, message: ChatMessage) -> None:
    """채팅(일반·시스템)이 저장됐다. `message.id`가 있어야 하므로 호출 전에 flush한다."""
    record_event(
        db,
        event_type=MESSAGE_CREATED,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=room.id,
        payload={
            **_participants(room),
            "messageId": message.id,
            "seq": message.seq,
            "type": message.type.value,
            "senderId": message.sender_id,
            "systemEvent": message.system_event.value if message.system_event else None,
        },
        occurred_at=message.created_at,
    )


def record_room_updated(db: Session, room: ChatRoom) -> None:
    """채팅방 상태·`statusReason`·요청·지원 상태가 바뀌었다. 순서 값(`version`)을 올리고 그때의 값을 담는다.

    요청·지원 상태는 일괄 UPDATE로 바뀐 경우가 있어(매칭 미선정 등) 세션 객체가 아니라 DB에서 읽는다.
    """
    room.version += 1
    db.flush()
    proposal_status = db.query(Proposal.status).filter(Proposal.id == room.proposal_id).scalar()
    offer_status = db.query(Offer.status).filter(Offer.id == room.offer_id).scalar()
    record_event(
        db,
        event_type=ROOM_UPDATED,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=room.id,
        payload={
            **_participants(room),
            "status": room.status.value,
            "statusReason": room.status_reason.value if room.status_reason else None,
            "proposalStatus": proposal_status.value if proposal_status else None,
            "offerStatus": offer_status.value if offer_status else None,
            "version": room.version,
        },
    )


def record_read_updated(db: Session, room: ChatRoom, reader: ChatRole, last_read_seq: int, version: int) -> None:
    """읽음 위치가 앞으로 움직였다(읽음, 전체 읽음, 채팅 전송). 움직인 뒤의 위치와 순서 값을 담는다."""
    record_event(
        db,
        event_type=READ_UPDATED,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=room.id,
        payload={**_participants(room), "readerRole": reader.value, "lastReadSeq": last_read_seq, "version": version},
    )
