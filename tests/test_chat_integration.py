"""채팅 통합 테스트 (API + MySQL, tests/conftest.py 의 client/db fixture 사용).

시나리오 정본: docs/domains/chat/test-scenarios.md 의 CHAT-TS-*
TDD 흐름: docs/design-docs/tdd-workflow.md
"""

from __future__ import annotations

import pytest

from app.models.offer import Offer
from app.models.proposal import Proposal, ProposalStatus

GREETING = "안녕하세요! 근처에 있어서 바로 갈 수 있어요."
OFFER_CREATED_TEXT = "회원님의 요청에 새로운 꼬붕이 생겼어요. 확인해보세요!"


def offer_payload(proposal_id: int, **overrides) -> dict:
    payload = {"proposalId": proposal_id, "greeting": GREETING}
    payload.update(overrides)
    return payload


def apply(client, factory, proposal: Proposal, runner, greeting: str = GREETING) -> int:
    """꼬붕이 첫 인사와 함께 지원하고 지원 ID를 돌려준다."""
    response = client.post(
        "/v1/offer",
        json=offer_payload(proposal.id, greeting=greeting),
        headers=factory.headers_for(runner),
    )
    assert response.status_code == 201, response.json()
    return response.json()["data"]["id"]


def runner_with_account(factory, phone: str, name: str):
    runner = factory.user(phone, name=name)
    factory.settlement_account(runner)
    return runner


def room_for_offer(db, offer_id: int):
    from app.models.chat import ChatRoom

    return db.query(ChatRoom).filter(ChatRoom.offer_id == offer_id).one()


def messages(client, factory, room_id: int, viewer) -> list[dict]:
    response = client.get(f"/v1/chat-room/{room_id}/messages", headers=factory.headers_for(viewer))
    assert response.status_code == 200, response.json()
    return response.json()["data"]["content"]


# ------------------------------------------------------------------ 채팅방 생성 (CHAT-REQ-001)


@pytest.mark.scenario("CHAT-TS-001")
def test_applying_creates_one_active_room_for_orderer_and_runner(client, db, factory, sample_user):
    from app.models.chat import ChatRoom, ChatRoomStatus

    runner = runner_with_account(factory, "01070000001", "꼬붕 하나")
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)

    offer_id = apply(client, factory, proposal, runner)

    rooms = db.query(ChatRoom).filter(ChatRoom.offer_id == offer_id).all()
    assert len(rooms) == 1
    room = rooms[0]
    assert room.status == ChatRoomStatus.ACTIVE
    assert room.status_reason is None
    assert room.proposal_id == proposal.id
    assert room.orderer_id == sample_user.id
    assert room.runner_id == runner.id


@pytest.mark.scenario("CHAT-TS-002")
def test_each_runner_gets_a_separate_room_without_mixed_chats(client, db, factory, sample_user):
    runner_a = runner_with_account(factory, "01070000002", "꼬붕 A")
    runner_b = runner_with_account(factory, "01070000003", "꼬붕 B")
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)

    room_a = room_for_offer(db, apply(client, factory, proposal, runner_a, greeting="A의 인사"))
    room_b = room_for_offer(db, apply(client, factory, proposal, runner_b, greeting="B의 인사"))

    assert room_a.id != room_b.id
    user_chats_a = [m for m in messages(client, factory, room_a.id, sample_user) if m["type"] == "USER"]
    user_chats_b = [m for m in messages(client, factory, room_b.id, sample_user) if m["type"] == "USER"]
    assert [(m["senderId"], m["content"]) for m in user_chats_a] == [(runner_a.id, "A의 인사")]
    assert [(m["senderId"], m["content"]) for m in user_chats_b] == [(runner_b.id, "B의 인사")]


@pytest.mark.scenario("CHAT-TS-003")
def test_same_runner_on_two_proposals_gets_two_rooms(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000004", "꼬붕 하나")
    first = factory.proposal(sample_user.id, ProposalStatus.POSTED, title="첫 요청")
    second = factory.proposal(sample_user.id, ProposalStatus.POSTED, title="두 번째 요청")

    room_first = room_for_offer(db, apply(client, factory, first, runner))
    room_second = room_for_offer(db, apply(client, factory, second, runner))

    assert room_first.id != room_second.id
    assert {room_first.proposal_id, room_second.proposal_id} == {first.id, second.id}


# ------------------------------------------------------------------ 접근 권한 (CHAT-REQ-002)


@pytest.mark.scenario("CHAT-TS-004")
def test_non_participant_cannot_read_room_or_chats(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000005", "꼬붕 하나")
    outsider = factory.user("01070000006", name="제3자")
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)
    room = room_for_offer(db, apply(client, factory, proposal, runner))

    for path in (f"/v1/chat-room/{room.id}", f"/v1/chat-room/{room.id}/messages"):
        response = client.get(path, headers=factory.headers_for(outsider))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.scenario("CHAT-TS-005")
def test_orderer_sees_all_rooms_and_runner_only_their_own(client, db, factory, sample_user):
    runner_a = runner_with_account(factory, "01070000007", "꼬붕 A")
    runner_b = runner_with_account(factory, "01070000008", "꼬붕 B")
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)
    room_a = room_for_offer(db, apply(client, factory, proposal, runner_a))
    room_b = room_for_offer(db, apply(client, factory, proposal, runner_b))

    for room in (room_a, room_b):
        response = client.get(f"/v1/chat-room/{room.id}", headers=factory.headers_for(sample_user))
        assert response.status_code == 200
        assert response.json()["data"]["id"] == room.id

    response = client.get(f"/v1/chat-room/{room_a.id}", headers=factory.headers_for(runner_b))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.scenario("CHAT-TS-006")
def test_participants_can_still_read_a_closed_room(client, db, factory, sample_user):
    from app.models.chat import ChatRoomStatus

    runner = runner_with_account(factory, "01070000009", "꼬붕 하나")
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)
    room = room_for_offer(db, apply(client, factory, proposal, runner))
    room.status = ChatRoomStatus.CLOSED
    db.commit()

    for viewer in (sample_user, runner):
        response = client.get(f"/v1/chat-room/{room.id}", headers=factory.headers_for(viewer))
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "CLOSED"
        assert len(messages(client, factory, room.id, viewer)) == 2


# ------------------------------------------------------------------ 지원 시 첫 인사 (CHAT-REQ-006)


@pytest.mark.scenario("CHAT-TS-016")
def test_applying_stores_start_notice_then_greeting(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000010", "꼬붕 하나")
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)
    room = room_for_offer(db, apply(client, factory, proposal, runner))

    for viewer in (sample_user, runner):
        chats = messages(client, factory, room.id, viewer)
        assert [(m["seq"], m["type"]) for m in chats] == [(1, "SYSTEM"), (2, "USER")]
        assert chats[0]["systemEvent"] == "OFFER_CREATED"
        assert chats[0]["senderId"] is None
        assert chats[0]["content"] == (OFFER_CREATED_TEXT if viewer.id == sample_user.id else "지원이 정상적으로 접수됐어요. 행님의 선택을 기다려주세요.")
        assert chats[1]["senderId"] == runner.id
        assert chats[1]["content"] == GREETING


@pytest.mark.scenario("CHAT-TS-017")
@pytest.mark.parametrize(
    "payload_overrides",
    [
        pytest.param({"greeting": None}, id="missing"),
        pytest.param({"greeting": "  \n\t "}, id="blank"),
        pytest.param({"greeting": "가" * 501}, id="too-long"),
    ],
)
def test_invalid_greeting_rejects_application_and_leaves_nothing(client, db, factory, sample_user, payload_overrides):
    from app.models.chat import ChatMessage, ChatRoom

    runner = runner_with_account(factory, "01070000011", "꼬붕 하나")
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)
    payload = offer_payload(proposal.id, **payload_overrides)
    if payload["greeting"] is None:
        del payload["greeting"]

    response = client.post("/v1/offer", json=payload, headers=factory.headers_for(runner))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    db.refresh(proposal)
    assert proposal.status == ProposalStatus.POSTED
    assert db.query(Offer).filter(Offer.proposal_id == proposal.id).count() == 0
    assert db.query(ChatRoom).filter(ChatRoom.proposal_id == proposal.id).count() == 0
    assert db.query(ChatMessage).count() == 0


@pytest.mark.scenario("CHAT-TS-088")
def test_failure_while_saving_greeting_rolls_back_everything(client, db, factory, sample_user, monkeypatch):
    from app.models.chat import ChatMessage, ChatRoom
    from app.services.chat import chat_lifecycle

    def fail_greeting(*args, **kwargs):
        raise RuntimeError("첫 인사 저장 실패")

    monkeypatch.setattr(chat_lifecycle.ChatLifecycle, "_add_greeting", staticmethod(fail_greeting))
    runner = runner_with_account(factory, "01070000012", "꼬붕 하나")
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)

    with pytest.raises(RuntimeError, match="첫 인사 저장 실패"):
        client.post("/v1/offer", json=offer_payload(proposal.id), headers=factory.headers_for(runner))

    db.rollback()
    db.refresh(proposal)
    assert proposal.status == ProposalStatus.POSTED
    assert db.query(Offer).filter(Offer.proposal_id == proposal.id).count() == 0
    assert db.query(ChatRoom).filter(ChatRoom.proposal_id == proposal.id).count() == 0
    assert db.query(ChatMessage).count() == 0


# ================================================================== 4-3 채팅 전송·조회·목록

from datetime import datetime, timedelta, timezone  # noqa: E402


def setup_room(db, factory, orderer, runner, title: str = "요청"):
    """요청·지원·채팅방(지원 등록 안내 + 첫 인사)을 서비스로 직접 만든다. API 지원보다 빠르다."""
    from app.services.chat.chat_lifecycle import ChatLifecycle

    proposal = factory.proposal(orderer.id, ProposalStatus.OFFERED, title=title)
    offer = factory.offer(proposal.id, runner.id)
    room = ChatLifecycle.on_offer_created(db, offer, proposal, GREETING)
    db.commit()
    db.refresh(room)
    return room


def add_user_chats(db, room, sender_id: str, count: int, start_at: datetime | None = None) -> None:
    """채팅을 DB에 바로 넣는다(순번은 채팅방 순번을 이어 쓴다)."""
    from app.models.chat import ChatMessage, ChatMessageType

    base = start_at or datetime(2026, 11, 17, 3, 0, 0)
    for index in range(count):
        seq = room.next_seq()
        db.add(
            ChatMessage(
                room_id=room.id,
                seq=seq,
                type=ChatMessageType.USER,
                sender_id=sender_id,
                content=f"채팅 {seq}",
                created_at=base + timedelta(seconds=index),
            )
        )
        room.last_message_at = base + timedelta(seconds=index)
    db.commit()


def send(client, factory, room_id: int, sender, content: str = "안녕하세요", client_message_id: str = "m-1", **extra):
    return client.post(
        f"/v1/chat-room/{room_id}/messages",
        json={"clientMessageId": client_message_id, "content": content, **extra},
        headers=factory.headers_for(sender),
    )


def chat_list(client, factory, viewer, **params) -> dict:
    response = client.get("/v1/chat-room", params=params, headers=factory.headers_for(viewer))
    assert response.status_code == 200, response.json()
    return response.json()["data"]


def message_count(db, room_id: int) -> int:
    from app.models.chat import ChatMessage

    return db.query(ChatMessage).filter(ChatMessage.room_id == room_id).count()


def outbox_events_for(db, event_type: str) -> list:
    from app.models.outbox import OutboxEvent

    return db.query(OutboxEvent).filter(OutboxEvent.event_type == event_type).order_by(OutboxEvent.id).all()


# ------------------------------------------------------------------ 채팅 전송 (CHAT-REQ-003, 019)


@pytest.mark.scenario("CHAT-TS-008")
def test_participant_sends_text_chat_and_gets_it_back(client, db, factory, sample_user):
    from app.models.chat import ChatMessage

    runner = runner_with_account(factory, "01070000101", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)

    before = datetime.now(timezone.utc)
    response = send(client, factory, room.id, sample_user, content="지금 어디세요?")

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["seq"] == 3
    assert data["type"] == "USER"
    assert data["senderId"] == sample_user.id
    assert data["content"] == "지금 어디세요?"
    # 기존 API와 같이 UTC 시각이다. 시간대 표기가 없으면 UTC로 읽는다.
    sent_at = datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00"))
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    assert sent_at.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=2) <= sent_at <= datetime.now(timezone.utc) + timedelta(seconds=2)

    stored = db.query(ChatMessage).filter(ChatMessage.id == data["id"]).one()
    assert (stored.sender_id, stored.content, stored.seq) == (sample_user.id, "지금 어디세요?", 3)


@pytest.mark.scenario("CHAT-TS-081")
def test_non_participant_cannot_send(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000102", "꼬붕 하나")
    outsider = factory.user("01070000103", name="제3자")
    room = setup_room(db, factory, sample_user, runner)

    response = send(client, factory, room.id, outsider)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert message_count(db, room.id) == 2


@pytest.mark.scenario("CHAT-TS-061")
def test_client_cannot_send_a_system_chat(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000104", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)

    response = send(client, factory, room.id, sample_user, type="SYSTEM")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert message_count(db, room.id) == 2


@pytest.mark.scenario("CHAT-TS-056")
def test_retrying_with_the_same_client_message_id_stores_one_chat(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000105", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    events_before = len(outbox_events_for(db, "chat.message.created"))

    first = send(client, factory, room.id, sample_user, content="재시도", client_message_id="retry-1")
    second = send(client, factory, room.id, sample_user, content="재시도", client_message_id="retry-1")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert message_count(db, room.id) == 3
    # 실시간 전달과 푸시는 이 이벤트 하나에서만 나간다
    assert len(outbox_events_for(db, "chat.message.created")) == events_before + 1


@pytest.mark.scenario("CHAT-TS-057")
def test_same_client_message_id_with_different_content_or_room_is_rejected(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000106", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner, title="첫 요청")
    other_room = setup_room(db, factory, sample_user, runner, title="두 번째 요청")
    assert send(client, factory, room.id, sample_user, content="원래 내용", client_message_id="dup").status_code == 201

    different_content = send(client, factory, room.id, sample_user, content="다른 내용", client_message_id="dup")
    different_room = send(client, factory, other_room.id, sample_user, content="원래 내용", client_message_id="dup")

    for response in (different_content, different_room):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CHAT_MESSAGE_ID_CONFLICT"
    assert message_count(db, room.id) == 3
    assert message_count(db, other_room.id) == 2


@pytest.mark.scenario("CHAT-TS-098")
def test_same_client_message_id_from_different_users_is_independent(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000107", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)

    by_orderer = send(client, factory, room.id, sample_user, content="행님", client_message_id="same-id")
    by_runner = send(client, factory, room.id, runner, content="꼬붕", client_message_id="same-id")

    assert by_orderer.status_code == 201
    assert by_runner.status_code == 201
    assert by_orderer.json()["data"]["id"] != by_runner.json()["data"]["id"]
    assert message_count(db, room.id) == 4


@pytest.mark.scenario("CHAT-TS-100")
def test_chat_event_is_recorded_only_when_the_chat_is_committed(client, db, factory, sample_user, monkeypatch):
    from app.services.chat import chat_events

    runner = runner_with_account(factory, "01070000108", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    events_before = outbox_events_for(db, "chat.message.created")

    response = send(client, factory, room.id, sample_user, content="커밋될 채팅", client_message_id="ok-1")
    assert response.status_code == 201
    events = outbox_events_for(db, "chat.message.created")
    assert len(events) == len(events_before) + 1
    assert events[-1].aggregate_type == "chat_room"
    assert events[-1].aggregate_id == str(room.id)
    assert events[-1].payload["messageId"] == response.json()["data"]["id"]

    original = chat_events.record_message_created

    def record_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("채팅 저장 중 실패")

    monkeypatch.setattr(chat_events, "record_message_created", record_then_fail)
    with pytest.raises(RuntimeError, match="채팅 저장 중 실패"):
        send(client, factory, room.id, sample_user, content="롤백될 채팅", client_message_id="fail-1")

    db.rollback()
    assert message_count(db, room.id) == 3
    assert len(outbox_events_for(db, "chat.message.created")) == len(events)


# ------------------------------------------------------------------ 채팅 조회 (CHAT-REQ-004, 005, 016, 022)


@pytest.mark.scenario("CHAT-TS-010")
def test_chats_page_by_30_from_latest_then_older(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000109", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    add_user_chats(db, room, runner.id, 43)  # 지원 안내·첫 인사 2개 + 43개 = 45개

    first = client.get(f"/v1/chat-room/{room.id}/messages", headers=factory.headers_for(sample_user)).json()["data"]
    assert [m["seq"] for m in first["content"]] == list(range(16, 46))
    assert first["hasPrevious"] is True

    older = client.get(
        f"/v1/chat-room/{room.id}/messages", params={"beforeSeq": 16}, headers=factory.headers_for(sample_user)
    ).json()["data"]
    assert [m["seq"] for m in older["content"]] == list(range(1, 16))
    assert older["hasPrevious"] is False


@pytest.mark.scenario("CHAT-TS-045")
def test_chats_after_the_last_received_seq_come_without_gaps_or_duplicates(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000110", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    add_user_chats(db, room, runner.id, 13)  # seq 3~15

    response = client.get(
        f"/v1/chat-room/{room.id}/messages", params={"afterSeq": 10}, headers=factory.headers_for(sample_user)
    )

    assert response.status_code == 200
    assert [m["seq"] for m in response.json()["data"]["content"]] == [11, 12, 13, 14, 15]


@pytest.mark.scenario("CHAT-TS-067")
def test_user_and_system_chats_come_in_one_list_in_saved_order(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000111", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    send(client, factory, room.id, sample_user, content="행님 채팅", client_message_id="o-1")
    send(client, factory, room.id, runner, content="꼬붕 채팅", client_message_id="r-1")

    chats = messages(client, factory, room.id, runner)

    assert [(m["seq"], m["type"]) for m in chats] == [(1, "SYSTEM"), (2, "USER"), (3, "USER"), (4, "USER")]
    assert chats[0]["systemEvent"] == "OFFER_CREATED"
    assert all(m["systemEvent"] is None for m in chats[1:])


@pytest.mark.scenario("CHAT-TS-015")
@pytest.mark.parametrize(
    "change",
    [
        "closed",
        pytest.param("blocked", marks=pytest.mark.skip(reason="사용자 차단 구현 후 활성화 (user-block.md)")),
    ],
)
def test_both_sides_can_read_existing_chats_after_close_or_block(client, db, factory, sample_user, change):
    from app.models.chat import ChatRoomStatus

    runner = runner_with_account(factory, "01070000112", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    add_user_chats(db, room, runner.id, 3)
    if change == "closed":
        room.status = ChatRoomStatus.CLOSED
        db.commit()

    for viewer in (sample_user, runner):
        assert [m["seq"] for m in messages(client, factory, room.id, viewer)] == [1, 2, 3, 4, 5]


# ------------------------------------------------------------------ 채팅 목록 (CHAT-REQ-014)


@pytest.mark.scenario("CHAT-TS-011")
def test_chat_list_orders_by_latest_chat_and_uses_created_time_for_empty_rooms(client, db, factory, sample_user):
    from app.models.chat import ChatRoom, ChatRoomStatus

    runner = runner_with_account(factory, "01070000113", "꼬붕 하나")
    older = setup_room(db, factory, sample_user, runner, title="오래된 채팅")
    newer = setup_room(db, factory, sample_user, runner, title="최근 채팅")
    older.last_message_at = datetime(2026, 11, 17, 1, 0, 0)
    newer.last_message_at = datetime(2026, 11, 17, 3, 0, 0)
    # 채팅이 없는 채팅방(배포 때 기존 지원으로 만든 방)은 생성 시각으로 줄을 선다
    empty_proposal = factory.proposal(sample_user.id, ProposalStatus.OFFERED, title="채팅 없음")
    empty_offer = factory.offer(empty_proposal.id, runner.id)
    empty = ChatRoom(
        offer_id=empty_offer.id,
        proposal_id=empty_proposal.id,
        orderer_id=sample_user.id,
        runner_id=runner.id,
        status=ChatRoomStatus.ACTIVE,
        last_seq=0,
        created_at=datetime(2026, 11, 17, 2, 0, 0),
    )
    db.add(empty)
    db.commit()

    rooms = chat_list(client, factory, sample_user)["content"]

    assert [room["id"] for room in rooms] == [newer.id, empty.id, older.id]
    assert rooms[1]["lastMessage"] is None


@pytest.mark.scenario("CHAT-TS-012")
def test_chat_list_item_has_everything_the_list_screen_needs(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000114", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner, title="편의점 심부름")

    item = chat_list(client, factory, sample_user)["content"][0]

    assert item["id"] == room.id
    assert item["partnerName"] == "꼬붕 하나"
    assert item["proposalTitle"] == "편의점 심부름"
    assert item["lastMessage"]["content"] == GREETING
    assert item["lastMessage"]["seq"] == 2
    assert item["lastMessageAt"] is not None
    assert item["unreadCount"] == 2
    assert item["status"] == "ACTIVE"
    assert item["statusReason"] is None
    assert item["proposalStatus"] == "OFFERED"
    assert item["offerStatus"] == "WAITING"
    assert item["blockStatus"] == "NONE"


@pytest.mark.scenario("CHAT-TS-013")
def test_withdrawn_partner_shows_placeholder_name_but_keeps_their_chats(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000115", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    runner.withdraw(datetime(2026, 11, 17, 4, 0, 0))
    db.commit()

    item = chat_list(client, factory, sample_user)["content"][0]
    detail = client.get(f"/v1/chat-room/{room.id}", headers=factory.headers_for(sample_user)).json()["data"]
    chats = messages(client, factory, room.id, sample_user)

    assert item["partnerName"] == "탈퇴한 사용자"
    assert detail["partnerName"] == "탈퇴한 사용자"
    assert chats[1]["senderId"] == runner.id
    assert chats[1]["content"] == GREETING


@pytest.mark.scenario("CHAT-TS-014")
def test_viewing_the_chat_list_does_not_mark_anything_read(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01070000116", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    add_user_chats(db, room, runner.id, 3)

    first = chat_list(client, factory, sample_user)["content"][0]
    second = chat_list(client, factory, sample_user)["content"][0]

    db.refresh(room)
    assert room.orderer_last_read_seq == 0
    assert first["unreadCount"] == second["unreadCount"] == 5


@pytest.mark.scenario("CHAT-TS-082")
def test_list_shows_the_last_system_chat_in_each_viewers_wording(client, db, factory, sample_user):
    from app.models.chat import ChatMessage, ChatMessageType, SystemChatEvent

    runner = runner_with_account(factory, "01070000117", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    db.add(
        ChatMessage(
            room_id=room.id,
            seq=room.next_seq(),
            type=ChatMessageType.SYSTEM,
            system_event=SystemChatEvent.NOT_SELECTED,
            system_event_key=f"NOT_SELECTED:offer:{room.offer_id}",
            created_at=datetime(2026, 11, 17, 5, 0, 0),
        )
    )
    room.last_message_at = datetime(2026, 11, 17, 5, 0, 0)
    db.commit()

    runner_item = chat_list(client, factory, runner)["content"][0]
    orderer_item = chat_list(client, factory, sample_user)["content"][0]

    assert runner_item["lastMessage"]["content"] == "이번엔 선택받지 못했지만 다음 기회가 분명 있을 거예요. 다시 도전해보세요!"
    assert orderer_item["lastMessage"]["content"] == "다른 꼬붕과 매칭되어 채팅이 종료됐어요."


@pytest.mark.scenario("CHAT-TS-083")
def test_chat_list_pages_across_both_roles_without_gaps_or_duplicates(client, db, factory, sample_user):
    other = factory.user("01070000118", name="다른 사용자")
    factory.settlement_account(other)
    factory.settlement_account(sample_user)
    expected: set[int] = set()
    for index in range(8):  # 나는 행님
        room = setup_room(db, factory, sample_user, other, title=f"내 요청 {index}")
        room.last_message_at = datetime(2026, 11, 17, 0, 0, 0) + timedelta(minutes=index * 2)
        expected.add(room.id)
    for index in range(7):  # 나는 꼬붕
        room = setup_room(db, factory, other, sample_user, title=f"남의 요청 {index}")
        room.last_message_at = datetime(2026, 11, 17, 0, 0, 0) + timedelta(minutes=index * 2 + 1)
        expected.add(room.id)
    db.commit()

    first = chat_list(client, factory, sample_user, size=10)
    second = chat_list(client, factory, sample_user, size=10, cursor=first["nextCursor"])

    ids = [room["id"] for room in first["content"]] + [room["id"] for room in second["content"]]
    assert len(first["content"]) == 10
    assert second["nextCursor"] is None
    assert len(ids) == len(set(ids)) == 15
    assert set(ids) == expected
    roles = {room["myRole"] for room in first["content"] + second["content"]}
    assert roles == {"ORDERER", "RUNNER"}


# ================================================================== 4-4 채팅방 상태와 시스템 채팅


class Journey:
    """요청 하나를 실제 API로 진행시키는 테스트 도우미. 꼬붕 여러 명이 지원할 수 있다."""

    __test__ = False

    def __init__(self, client, db, factory, orderer, admin_headers=None, errand_fee: int = 5000):
        self.client, self.db, self.factory = client, db, factory
        self.orderer = orderer
        self.admin_headers = admin_headers
        self.proposal = factory.proposal(orderer.id, ProposalStatus.POSTED)
        self.proposal.errand_fee = errand_fee
        db.commit()
        self.runners: list = []
        self.offer_ids: dict[str, int] = {}

    # ------------------------------------------------------------- 사건
    def apply(self, phone: str, name: str):
        runner = runner_with_account(self.factory, phone, name)
        self.offer_ids[runner.id] = apply(self.client, self.factory, self.proposal, runner)
        self.runners.append(runner)
        return runner

    def accept(self, runner) -> None:
        response = self.client.post(f"/v1/offer/{self.offer_ids[runner.id]}/accept", headers=self.h(self.orderer))
        assert response.status_code == 201, response.json()

    def cancel_offer(self, runner):
        return self.client.delete(f"/v1/offer/{self.offer_ids[runner.id]}", headers=self.h(runner))

    def withdraw(self, user) -> None:
        from app.models.user import UserWithdrawalReasonQuestion

        reason = UserWithdrawalReasonQuestion(question_text="서비스를 잘 쓰지 않아요", display_order=99, requires_detail=False, is_active=True)
        self.db.add(reason)
        self.db.commit()
        response = self.client.delete("/v1/user", json={"reasonQuestionId": reason.id}, headers=self.h(user))
        assert response.status_code == 200, response.json()

    def runner_complete(self, runner):
        return self.client.post(f"/v1/offer/{self.offer_ids[runner.id]}/complete-delivery", headers=self.h(runner))

    def orderer_confirm(self):
        return self.client.post(f"/v1/proposal/{self.proposal.id}/confirm-received", headers=self.h(self.orderer))

    def dispute(self, by: str, runner):
        from app.models.dispute_survey import DisputeSurveyQuestion, DisputeSurveyTargetType

        target = DisputeSurveyTargetType.ORDER if by == "ORDERER" else DisputeSurveyTargetType.RUNNER
        question = DisputeSurveyQuestion(target_type=target, question_text="문제가 있었어요", display_order=1, is_active=True, requires_detail=False)
        self.db.add(question)
        self.db.commit()
        body = {"reasonQuestionId": question.id, "detailReason": "약속 장소에 없었어요"}
        if by == "ORDERER":
            response = self.client.post(f"/v1/proposal/{self.proposal.id}/dispute", json=body, headers=self.h(self.orderer))
        else:
            response = self.client.post(f"/v1/offer/{self.offer_ids[runner.id]}/dispute", json=body, headers=self.h(runner))
        assert response.status_code == 200, response.json()

    def resolve(self, outcome: str, runner) -> None:
        response = self.client.post(
            f"/v1/admin/missions/{self.mission(runner).id}/resolve", json={"resolution": outcome}, headers=self.admin_headers
        )
        assert response.status_code == 200, response.json()

    def payout(self, runner):
        return self.client.post(f"/v1/admin/payout/{self.mission(runner).id}/complete", json={"adminNote": "이체 완료"}, headers=self.admin_headers)

    def cancel_proposal(self):
        return self.client.post(f"/v1/proposal/{self.proposal.id}/cancel", headers=self.h(self.orderer))

    def admin_cancel(self):
        return self.client.post(f"/v1/admin/proposal/{self.proposal.id}/cancel", json={"adminNote": "운영 취소"}, headers=self.admin_headers)

    def refund_complete(self) -> None:
        from app.models.refund import Refund

        refund = self.db.query(Refund).filter(Refund.proposal_id == self.proposal.id).one()
        response = self.client.post(f"/v1/admin/refund/{refund.id}/complete", json={"adminNote": "환불 완료"}, headers=self.admin_headers)
        assert response.status_code == 200, response.json()

    def report_and_accept(self) -> None:
        from app.models.proposal_report import ProposalReport, ProposalReportReasonQuestion, ProposalReportStatus

        reason = ProposalReportReasonQuestion(question_text="광고 또는 스팸이에요", display_order=1, is_active=True, requires_detail=False)
        self.db.add(reason)
        self.db.commit()
        reporter = self.factory.user("01079999999", name="신고자")
        report = ProposalReport(proposal_id=self.proposal.id, reporter_id=reporter.id, reason_question_id=reason.id, status=ProposalReportStatus.PENDING)
        self.db.add(report)
        self.db.commit()
        response = self.client.post(f"/v1/admin/proposal-reports/{report.id}/accept", headers=self.admin_headers)
        assert response.status_code == 200, response.json()

    # ------------------------------------------------------------- 조회
    def h(self, user) -> dict:
        return self.factory.headers_for(user)

    def mission(self, runner):
        from app.models.mission import Mission

        self.db.expire_all()
        return self.db.query(Mission).filter(Mission.offer_id == self.offer_ids[runner.id]).one()

    def room(self, runner):
        self.db.expire_all()
        return room_for_offer(self.db, self.offer_ids[runner.id])

    def state(self, runner) -> tuple[str, str | None]:
        room = self.room(runner)
        return room.status.value, room.status_reason.value if room.status_reason else None

    def system_chats(self, runner, viewer=None) -> list[tuple[str, str]]:
        """(사건 코드, 보는 사람에게 보이는 문구) 목록. 기본은 행님 기준."""
        chats = messages(self.client, self.factory, self.room(runner).id, viewer or self.orderer)
        return [(m["systemEvent"], m["content"]) for m in chats if m["type"] == "SYSTEM"]

    def events(self, runner) -> list[str]:
        return [event for event, _ in self.system_chats(runner)]


@pytest.fixture
def journey(client, db, factory, sample_user, admin_headers):
    return Journey(client, db, factory, sample_user, admin_headers)


# ------------------------------------------------------------------ 채팅방 상태 변경 (CHAT-REQ-007·008·009)


@pytest.mark.scenario("CHAT-TS-018")
def test_matching_keeps_the_selected_room_and_closes_the_others(journey):
    a = journey.apply("01071000001", "꼬붕 A")
    b = journey.apply("01071000002", "꼬붕 B")

    journey.accept(a)

    assert journey.state(a) == ("ACTIVE", None)
    assert journey.state(b) == ("CLOSED", "NOT_SELECTED")


@pytest.mark.scenario("CHAT-TS-019")
@pytest.mark.parametrize("how", ["cancel", "withdraw"])
def test_runner_cancelling_or_withdrawing_closes_the_room(journey, how):
    runner = journey.apply("01071000003", "꼬붕 하나")

    if how == "cancel":
        assert journey.cancel_offer(runner).status_code == 204
    else:
        journey.withdraw(runner)

    assert journey.state(runner) == ("CLOSED", "OFFER_CANCELLED")


@pytest.mark.scenario("CHAT-TS-020")
def test_orderer_cancelling_before_matching_closes_every_room(journey):
    a = journey.apply("01071000004", "꼬붕 A")
    b = journey.apply("01071000005", "꼬붕 B")

    assert journey.cancel_proposal().status_code == 200

    assert journey.state(a) == ("CLOSED", "PROPOSAL_CANCELLED")
    assert journey.state(b) == ("CLOSED", "PROPOSAL_CANCELLED")


@pytest.mark.scenario("CHAT-TS-021")
@pytest.mark.parametrize("matched", [False, True], ids=["before-match", "after-match"])
def test_admin_cancel_closes_rooms_that_were_still_open(journey, matched):
    a = journey.apply("01071000006", "꼬붕 A")
    b = journey.apply("01071000007", "꼬붕 B")
    if matched:
        journey.accept(a)

    assert journey.admin_cancel().status_code == 200

    assert journey.state(a) == ("CLOSED", "ADMIN_CANCELLED")
    # 매칭 때 이미 닫힌 방은 이유가 바뀌지 않는다
    assert journey.state(b) == (("CLOSED", "NOT_SELECTED") if matched else ("CLOSED", "ADMIN_CANCELLED"))


@pytest.mark.scenario("CHAT-TS-022")
def test_accepting_a_report_closes_waiting_rooms_without_a_system_chat(journey):
    runner = journey.apply("01071000008", "꼬붕 하나")
    before = journey.events(runner)

    journey.report_and_accept()

    assert journey.state(runner) == ("CLOSED", "ADMIN_CANCELLED")
    assert journey.events(runner) == before


@pytest.mark.scenario("CHAT-TS-023")
@pytest.mark.parametrize(
    "raised_by,outcome,disputed,resolved",
    [
        ("ORDERER", "COMPLETED", "ORDERER_DISPUTED", "DISPUTE_COMPLETED"),
        ("RUNNER", "FAILED", "RUNNER_DISPUTED", "DISPUTE_FAILED"),
    ],
)
def test_dispute_pauses_the_room_and_resolution_closes_it(journey, raised_by, outcome, disputed, resolved):
    runner = journey.apply("01071000009", "꼬붕 하나")
    journey.accept(runner)

    journey.dispute(raised_by, runner)
    assert journey.state(runner) == ("INACTIVE", disputed)

    journey.resolve(outcome, runner)
    assert journey.state(runner) == ("CLOSED", resolved)


@pytest.mark.scenario("CHAT-TS-025")
def test_room_closes_only_after_both_sides_confirm(journey):
    runner = journey.apply("01071000010", "꼬붕 하나")
    journey.accept(runner)

    assert journey.runner_complete(runner).status_code == 200
    assert journey.state(runner) == ("ACTIVE", None)

    assert journey.orderer_confirm().status_code == 200
    assert journey.state(runner) == ("CLOSED", "ALL_CONFIRMED")


@pytest.mark.scenario("CHAT-TS-026")
def test_repeating_a_completion_is_rejected_and_changes_nothing(journey):
    runner = journey.apply("01071000011", "꼬붕 하나")
    journey.accept(runner)
    assert journey.runner_complete(runner).status_code == 200
    before = (journey.state(runner), journey.events(runner))

    again = journey.runner_complete(runner)

    assert again.status_code >= 400
    assert (journey.state(runner), journey.events(runner)) == before


@pytest.mark.scenario("CHAT-TS-027")
@pytest.mark.skip(reason="사용자 차단 구현 후 활성화 (user-block.md)")
def test_completion_works_even_when_one_side_blocked_the_other(journey):
    """차단이 있어도 임무 완료(확인)는 처리된다."""


@pytest.mark.scenario("CHAT-TS-028")
@pytest.mark.parametrize("closed_by", ["dispute", "cancel"], ids=["inactive", "closed"])
def test_inactive_or_closed_room_rejects_new_chats(journey, client, factory, db, closed_by):
    runner = journey.apply("01071000012", "꼬붕 하나")
    if closed_by == "dispute":
        journey.accept(runner)
        journey.dispute("ORDERER", runner)
    else:
        journey.cancel_offer(runner)
    room_id = journey.room(runner).id
    before = message_count(db, room_id)

    response = send(client, factory, room_id, runner, content="보낼 수 없는 채팅")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHAT_ROOM_NOT_SENDABLE"
    assert message_count(db, room_id) == before


@pytest.mark.scenario("CHAT-TS-029")
@pytest.mark.skip(reason="사용자 차단 구현 후 활성화 (user-block.md)")
def test_blocked_active_room_rejects_chats_from_both_sides(journey):
    """한쪽이 차단한 ACTIVE 채팅방에서는 양쪽 모두 보낼 수 없다."""


@pytest.mark.scenario("CHAT-TS-094")
def test_sending_against_a_stale_open_room_is_rejected_with_the_new_state(journey, client, factory):
    runner = journey.apply("01071000013", "꼬붕 하나")
    room_id = journey.room(runner).id
    journey.cancel_offer(runner)  # 앱은 아직 ACTIVE로 알고 있다

    response = send(client, factory, room_id, journey.orderer, content="늦게 보낸 채팅")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHAT_ROOM_NOT_SENDABLE"
    detail = client.get(f"/v1/chat-room/{room_id}", headers=factory.headers_for(journey.orderer)).json()["data"]
    assert (detail["status"], detail["statusReason"]) == ("CLOSED", "OFFER_CANCELLED")


@pytest.mark.scenario("CHAT-TS-087")
def test_admin_cannot_cancel_a_disputed_request_and_room_stays_paused(journey):
    runner = journey.apply("01071000014", "꼬붕 하나")
    journey.accept(runner)
    journey.dispute("RUNNER", runner)
    before = journey.events(runner)

    response = journey.admin_cancel()

    assert response.status_code >= 400
    assert journey.state(runner) == ("INACTIVE", "RUNNER_DISPUTED")
    assert journey.events(runner) == before


# ------------------------------------------------------------------ 시스템 채팅 (CHAT-REQ-020·021·024)

ORDERER_TEXT = {
    "OFFER_CREATED": "회원님의 요청에 새로운 꼬붕이 생겼어요. 확인해보세요!",
    "MATCHED": "꼬붕을 선택하셨어요! 임무를 바로 시작해보세요.",
    "NOT_SELECTED": "다른 꼬붕과 매칭되어 채팅이 종료됐어요.",
    "OFFER_CANCELLED": "꼬붕이 지원을 취소했어요. 채팅이 자동으로 종료돼요.",
    "RUNNER_COMPLETED": "꼬붕이 임무를 완료했어요. 회원님도 확인해주시면 수행비가 꼬붕에게 전달돼요.",
    "ORDERER_CONFIRMED": "꼬붕의 임무 완료를 기다리고 있어요.",
    "ALL_CONFIRMED": "양측 모두 임무 완료를 확인했어요. 성공적으로 임무 수행이 완료됐습니다!",
    "DISPUTE_RAISED": "분쟁 중인 임무예요. 분쟁이 해결될 때까지 잠시만 기다려 주세요.",
    "DISPUTE_COMPLETED": "임무가 완료됐어요. 정산이 곧 시작돼요.",
    "DISPUTE_FAILED": "종료된 임무예요. 더 이상 진행할 수 없어요.",
    "PROPOSAL_CANCELLED": "요청이 취소되어 채팅이 종료됐어요.",
    "ADMIN_CANCELLED_AFTER_MATCH": "종료된 임무예요. 더 이상 진행할 수 없어요.",
    "PAYOUT_COMPLETED": "꼬붕에게 수행비 5,000원이 입금됐어요.",
    "REFUND_COMPLETED": "행님에게 환불이 완료됐어요.",
}
RUNNER_TEXT = {
    **ORDERER_TEXT,
    "NOT_SELECTED": "이번엔 선택받지 못했지만 다음 기회가 분명 있을 거예요. 다시 도전해보세요!",
    "OFFER_CANCELLED": "지원을 취소했어요. 채팅이 자동으로 종료돼요.",
    "RUNNER_COMPLETED": "행님의 임무 완료 확인을 기다리고 있어요.",
    "ORDERER_CONFIRMED": "행님이 임무 완료를 확인했어요. 회원님도 앱에서 임무 완료를 눌러주시면 정산이 바로 진행돼요!",
    "OFFER_CREATED": "지원이 정상적으로 접수됐어요. 행님의 선택을 기다려주세요.",
    "MATCHED": "행님이 회원님을 선택했어요.",
    "ALL_CONFIRMED": "양측 모두 임무 완료를 확인했어요. 성공적으로 임무 수행이 완료됐습니다!",
    "PAYOUT_COMPLETED": "5,000원이 회원님 계좌로 입금됐어요. 오늘도 멋진 활동 감사해요!",
    "DISPUTE_RAISED": "행님이 분쟁을 접수했어요. 앱에서 내용을 확인해주세요.",
}


def _cause(journey: Journey, case: str):
    """사건을 일으키고, 확인할 꼬붕과 그 채팅방에 새로 생겨야 하는 시스템 채팅을 돌려준다."""
    a = journey.apply("01072000001", "꼬붕 A")
    if case == "OFFER_CREATED":
        return a, "OFFER_CREATED"
    if case == "NOT_SELECTED":
        b = journey.apply("01072000002", "꼬붕 B")
        journey.accept(a)
        return b, "NOT_SELECTED"
    if case == "OFFER_CANCELLED":
        journey.cancel_offer(a)
        return a, "OFFER_CANCELLED"
    if case == "OFFER_CANCELLED_BY_WITHDRAWAL":
        journey.withdraw(a)
        return a, "OFFER_CANCELLED"
    if case == "PROPOSAL_CANCELLED":
        journey.cancel_proposal()
        return a, "PROPOSAL_CANCELLED"
    if case == "PROPOSAL_CANCELLED_BY_ADMIN":
        journey.admin_cancel()
        return a, "PROPOSAL_CANCELLED"
    journey.accept(a)
    if case == "MATCHED":
        return a, "MATCHED"
    if case == "RUNNER_COMPLETED":
        journey.runner_complete(a)
        return a, "RUNNER_COMPLETED"
    if case == "ORDERER_CONFIRMED":
        journey.orderer_confirm()
        return a, "ORDERER_CONFIRMED"
    if case == "ALL_CONFIRMED":
        journey.runner_complete(a)
        journey.orderer_confirm()
        return a, "ALL_CONFIRMED"
    if case == "DISPUTE_RAISED":
        journey.dispute("ORDERER", a)
        return a, "DISPUTE_RAISED"
    if case == "DISPUTE_COMPLETED":
        journey.dispute("ORDERER", a)
        journey.resolve("COMPLETED", a)
        return a, "DISPUTE_COMPLETED"
    if case == "DISPUTE_FAILED":
        journey.dispute("RUNNER", a)
        journey.resolve("FAILED", a)
        return a, "DISPUTE_FAILED"
    if case == "ADMIN_CANCELLED_AFTER_MATCH":
        journey.admin_cancel()
        return a, "ADMIN_CANCELLED_AFTER_MATCH"
    if case == "PAYOUT_COMPLETED":
        journey.runner_complete(a)
        journey.orderer_confirm()
        journey.payout(a)
        return a, "PAYOUT_COMPLETED"
    if case == "REFUND_COMPLETED":
        journey.dispute("RUNNER", a)
        journey.resolve("FAILED", a)
        journey.refund_complete()
        return a, "REFUND_COMPLETED"
    raise AssertionError(case)


@pytest.mark.scenario("CHAT-TS-089")
@pytest.mark.parametrize(
    "case",
    [
        "OFFER_CREATED",
        "MATCHED",
        "NOT_SELECTED",
        "OFFER_CANCELLED",
        "OFFER_CANCELLED_BY_WITHDRAWAL",
        "RUNNER_COMPLETED",
        "ORDERER_CONFIRMED",
        "ALL_CONFIRMED",
        "DISPUTE_RAISED",
        "DISPUTE_COMPLETED",
        "DISPUTE_FAILED",
        "PROPOSAL_CANCELLED",
        "PROPOSAL_CANCELLED_BY_ADMIN",
        "ADMIN_CANCELLED_AFTER_MATCH",
        "PAYOUT_COMPLETED",
        "REFUND_COMPLETED",
    ],
)
def test_each_event_stores_one_system_chat_with_each_viewers_wording(journey, case):
    runner, event = _cause(journey, case)

    orderer_view = journey.system_chats(runner)
    runner_view = journey.system_chats(runner, viewer=runner if case != "OFFER_CANCELLED_BY_WITHDRAWAL" else None)

    assert [e for e, _ in orderer_view].count(event) == 1
    assert orderer_view[-1] == (event, ORDERER_TEXT[event])
    if case != "OFFER_CANCELLED_BY_WITHDRAWAL":  # 탈퇴한 꼬붕은 더 조회하지 않는다
        assert runner_view[-1] == (event, RUNNER_TEXT[event])


@pytest.mark.scenario("CHAT-TS-064")
@pytest.mark.parametrize(
    "matched,text",
    [
        (False, "요청이 취소되어 채팅이 종료됐어요."),
        (True, "종료된 임무예요. 더 이상 진행할 수 없어요."),
    ],
    ids=["before-match", "after-match"],
)
def test_admin_cancel_wording_depends_on_whether_a_mission_exists(journey, matched, text):
    runner = journey.apply("01071000015", "꼬붕 하나")
    if matched:
        journey.accept(runner)

    journey.admin_cancel()

    assert journey.system_chats(runner)[-1][1] == text
    assert journey.system_chats(runner, viewer=runner)[-1][1] == text


@pytest.mark.scenario("CHAT-TS-066")
def test_payout_notice_shows_the_formatted_amount_to_both(client, db, factory, sample_user, admin_headers):
    journey = Journey(client, db, factory, sample_user, admin_headers, errand_fee=15000)
    runner = journey.apply("01071000016", "꼬붕 하나")
    journey.accept(runner)
    journey.runner_complete(runner)
    journey.orderer_confirm()

    assert journey.payout(runner).status_code == 200

    expected = "꼬붕에게 수행비 15,000원이 입금됐어요."
    assert journey.system_chats(runner)[-1] == ("PAYOUT_COMPLETED", expected)
    assert journey.system_chats(runner, viewer=runner)[-1] == ("PAYOUT_COMPLETED", "15,000원이 회원님 계좌로 입금됐어요. 오늘도 멋진 활동 감사해요!")


@pytest.mark.scenario("CHAT-TS-065")
def test_refund_notice_uses_matched_room_or_all_pre_match_rooms(client, db, factory, sample_user, admin_headers):
    after_match = Journey(client, db, factory, sample_user, admin_headers)
    matched_runner = after_match.apply("01071000017", "꼬붕 하나")
    unselected_runner = after_match.apply("01071000019", "미선정 꼬붕")
    after_match.accept(matched_runner)
    after_match.dispute("RUNNER", matched_runner)
    after_match.resolve("FAILED", matched_runner)

    before_match = Journey(client, db, factory, sample_user, admin_headers)
    waiting_runner = before_match.apply("01071000018", "꼬붕 둘")
    assert before_match.cancel_proposal().status_code == 200

    after_match.refund_complete()
    before_match.refund_complete()

    assert after_match.events(matched_runner)[-1] == "REFUND_COMPLETED"
    assert "REFUND_COMPLETED" not in after_match.events(unselected_runner)
    assert before_match.events(waiting_runner)[-1] == "REFUND_COMPLETED"


@pytest.mark.scenario("CHAT-TS-090")
def test_refund_notice_appears_only_once_the_refund_is_completed(journey):
    runner = journey.apply("01071000019", "꼬붕 하나")
    journey.accept(runner)
    journey.dispute("RUNNER", runner)
    journey.resolve("FAILED", runner)  # 환불이 PENDING으로 생긴다

    assert "REFUND_COMPLETED" not in journey.events(runner)

    journey.refund_complete()

    assert journey.events(runner).count("REFUND_COMPLETED") == 1


@pytest.mark.scenario("CHAT-TS-059")
def test_the_same_payout_handled_twice_leaves_one_notice(journey, db):
    from app.services.chat.chat_lifecycle import ChatLifecycle

    runner = journey.apply("01071000020", "꼬붕 하나")
    journey.accept(runner)
    journey.runner_complete(runner)
    journey.orderer_confirm()
    assert journey.payout(runner).status_code == 200

    # 같은 사건이 한 번 더 전달된 경우 (예: 재처리)
    ChatLifecycle.on_payout_completed(db, journey.mission(runner))
    db.commit()

    assert journey.events(runner).count("PAYOUT_COMPLETED") == 1


@pytest.mark.scenario("CHAT-TS-060")
@pytest.mark.parametrize(
    "case",
    [
        "payout-in-closed-room",
        "refund-in-closed-room",
        pytest.param("blocked-room", marks=pytest.mark.skip(reason="사용자 차단 구현 후 활성화 (user-block.md)")),
    ],
)
def test_money_notices_are_stored_even_in_closed_rooms(journey, case):
    runner = journey.apply("01071000021", "꼬붕 하나")
    journey.accept(runner)
    if case == "payout-in-closed-room":
        journey.runner_complete(runner)
        journey.orderer_confirm()
        assert journey.state(runner)[0] == "CLOSED"
        journey.payout(runner)
        assert journey.events(runner)[-1] == "PAYOUT_COMPLETED"
    else:
        journey.dispute("RUNNER", runner)
        journey.resolve("FAILED", runner)
        assert journey.state(runner)[0] == "CLOSED"
        journey.refund_complete()
        assert journey.events(runner)[-1] == "REFUND_COMPLETED"


@pytest.mark.scenario("CHAT-TS-093")
def test_system_chats_are_stored_in_the_order_events_were_confirmed(journey):
    runner = journey.apply("01071000022", "꼬붕 하나")
    journey.accept(runner)

    journey.runner_complete(runner)
    journey.orderer_confirm()
    journey.payout(runner)

    assert journey.events(runner) == ["OFFER_CREATED", "MATCHED", "RUNNER_COMPLETED", "ALL_CONFIRMED", "PAYOUT_COMPLETED"]


@pytest.mark.scenario("CHAT-TS-058")
def test_failed_event_processing_leaves_no_system_chat(journey, db, monkeypatch):
    from app.models.offer import OfferStatus
    from app.services.chat import chat_events

    runner = journey.apply("01071000023", "꼬붕 하나")
    before = journey.events(runner)
    original = chat_events.record_message_created

    def record_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("매칭 처리 중 실패")

    monkeypatch.setattr(chat_events, "record_message_created", record_then_fail)
    with pytest.raises(RuntimeError, match="매칭 처리 중 실패"):
        journey.accept(runner)
    monkeypatch.undo()

    db.rollback()
    assert db.get(Offer, journey.offer_ids[runner.id]).status == OfferStatus.WAITING
    assert journey.state(runner) == ("ACTIVE", None)
    assert journey.events(runner) == before


@pytest.mark.scenario("CHAT-TS-101")
def test_failed_cancel_rolls_back_offer_room_chat_and_outbox_event(journey, db, monkeypatch):
    from app.models.offer import OfferStatus
    from app.services.chat import chat_events

    runner = journey.apply("01071000024", "꼬붕 하나")
    events_before = len(outbox_events_for(db, "chat.message.created"))
    chats_before = journey.events(runner)
    original = chat_events.record_message_created

    def record_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("취소 처리 중 실패")

    monkeypatch.setattr(chat_events, "record_message_created", record_then_fail)
    with pytest.raises(RuntimeError, match="취소 처리 중 실패"):
        journey.cancel_offer(runner)
    monkeypatch.undo()

    db.rollback()
    assert db.get(Offer, journey.offer_ids[runner.id]).status == OfferStatus.WAITING
    assert journey.state(runner) == ("ACTIVE", None)
    assert journey.events(runner) == chats_before
    assert len(outbox_events_for(db, "chat.message.created")) == events_before


# ================================================================== 4-5 읽음과 안읽음


def read(client, factory, room_id: int, viewer, seq: int):
    return client.post(f"/v1/chat-room/{room_id}/read", json={"seq": seq}, headers=factory.headers_for(viewer))


def unread_summary(client, factory, viewer) -> dict:
    response = client.get("/v1/chat-room/unread-count", headers=factory.headers_for(viewer))
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    return {"total": data["totalUnreadCount"], **{item["roomId"]: item["unreadCount"] for item in data["rooms"]}}


def room_detail(client, factory, room_id: int, viewer) -> dict:
    response = client.get(f"/v1/chat-room/{room_id}", headers=factory.headers_for(viewer))
    assert response.status_code == 200, response.json()
    return response.json()["data"]


def add_system_chat(db, room, event) -> None:
    from app.services.chat.chat_lifecycle import ChatLifecycle

    ChatLifecycle._add_system_chat(db, room, event, event_key=f"{event.value}:test:{room.last_seq}")
    db.commit()


def close_room(db, room) -> None:
    from app.models.chat import ChatRoomStatus, ChatRoomStatusReason

    room.status = ChatRoomStatus.CLOSED
    room.status_reason = ChatRoomStatusReason.OFFER_CANCELLED
    db.commit()


# ------------------------------------------------------------------ 읽음 (CHAT-REQ-010)


@pytest.mark.scenario("CHAT-TS-030")
def test_entering_a_room_reads_everything_up_to_the_last_chat(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01073000001", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    add_user_chats(db, room, runner.id, 3)  # 시작 안내 1, 첫 인사 2, 채팅 3~5

    response = read(client, factory, room.id, sample_user, 5)

    assert response.status_code == 200, response.json()
    assert response.json()["data"] == {"roomId": room.id, "lastReadSeq": 5, "unreadCount": 0}
    assert room_detail(client, factory, room.id, sample_user)["myLastReadSeq"] == 5
    assert unread_summary(client, factory, sample_user)["total"] == 0


@pytest.mark.scenario("CHAT-TS-031")
def test_sending_a_chat_reads_everything_before_it(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01073000002", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    add_user_chats(db, room, runner.id, 2)  # 1~4

    sent = send(client, factory, room.id, sample_user, content="답장")

    assert sent.status_code == 201, sent.json()
    assert sent.json()["data"]["seq"] == 5
    assert room_detail(client, factory, room.id, sample_user)["myLastReadSeq"] == 4
    assert unread_summary(client, factory, sample_user)["total"] == 0


@pytest.mark.scenario("CHAT-TS-032")
def test_read_position_only_moves_forward(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01073000003", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    add_user_chats(db, room, runner.id, 8)  # 1~10
    assert read(client, factory, room.id, sample_user, 10).status_code == 200
    version = room_detail(client, factory, room.id, sample_user)["version"]

    late = read(client, factory, room.id, sample_user, 7)  # 늦게 도착한 이전 읽음 요청

    assert late.status_code == 200, late.json()
    assert late.json()["data"]["lastReadSeq"] == 10
    detail = room_detail(client, factory, room.id, sample_user)
    assert detail["myLastReadSeq"] == 10
    assert detail["version"] == version  # 바뀐 것이 없으면 순서 값도 그대로


@pytest.mark.scenario("CHAT-TS-033")
def test_reading_a_chat_that_is_not_in_the_room_is_rejected(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01073000004", "꼬붕 하나")
    room_a = setup_room(db, factory, sample_user, runner, title="요청 A")  # 1~2
    room_b = setup_room(db, factory, sample_user, runner, title="요청 B")
    add_user_chats(db, room_b, runner.id, 3)  # B에는 채팅 5까지 있다

    for seq in (5, 999):  # B의 채팅 순번, 없는 채팅
        response = read(client, factory, room_a.id, sample_user, seq)
        assert response.status_code == 400, response.json()
        assert response.json()["error"]["code"] == "CHAT_READ_SEQ_INVALID"
    zero = read(client, factory, room_a.id, sample_user, 0)
    assert zero.status_code == 400 and zero.json()["error"]["code"] == "VALIDATION_ERROR"
    assert room_detail(client, factory, room_a.id, sample_user)["myLastReadSeq"] == 0


@pytest.mark.scenario("CHAT-TS-034")
@pytest.mark.parametrize(
    "case",
    ["closed", pytest.param("blocked", marks=pytest.mark.skip(reason="사용자 차단 구현 후 활성화 (user-block.md)"))],
)
def test_closed_room_can_still_be_read(client, db, factory, sample_user, case):
    runner = runner_with_account(factory, "01073000005", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    close_room(db, room)

    response = read(client, factory, room.id, sample_user, 2)

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["lastReadSeq"] == 2


# ------------------------------------------------------------------ 안읽음 수 (CHAT-REQ-011)


@pytest.mark.scenario("CHAT-TS-035")
def test_unread_count_counts_partner_and_visible_system_chats_only(client, db, factory, sample_user):
    from app.models.chat import SystemChatEvent

    runner = runner_with_account(factory, "01073000006", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    assert read(client, factory, room.id, sample_user, 2).status_code == 200
    assert read(client, factory, room.id, runner, 2).status_code == 200

    add_user_chats(db, room, sample_user.id, 1)  # 행님(나)의 채팅
    add_user_chats(db, room, runner.id, 2)  # 상대 채팅 2
    add_system_chat(db, room, SystemChatEvent.MATCHED)  # 시스템 채팅 1
    add_system_chat(db, room, SystemChatEvent.NOT_SELECTED)  # 행님에게는 안읽음 제외

    assert unread_summary(client, factory, sample_user)[room.id] == 3
    # 꼬붕 기준: 행님 채팅 1 + 시스템 채팅 2 (꼬붕에게는 미선정 안내도 포함)
    assert unread_summary(client, factory, runner)[room.id] == 3


@pytest.mark.scenario("CHAT-TS-036")
def test_application_leaves_two_unread_for_orderer_and_one_for_runner(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01073000007", "꼬붕 하나")
    proposal = factory.proposal(sample_user.id, ProposalStatus.POSTED)

    offer_id = apply(client, factory, proposal, runner)

    room = room_for_offer(db, offer_id)
    assert unread_summary(client, factory, sample_user) == {"total": 2, room.id: 2}
    assert unread_summary(client, factory, runner) == {"total": 1, room.id: 1}


@pytest.mark.scenario("CHAT-TS-037")
@pytest.mark.parametrize(
    "case",
    ["active-and-closed", pytest.param("blocked", marks=pytest.mark.skip(reason="사용자 차단 구현 후 활성화 (user-block.md)"))],
)
def test_unread_summary_has_per_room_counts_and_a_total_including_closed_rooms(client, db, factory, sample_user, case):
    runner = runner_with_account(factory, "01073000008", "꼬붕 하나")
    active = setup_room(db, factory, sample_user, runner, title="요청 A")
    closed = setup_room(db, factory, sample_user, runner, title="요청 B")
    read_room = setup_room(db, factory, sample_user, runner, title="요청 C")
    add_user_chats(db, active, runner.id, 1)  # 3
    add_user_chats(db, closed, runner.id, 2)  # 4
    close_room(db, closed)
    assert read(client, factory, read_room.id, sample_user, 2).status_code == 200

    summary = unread_summary(client, factory, sample_user)

    assert summary == {"total": 7, active.id: 3, closed.id: 4}  # 다 읽은 채팅방은 목록에 없다


# ------------------------------------------------------------------ 전체 읽음 (CHAT-REQ-012)


@pytest.mark.scenario("CHAT-TS-038")
@pytest.mark.parametrize(
    "case",
    ["mixed-roles", pytest.param("blocked", marks=pytest.mark.skip(reason="사용자 차단 구현 후 활성화 (user-block.md)"))],
)
def test_read_all_reads_every_room_in_both_roles_without_touching_the_partner(client, db, factory, sample_user, case):
    runner = runner_with_account(factory, "01073000009", "꼬붕 하나")
    other_orderer = factory.user("01073000010", name="다른 행님")
    factory.settlement_account(sample_user)
    as_orderer = setup_room(db, factory, sample_user, runner, title="내 요청")
    closed = setup_room(db, factory, sample_user, runner, title="닫힌 요청")
    as_runner = setup_room(db, factory, other_orderer, sample_user, title="남의 요청")
    add_user_chats(db, as_orderer, runner.id, 2)
    add_user_chats(db, closed, runner.id, 1)
    close_room(db, closed)
    add_user_chats(db, as_runner, other_orderer.id, 3)

    response = client.post("/v1/chat-room/read-all", headers=factory.headers_for(sample_user))

    assert response.status_code == 200, response.json()
    assert response.json()["data"] == {"totalUnreadCount": 0}
    for room in (as_orderer, closed, as_runner):
        db.refresh(room)
        assert room_detail(client, factory, room.id, sample_user)["myLastReadSeq"] == room.last_seq
    # 상대방 읽음 위치는 그대로다
    assert room_detail(client, factory, as_orderer.id, runner)["myLastReadSeq"] == 0
    assert room_detail(client, factory, as_runner.id, other_orderer)["myLastReadSeq"] == 0


@pytest.mark.scenario("CHAT-TS-039")
def test_read_all_never_moves_a_room_back_behind_a_newer_read(client, db, factory, sample_user):
    from app.services.chat.chat_read_service import ChatReadService

    runner = runner_with_account(factory, "01073000011", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    add_user_chats(db, room, sample_user.id, 8)  # 1~10
    targets = ChatReadService.read_all_targets(db, runner.id)  # 전체 읽음 요청 시점: 채팅 10까지

    add_user_chats(db, room, sample_user.id, 1)  # 그 사이 채팅 11이 오고
    assert read(client, factory, room.id, runner, 11).status_code == 200  # 채팅방에 들어가 11까지 읽음

    ChatReadService.apply_read_targets(db, targets)
    db.commit()

    assert room_detail(client, factory, room.id, runner)["myLastReadSeq"] == 11


# ------------------------------------------------------------------ 상대방 읽음 표시 (CHAT-REQ-013)


@pytest.mark.scenario("CHAT-TS-040")
def test_room_detail_shows_where_the_partner_has_read_up_to(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01073000012", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    seqs = [send(client, factory, room.id, sample_user, content=f"채팅 {i}", client_message_id=f"m-{i}").json()["data"]["seq"] for i in range(3)]

    assert read(client, factory, room.id, runner, seqs[1]).status_code == 200

    assert room_detail(client, factory, room.id, sample_user)["partnerLastReadSeq"] == seqs[1]


# ================================================================== 4-6 채팅 푸시


class FakePushSender:
    """가짜 FCM 발송기. 처음 `fail_times`번은 실패한다. 성공한 발송만 `sent`에 남긴다."""

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.attempts = 0
        self.sent: list[dict] = []

    def send(self, **push):
        from app.schemas.notification import FCMSendResult

        self.attempts += 1
        if self.attempts <= self.fail_times:
            return FCMSendResult(success=False, error_code="UNAVAILABLE", error_message="FCM 일시 오류")
        self.sent.append(push)
        return FCMSendResult(success=True, message_id=f"message-{self.attempts}")

    def to(self, user) -> list[dict]:
        return [push for push in self.sent if push["token"] == f"token-{user.id}"]


class RecordingRealtime:
    """`chat.realtime` 자리의 가짜 전달 대상 (4-7 전까지)."""

    name = "chat.realtime"
    event_types = frozenset({"chat.message.created"})

    def __init__(self):
        from app.services.outbox.policy import RetryPolicy

        self.retry_policy = RetryPolicy(max_retries=0, backoff=(timedelta(seconds=5),))
        self.calls = 0

    def handle(self, envelope) -> None:
        self.calls += 1


class NoAlerts:
    def __init__(self):
        self.sent = []

    def send(self, alert) -> None:
        self.sent.append(alert)


def enable_push(db, *users) -> None:
    from app.models.user import UserFCMToken

    for user in users:
        user.alarm_enabled = True
        db.add(UserFCMToken(user_id=user.id, fcm_token=f"token-{user.id}"))
    db.commit()


def run_chat_push(sender, *extra_consumers, now: datetime | None = None) -> None:
    """outbox 처리 한 바퀴: 미발행 이벤트 발행 → 처리할 전달 실행."""
    from app.core.time import utcnow_naive
    from app.services.chat.chat_push import ChatPushConsumer
    from app.services.outbox.consumers import ConsumerRegistry
    from app.services.outbox.delivery import process_due_deliveries
    from app.services.outbox.publisher import InProcessEventPublisher
    from app.services.outbox.relay import publish_pending
    from tests.conftest import TestSessionLocal

    registry = ConsumerRegistry()
    registry.register(ChatPushConsumer(TestSessionLocal, sender))
    for consumer in extra_consumers:
        registry.register(consumer)
    now = now or utcnow_naive()
    with TestSessionLocal() as session:
        while publish_pending(session, InProcessEventPublisher(registry), now) > 0:
            pass
        # 워커처럼 처리할 전달이 없을 때까지 반복한다 (같은 채팅방은 한 번에 하나씩 집는다)
        while process_due_deliveries(session, registry, now, NoAlerts()) > 0:
            pass


def for_seq(pushes: list[dict], room_id: int, seq: int) -> list[dict]:
    return [p for p in pushes if p["data"].get("roomId") == str(room_id) and p["data"].get("seq") == str(seq)]


@pytest.mark.scenario("CHAT-TS-051")
def test_partner_chat_is_pushed_once_with_name_content_and_badge(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01074000001", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    enable_push(db, sample_user, runner)
    factory.notification(runner.id, read_at=None)  # 꼬붕의 알림 미읽음 1
    sender = FakePushSender()

    seq = send(client, factory, room.id, sample_user, content="지금 출발할게요").json()["data"]["seq"]
    run_chat_push(sender)

    pushes = for_seq(sender.sent, room.id, seq)
    assert len(pushes) == 1
    push = pushes[0]
    assert push["token"] == f"token-{runner.id}"
    assert (push["title"], push["body"]) == (sample_user.name, "지금 출발할게요")
    # 꼬붕 채팅 안읽음 합계(시작 안내 1 + 행님 채팅 1) + 알림 미읽음 1
    assert push["badge"] == 3


@pytest.mark.scenario("CHAT-TS-052")
def test_no_push_to_the_sender_or_to_someone_with_alarm_off(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01074000002", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    enable_push(db, sample_user, runner)
    runner.alarm_enabled = False
    db.commit()
    before = unread_summary(client, factory, runner).get(room.id, 0)
    sender = FakePushSender()

    seq = send(client, factory, room.id, sample_user, content="알림 꺼진 꼬붕에게").json()["data"]["seq"]
    run_chat_push(sender)

    assert for_seq(sender.sent, room.id, seq) == []  # 보낸 행님에게도, 알림 끈 꼬붕에게도 없다
    assert unread_summary(client, factory, runner)[room.id] == before + 1


@pytest.mark.scenario("CHAT-TS-053")
def test_pushes_of_one_room_share_a_collapse_key_and_open_that_room(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01074000003", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    enable_push(db, sample_user, runner)
    sender = FakePushSender()

    first = send(client, factory, room.id, runner, content="첫 번째", client_message_id="m-1").json()["data"]["seq"]
    second = send(client, factory, room.id, runner, content="두 번째", client_message_id="m-2").json()["data"]["seq"]
    run_chat_push(sender)

    pushes = for_seq(sender.sent, room.id, first) + for_seq(sender.sent, room.id, second)
    assert [p["body"] for p in pushes] == ["첫 번째", "두 번째"]
    assert {p["collapse_key"] for p in pushes} == {f"chat-room-{room.id}"}
    assert all(p["data"]["type"] == "CHAT" and p["data"]["roomId"] == str(room.id) for p in pushes)


@pytest.mark.scenario("CHAT-TS-054")
def test_chat_push_is_not_stored_as_a_notification(client, db, factory, sample_user):
    from app.models.notification import Notification

    runner = runner_with_account(factory, "01074000004", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    enable_push(db, sample_user, runner)
    before = db.query(Notification).count()
    sender = FakePushSender()

    seq = send(client, factory, room.id, runner, content="알림 목록에 없어야 해요").json()["data"]["seq"]
    run_chat_push(sender)

    assert len(for_seq(sender.sent, room.id, seq)) == 1
    db.rollback()
    assert db.query(Notification).count() == before


@pytest.mark.scenario("CHAT-TS-079")
def test_failed_push_is_retried_and_sent_once_on_success(client, db, factory, sample_user):
    from app.core.time import utcnow_naive

    runner = runner_with_account(factory, "01074000005", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    enable_push(db, sample_user, runner)
    run_chat_push(FakePushSender())  # 앞서 쌓인 지원 등록 이벤트를 먼저 끝낸다
    sender = FakePushSender(fail_times=1)
    now = utcnow_naive()

    response = send(client, factory, room.id, runner, content="재시도 확인")
    assert response.status_code == 201  # 푸시 실패와 관계없이 전송은 성공
    seq = response.json()["data"]["seq"]
    run_chat_push(sender, now=now)  # 첫 시도 실패
    assert for_seq(sender.sent, room.id, seq) == []
    run_chat_push(sender, now=now + timedelta(seconds=6))  # 5초 뒤 재시도 성공
    run_chat_push(sender, now=now + timedelta(minutes=1))  # 끝난 전달은 다시 보내지 않는다

    assert sender.attempts == 2
    assert len(for_seq(sender.sent, room.id, seq)) == 1


@pytest.mark.scenario("CHAT-TS-105")
def test_only_the_failed_push_is_retried_not_the_realtime_event(client, db, factory, sample_user):
    from app.core.time import utcnow_naive

    runner = runner_with_account(factory, "01074000006", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    enable_push(db, sample_user, runner)
    run_chat_push(FakePushSender(), RecordingRealtime())
    sender, realtime = FakePushSender(fail_times=1), RecordingRealtime()
    now = utcnow_naive()

    send(client, factory, room.id, runner, content="푸시만 다시")
    run_chat_push(sender, realtime, now=now)
    run_chat_push(sender, realtime, now=now + timedelta(seconds=6))

    assert realtime.calls == 1
    assert sender.attempts == 2
    assert len(sender.sent) == 1


@pytest.mark.scenario("CHAT-TS-091")
def test_offer_cancel_notice_is_pushed_to_both_in_their_own_wording(journey, db):
    runner = journey.apply("01074000007", "꼬붕 하나")
    enable_push(db, journey.orderer, runner)
    run_chat_push(FakePushSender())  # 지원 등록까지의 이벤트를 먼저 끝낸다
    sender = FakePushSender()

    assert journey.cancel_offer(runner).status_code == 204
    run_chat_push(sender)

    assert [(p["title"], p["body"]) for p in sender.to(journey.orderer)] == [
        ("꼬붕 하나", "꼬붕이 지원을 취소했어요. 채팅이 자동으로 종료돼요.")
    ]
    assert [(p["title"], p["body"]) for p in sender.to(runner)] == [
        (journey.orderer.name, "지원을 취소했어요. 채팅이 자동으로 종료돼요.")
    ]


@pytest.mark.scenario("CHAT-TS-092")
def test_runner_completion_uses_system_push_with_legacy_copy_for_orderer(journey, db, client, factory):
    runner = journey.apply("01074000008", "꼬붕 하나")
    journey.accept(runner)
    enable_push(db, journey.orderer, runner)
    run_chat_push(FakePushSender())
    room_id = journey.room(runner).id
    before = unread_summary(client, factory, journey.orderer).get(room_id, 0)
    sender = FakePushSender()

    assert journey.runner_complete(runner).status_code == 200
    run_chat_push(sender)

    assert [(p["title"], p["body"]) for p in sender.to(journey.orderer)] == [("꼬붕이 임무를 완료했어요! 🤝", "꼬붕이 임무를 완료했어요. 회원님도 확인해주시면 수행비가 꼬붕에게 전달돼요.")]
    assert [p["body"] for p in sender.to(runner)] == ["행님의 임무 완료 확인을 기다리고 있어요."]
    assert unread_summary(client, factory, journey.orderer)[room_id] == before + 1


# ================================================================== 4-7 실시간

ORDERER_CANCEL_TEXT = "꼬붕이 지원을 취소했어요. 채팅이 자동으로 종료돼요."
RUNNER_CANCEL_TEXT = "지원을 취소했어요. 채팅이 자동으로 종료돼요."


def ws_connect(client, user, token: str | None = None):
    from app.core.security import create_access_token

    token = token or create_access_token({"sub": user.id})
    return client.websocket_connect("/v1/chat/ws", headers={"Authorization": f"Bearer {token}"})


def run_realtime(now: datetime | None = None) -> None:
    """outbox 처리 한 바퀴를 chat.realtime만 등록해 돌린다(앱의 hub로 보낸다)."""
    from app.core.time import utcnow_naive
    from app.realtime.hub import chat_hub
    from app.services.chat.chat_realtime import ChatRealtimeConsumer
    from app.services.outbox.consumers import ConsumerRegistry
    from app.services.outbox.delivery import process_due_deliveries
    from app.services.outbox.publisher import InProcessEventPublisher
    from app.services.outbox.relay import publish_pending
    from tests.conftest import TestSessionLocal

    registry = ConsumerRegistry()
    registry.register(ChatRealtimeConsumer(TestSessionLocal, chat_hub))
    now = now or utcnow_naive()
    with TestSessionLocal() as session:
        while publish_pending(session, InProcessEventPublisher(registry), now) > 0:
            pass
        while process_due_deliveries(session, registry, now, NoAlerts()) > 0:
            pass


def received(ws, user) -> list[dict]:
    """지금까지 그 연결로 받은 이벤트. 끝 표시를 hub로 보내고 그 앞까지 모은다(ping 제외)."""
    from app.realtime.hub import chat_hub

    chat_hub.send(user.id, {"type": "test.end"})
    events = []
    while True:
        event = ws.receive_json()
        if event["type"] == "test.end":
            return events
        if event["type"] != "ping":
            events.append(event)


def of_type(events: list[dict], event_type: str, room_id: int | None = None) -> list[dict]:
    return [e for e in events if e["type"] == event_type and (room_id is None or e["roomId"] == room_id)]


# ------------------------------------------------------------------ 실시간 채팅 수신 (CHAT-REQ-015)


@pytest.mark.scenario("CHAT-TS-041")
def test_one_connection_receives_chats_from_every_room_in_both_roles(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01076000001", "꼬붕 하나")
    other_orderer = factory.user("01076000002", name="다른 행님")
    as_orderer = setup_room(db, factory, sample_user, runner, title="내 요청")
    as_runner = setup_room(db, factory, other_orderer, sample_user, title="남의 요청")

    with ws_connect(client, sample_user) as ws:
        send(client, factory, as_orderer.id, runner, content="A방 채팅", client_message_id="a-1")
        send(client, factory, as_runner.id, other_orderer, content="B방 채팅", client_message_id="b-1")
        run_realtime()
        events = of_type(received(ws, sample_user), "chat.message.created")

    contents = {(e["roomId"], e["message"]["content"]) for e in events}
    assert {(as_orderer.id, "A방 채팅"), (as_runner.id, "B방 채팅")} <= contents


@pytest.mark.scenario("CHAT-TS-042")
def test_non_participant_connection_receives_nothing(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01076000003", "꼬붕 하나")
    outsider = factory.user("01076000004", name="제3자")
    room = setup_room(db, factory, sample_user, runner)

    with ws_connect(client, outsider) as ws:
        send(client, factory, room.id, runner, content="둘만 보는 채팅")
        run_realtime()
        assert received(ws, outsider) == []


@pytest.mark.scenario("CHAT-TS-043")
def test_failed_save_sends_nothing_in_realtime(client, db, factory, sample_user, monkeypatch):
    from app.services.chat import chat_events

    runner = runner_with_account(factory, "01076000005", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    original = chat_events.record_message_created

    def record_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("저장 중 실패")

    with ws_connect(client, runner) as ws:
        run_realtime()
        received(ws, runner)  # 지원 등록 때 쌓인 이벤트는 비운다
        monkeypatch.setattr(chat_events, "record_message_created", record_then_fail)
        with pytest.raises(RuntimeError, match="저장 중 실패"):
            send(client, factory, room.id, sample_user, content="저장 안 되는 채팅")
        monkeypatch.undo()
        db.rollback()
        run_realtime()
        assert of_type(received(ws, runner), "chat.message.created") == []


@pytest.mark.scenario("CHAT-TS-044")
def test_realtime_chat_event_carries_chat_id_and_room_id(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01076000006", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)

    with ws_connect(client, runner) as ws:
        sent = send(client, factory, room.id, sample_user, content="ID 확인").json()["data"]
        run_realtime()
        events = of_type(received(ws, runner), "chat.message.created", room.id)

    event = next(e for e in events if e["message"]["seq"] == sent["seq"])
    assert event["roomId"] == room.id
    assert event["message"]["id"] == sent["id"]
    assert event["message"]["content"] == "ID 확인"


@pytest.mark.scenario("CHAT-TS-084")
def test_system_chat_arrives_in_realtime_in_each_viewers_wording(journey, client):
    runner = journey.apply("01076000007", "꼬붕 하나")
    room_id = journey.room(runner).id

    with ws_connect(client, journey.orderer) as orderer_ws, ws_connect(client, runner) as runner_ws:
        run_realtime()
        received(orderer_ws, journey.orderer)
        received(runner_ws, runner)
        assert journey.cancel_offer(runner).status_code == 204
        run_realtime()
        orderer_chats = of_type(received(orderer_ws, journey.orderer), "chat.message.created", room_id)
        runner_chats = of_type(received(runner_ws, runner), "chat.message.created", room_id)

    assert [(e["message"]["systemEvent"], e["message"]["content"]) for e in orderer_chats] == [("OFFER_CANCELLED", ORDERER_CANCEL_TEXT)]
    assert [(e["message"]["systemEvent"], e["message"]["content"]) for e in runner_chats] == [("OFFER_CANCELLED", RUNNER_CANCEL_TEXT)]


# ------------------------------------------------------------------ 연결과 재연결 (CHAT-REQ-016)


@pytest.mark.scenario("CHAT-TS-046")
@pytest.mark.parametrize("token_case", ["expired", "missing"])
def test_connection_with_expired_or_missing_token_is_refused(client, sample_user, token_case):
    from starlette.websockets import WebSocketDisconnect

    from app.core.security import create_access_token

    with pytest.raises(WebSocketDisconnect) as refused:
        if token_case == "expired":
            expired = create_access_token({"sub": sample_user.id}, expires_delta=timedelta(seconds=-1))
            with ws_connect(client, sample_user, token=expired):
                pass
        else:
            with client.websocket_connect("/v1/chat/ws"):
                pass
    assert refused.value.code == 4401


@pytest.mark.scenario("CHAT-TS-047")
def test_server_closes_the_connection_when_the_token_expires(client, sample_user):
    from starlette.websockets import WebSocketDisconnect

    from app.core.security import create_access_token

    short = create_access_token({"sub": sample_user.id}, expires_delta=timedelta(seconds=2))
    with ws_connect(client, sample_user, token=short) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            while True:
                ws.receive_json()
    assert closed.value.code == 4401


@pytest.mark.scenario("CHAT-TS-085")
@pytest.mark.parametrize("room_state", ["CLOSED", "INACTIVE"])
def test_missed_chats_after_close_or_pause_come_in_saved_order(journey, client, factory, db, room_state):
    runner = journey.apply("01076000008", "꼬붕 하나")  # 1, 2
    room = journey.room(runner)
    if room_state == "INACTIVE":
        journey.accept(runner)  # 3
        add_user_chats(db, journey.room(runner), runner.id, 2)  # 4, 5
        journey.dispute("ORDERER", runner)  # 6
        expected = "DISPUTE_RAISED"
    else:
        add_user_chats(db, journey.room(runner), runner.id, 3)  # 3~5
        journey.cancel_offer(runner)  # 6
        expected = "OFFER_CANCELLED"

    response = client.get(f"/v1/chat-room/{room.id}/messages", params={"afterSeq": 5}, headers=factory.headers_for(journey.orderer))

    assert response.status_code == 200, response.json()
    missed = response.json()["data"]["content"]
    assert [(m["seq"], m["systemEvent"]) for m in missed] == [(6, expected)]
    assert journey.state(runner)[0] == room_state


# ------------------------------------------------------------------ 상태·읽음 실시간 반영 (CHAT-REQ-017, 028)


@pytest.mark.scenario("CHAT-TS-048")
def test_matching_sends_room_updates_to_every_participant(journey, client):
    a = journey.apply("01076000009", "꼬붕 A")
    b = journey.apply("01076000010", "꼬붕 B")
    room_a, room_b = journey.room(a).id, journey.room(b).id

    with ws_connect(client, journey.orderer) as o_ws, ws_connect(client, a) as a_ws, ws_connect(client, b) as b_ws:
        journey.accept(a)
        run_realtime()
        orderer_events = of_type(received(o_ws, journey.orderer), "chat.room.updated")
        a_events = of_type(received(a_ws, a), "chat.room.updated")
        b_events = of_type(received(b_ws, b), "chat.room.updated")

    def state(event):
        return (event["roomId"], event["status"], event["statusReason"], event["proposalStatus"], event["offerStatus"])

    selected = (room_a, "ACTIVE", None, "MATCHED", "ACCEPTED")
    not_selected = (room_b, "CLOSED", "NOT_SELECTED", "MATCHED", "REJECTED")
    assert {state(e) for e in orderer_events} == {selected, not_selected}
    assert [state(e) for e in a_events] == [selected]
    assert [state(e) for e in b_events] == [not_selected]


@pytest.mark.scenario("CHAT-TS-049")
def test_reading_sends_read_position_to_partner_and_unread_counts_to_reader(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01076000011", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)
    add_user_chats(db, room, sample_user.id, 2)  # 1~4

    with ws_connect(client, sample_user) as o_ws, ws_connect(client, runner) as r_ws:
        run_realtime()
        received(o_ws, sample_user)
        received(r_ws, runner)
        assert read(client, factory, room.id, runner, 4).status_code == 200
        run_realtime()
        orderer_events = received(o_ws, sample_user)
        runner_events = received(r_ws, runner)

    [read_event] = of_type(orderer_events, "chat.read.updated", room.id)
    assert read_event["lastReadSeq"] == 4
    assert isinstance(read_event["version"], int)
    [unread_event] = of_type(runner_events, "chat.unread.updated", room.id)
    assert (unread_event["unreadCount"], unread_event["totalUnreadCount"]) == (0, 0)
    assert of_type(runner_events, "chat.read.updated") == []  # 읽은 사람에게는 읽음 위치 이벤트가 없다


@pytest.mark.scenario("CHAT-TS-050")
@pytest.mark.skip(reason="사용자 차단 구현 후 활성화 (user-block.md)")
def test_block_and_unblock_are_sent_to_both_participants():
    """한쪽이 차단 후 해제하면 양쪽이 차단 상태 변경 이벤트를 두 번 받는다."""


@pytest.mark.scenario("CHAT-TS-078")
def test_room_and_read_events_carry_an_increasing_order_value(client, db, factory, sample_user):
    runner = runner_with_account(factory, "01076000012", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner)

    with ws_connect(client, sample_user) as ws:
        read(client, factory, room.id, runner, 1)
        read(client, factory, room.id, runner, 2)
        assert client.delete(f"/v1/offer/{room.offer_id}", headers=factory.headers_for(runner)).status_code == 204
        run_realtime()
        events = [e for e in received(ws, sample_user) if e["type"] in ("chat.read.updated", "chat.room.updated")]

    assert [e["type"] for e in events] == ["chat.read.updated", "chat.read.updated", "chat.room.updated"]
    versions = [e["version"] for e in events]
    assert versions == sorted(versions) and len(set(versions)) == 3


@pytest.mark.scenario("CHAT-TS-086")
def test_runner_completion_sends_offer_status_to_both(journey, client):
    runner = journey.apply("01076000013", "꼬붕 하나")
    journey.accept(runner)
    room_id = journey.room(runner).id

    with ws_connect(client, journey.orderer) as o_ws, ws_connect(client, runner) as r_ws:
        run_realtime()
        received(o_ws, journey.orderer)
        received(r_ws, runner)
        assert journey.runner_complete(runner).status_code == 200
        run_realtime()
        both = [of_type(received(o_ws, journey.orderer), "chat.room.updated", room_id),
                of_type(received(r_ws, runner), "chat.room.updated", room_id)]

    for events in both:
        assert [(e["status"], e["offerStatus"], e["proposalStatus"]) for e in events] == [("ACTIVE", "RUNNER_COMPLETED", "MATCHED")]


# ================================================================== 4-8 중복·동시성
#
# 요청마다 새 DB 세션을 쓰는 클라이언트로 실제로 동시에 보낸다. 두 요청이 "검사를 마치고 상태를 바꾸기 직전"에
# 서로를 기다리게(최대 1초) 해서, 잠금이 없으면 둘 다 같은 옛 상태로 검사를 통과하게 만든다.
# 잠금이 있으면 뒤 요청은 앞 요청이 커밋할 때까지 잠금에서 기다리므로 만나지 못하고 1초 뒤 각자 진행한다.

import threading  # noqa: E402

from app.models.offer import OfferStatus  # noqa: E402


class Parallel:
    """요청마다 새 세션을 쓰는 API 호출 도우미."""

    __test__ = False

    def __init__(self, factory, admin_headers):
        self.factory = factory
        self.admin_headers = admin_headers

    def _client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def call(self, method: str, url: str, user=None, json=None, headers=None):
        headers = headers or (self.factory.headers_for(user) if user is not None else {})
        return self._client().request(method, url, json=json, headers=headers)

    def at_once(self, *requests):
        """(method, url, user, json[, headers]) 여러 개를 동시에 보내고 응답을 순서대로 돌려준다."""
        # 헤더는 메인 스레드에서 만든다. 스레드에서 테스트 세션의 객체를 건드리면 세션을 함께 쓰게 된다.
        prepared = []
        for method, url, user, json, *rest in requests:
            headers = rest[0] if rest else self.factory.headers_for(user)
            prepared.append((method, url, None, json, headers))
        responses = [None] * len(requests)
        start = threading.Barrier(len(requests))

        def run(index, request):
            start.wait()
            responses[index] = self.call(*request)

        threads = [threading.Thread(target=run, args=(i, r)) for i, r in enumerate(prepared)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return responses


@pytest.fixture
def parallel(db, factory, admin_headers, admin_alerts, sms_sender, monkeypatch):
    """`client` fixture와 같은 가짜(알림 워커·SMS)를 쓰되, DB 세션만 요청마다 새로 연다."""
    from app.core.database import get_db
    from app.main import app
    from app.services.sms_service import get_sms_sender
    from tests.conftest import NoopNotificationWorker, TestSessionLocal

    def new_session():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    for target in (
        "app.main.get_notification_worker",
        "app.api.v1.offer.offer_router.get_notification_worker",
        "app.api.v1.proposal.proposal_router.get_notification_worker",
        "app.api.v1.admin.admin_router.get_notification_worker",
    ):
        monkeypatch.setattr(target, lambda: NoopNotificationWorker())
    app.dependency_overrides[get_db] = new_session
    app.dependency_overrides[get_sms_sender] = lambda: sms_sender
    yield Parallel(factory, admin_headers)
    app.dependency_overrides.clear()


def meet_before(monkeypatch, *targets) -> None:
    """두 요청이 (클래스, 메서드) 중 하나를 부르기 직전에 서로를 최대 1초 기다리게 한다."""
    barrier = threading.Barrier(2, timeout=1.0)
    for cls, name in targets:
        original = getattr(cls, name)

        def wrapper(self, *args, __original=original, **kwargs):
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
            return __original(self, *args, **kwargs)

        monkeypatch.setattr(cls, name, wrapper)


def fresh_room(db, offer_id: int):
    db.rollback()  # 다른 세션이 커밋한 결과를 읽는다
    return room_for_offer(db, offer_id)


def system_events(db, room_id: int) -> list[str]:
    from app.models.chat import ChatMessage, ChatMessageType

    db.rollback()
    rows = (
        db.query(ChatMessage.system_event)
        .filter(ChatMessage.room_id == room_id, ChatMessage.type == ChatMessageType.SYSTEM)
        .order_by(ChatMessage.seq)
        .all()
    )
    return [row[0].value for row in rows]


def open_proposal(factory, orderer):
    return factory.proposal(orderer.id, ProposalStatus.POSTED)


def p_apply(parallel, proposal, runner) -> int:
    response = parallel.call("POST", "/v1/offer", runner, {"proposalId": proposal.id, "greeting": GREETING})
    assert response.status_code == 201, response.json()
    return response.json()["data"]["id"]


def p_accept(parallel, offer_id, orderer):
    response = parallel.call("POST", f"/v1/offer/{offer_id}/accept", orderer)
    assert response.status_code == 201, response.json()


def dispute_question(db, target: str) -> int:
    from app.models.dispute_survey import DisputeSurveyQuestion, DisputeSurveyTargetType

    question = DisputeSurveyQuestion(
        target_type=DisputeSurveyTargetType(target), question_text="문제가 있었어요", display_order=1, is_active=True, requires_detail=False
    )
    db.add(question)
    db.commit()
    return question.id


def statuses(responses) -> list[int]:
    return sorted(r.status_code for r in responses)


@pytest.mark.scenario("CHAT-TS-068")
def test_same_runner_applying_twice_at_once_leaves_one_of_everything(parallel, db, factory, sample_user):
    from app.models.chat import ChatMessage, ChatRoom

    runner = runner_with_account(factory, "01077000001", "꼬붕 하나")
    proposal = open_proposal(factory, sample_user)
    body = {"proposalId": proposal.id, "greeting": GREETING}

    responses = parallel.at_once(("POST", "/v1/offer", runner, body), ("POST", "/v1/offer", runner, body))

    assert statuses(responses) == [201, 409]
    db.rollback()
    offers = db.query(Offer).filter(Offer.proposal_id == proposal.id).all()
    assert len(offers) == 1
    rooms = db.query(ChatRoom).filter(ChatRoom.proposal_id == proposal.id).all()
    assert len(rooms) == 1
    kinds = [(m.type.value, m.system_event.value if m.system_event else None) for m in db.query(ChatMessage).filter(ChatMessage.room_id == rooms[0].id).order_by(ChatMessage.seq)]
    assert kinds == [("SYSTEM", "OFFER_CREATED"), ("USER", None)]


@pytest.mark.scenario("CHAT-TS-070")
def test_chats_sent_at_once_by_both_get_distinct_gapless_seqs(parallel, db, factory, sample_user):
    runner = runner_with_account(factory, "01077000002", "꼬붕 하나")
    offer_id = p_apply(parallel, open_proposal(factory, sample_user), runner)
    room = fresh_room(db, offer_id)
    requests = [
        ("POST", f"/v1/chat-room/{room.id}/messages", user, {"clientMessageId": f"{tag}-{i}", "content": f"{tag} {i}"})
        for i in range(4)
        for user, tag in ((sample_user, "o"), (runner, "r"))
    ]

    responses = parallel.at_once(*requests)

    assert all(r.status_code == 201 for r in responses), [r.json() for r in responses]
    seqs = sorted(r.json()["data"]["seq"] for r in responses)
    assert seqs == list(range(3, 11))  # 1·2는 지원 등록 안내·첫 인사
    after = parallel.call("GET", f"/v1/chat-room/{room.id}/messages", sample_user).json()["data"]["content"]
    assert [m["seq"] for m in after] == list(range(1, 11))


@pytest.mark.scenario("CHAT-TS-071")
def test_chat_racing_with_room_close_never_lands_after_the_close_notice(parallel, db, factory, sample_user, monkeypatch):
    from app.models.chat import ChatMessage, ChatMessageType

    runner = runner_with_account(factory, "01077000003", "꼬붕 하나")
    offer_id = p_apply(parallel, open_proposal(factory, sample_user), runner)
    room = fresh_room(db, offer_id)

    send_response, cancel_response = parallel.at_once(
        ("POST", f"/v1/chat-room/{room.id}/messages", sample_user, {"clientMessageId": "race-1", "content": "마지막 채팅"}),
        ("DELETE", f"/v1/offer/{offer_id}", runner, None),
    )

    assert cancel_response.status_code == 204
    assert send_response.status_code in (201, 409)
    db.rollback()
    chats = db.query(ChatMessage).filter(ChatMessage.room_id == room.id).order_by(ChatMessage.seq).all()
    close_seq = next(m.seq for m in chats if m.system_event and m.system_event.value == "OFFER_CANCELLED")
    assert not [m for m in chats if m.type == ChatMessageType.USER and m.seq > close_seq]


@pytest.mark.scenario("CHAT-TS-072")
def test_matching_two_runners_at_once_matches_only_one(parallel, db, factory, sample_user, monkeypatch):
    from app.models.chat import ChatRoom, ChatRoomStatus

    proposal = open_proposal(factory, sample_user)
    a = p_apply(parallel, proposal, runner_with_account(factory, "01077000004", "꼬붕 A"))
    b = p_apply(parallel, proposal, runner_with_account(factory, "01077000005", "꼬붕 B"))
    meet_before(monkeypatch, (Offer, "accept"))

    responses = parallel.at_once(
        ("POST", f"/v1/offer/{a}/accept", sample_user, None),
        ("POST", f"/v1/offer/{b}/accept", sample_user, None),
    )

    assert statuses(responses) == [201, 409], [r.json() for r in responses]
    db.rollback()
    accepted = db.query(Offer).filter(Offer.proposal_id == proposal.id, Offer.status == OfferStatus.ACCEPTED).count()
    assert accepted == 1
    active = db.query(ChatRoom).filter(ChatRoom.proposal_id == proposal.id, ChatRoom.status == ChatRoomStatus.ACTIVE).count()
    assert active == 1


@pytest.mark.scenario("CHAT-TS-073")
def test_matching_and_runner_cancel_at_once_settle_on_one(parallel, db, factory, sample_user, monkeypatch):
    runner = runner_with_account(factory, "01077000006", "꼬붕 하나")
    offer_id = p_apply(parallel, open_proposal(factory, sample_user), runner)
    meet_before(monkeypatch, (Offer, "accept"), (Offer, "cancel"))

    accept, cancel = parallel.at_once(
        ("POST", f"/v1/offer/{offer_id}/accept", sample_user, None),
        ("DELETE", f"/v1/offer/{offer_id}", runner, None),
    )

    assert sorted([accept.status_code, cancel.status_code]) in ([201, 409], [204, 409]), (accept.json(), cancel.status_code)
    room = fresh_room(db, offer_id)
    events = system_events(db, room.id)
    assert not {"MATCHED", "OFFER_CANCELLED"} <= set(events)
    if accept.status_code == 201:
        assert (room.status.value, events[-1]) == ("ACTIVE", "MATCHED")
    else:
        assert (room.status.value, events[-1]) == ("CLOSED", "OFFER_CANCELLED")


@pytest.mark.scenario("CHAT-TS-074")
def test_both_completions_at_once_close_the_room_once(parallel, db, factory, sample_user, monkeypatch):
    from app.models.proposal import Proposal

    runner = runner_with_account(factory, "01077000007", "꼬붕 하나")
    proposal = open_proposal(factory, sample_user)
    offer_id = p_apply(parallel, proposal, runner)
    p_accept(parallel, offer_id, sample_user)
    meet_before(monkeypatch, (Offer, "confirm_runner_completion"), (Proposal, "confirm_orderer_completion"))

    responses = parallel.at_once(
        ("POST", f"/v1/offer/{offer_id}/complete-delivery", runner, None),
        ("POST", f"/v1/proposal/{proposal.id}/confirm-received", sample_user, None),
    )

    assert [r.status_code for r in responses] == [200, 200], [r.json() for r in responses]
    db.rollback()
    assert db.get(Proposal, proposal.id).status == ProposalStatus.ALL_COMPLETED
    assert db.get(Offer, offer_id).status == OfferStatus.ALL_COMPLETED
    room = fresh_room(db, offer_id)
    assert (room.status.value, room.status_reason.value) == ("CLOSED", "ALL_CONFIRMED")
    events = system_events(db, room.id)
    assert events.count("ALL_CONFIRMED") == 1
    assert events[-1] == "ALL_CONFIRMED"


@pytest.mark.scenario("CHAT-TS-075")
def test_late_dispute_or_status_change_never_reopens_a_closed_room(parallel, db, factory, sample_user):
    from app.models.chat import ChatRole
    from app.services.chat.chat_lifecycle import ChatLifecycle

    runner = runner_with_account(factory, "01077000008", "꼬붕 하나")
    offer_id = p_apply(parallel, open_proposal(factory, sample_user), runner)
    assert parallel.call("DELETE", f"/v1/offer/{offer_id}", runner).status_code == 204
    room = fresh_room(db, offer_id)
    before = system_events(db, room.id)

    offer = db.get(Offer, offer_id)
    ChatLifecycle.on_dispute_raised(db, offer, raised_by=ChatRole.ORDERER)  # 늦게 도착한 분쟁 접수
    ChatLifecycle.on_offer_accepted(db, offer)  # 늦게 도착한 매칭
    ChatLifecycle.on_runner_completed(db, offer, all_confirmed=False)
    db.commit()

    room = fresh_room(db, offer_id)
    assert (room.status.value, room.status_reason.value) == ("CLOSED", "OFFER_CANCELLED")
    assert system_events(db, room.id) == before


@pytest.mark.scenario("CHAT-TS-076")
def test_two_reads_at_once_keep_the_furthest_position(parallel, db, factory, sample_user):
    runner = runner_with_account(factory, "01077000009", "꼬붕 하나")
    offer_id = p_apply(parallel, open_proposal(factory, sample_user), runner)
    room = fresh_room(db, offer_id)
    add_user_chats(db, room, runner.id, 8)  # 1~10

    responses = parallel.at_once(
        ("POST", f"/v1/chat-room/{room.id}/read", sample_user, {"seq": 5}),
        ("POST", f"/v1/chat-room/{room.id}/read", sample_user, {"seq": 9}),
    )

    assert [r.status_code for r in responses] == [200, 200]
    assert fresh_room(db, offer_id).orderer_last_read_seq == 9


@pytest.mark.scenario("CHAT-TS-077")
def test_chat_saved_after_the_read_target_stays_unread(parallel, db, factory, sample_user):
    runner = runner_with_account(factory, "01077000010", "꼬붕 하나")
    offer_id = p_apply(parallel, open_proposal(factory, sample_user), runner)
    room = fresh_room(db, offer_id)
    add_user_chats(db, room, runner.id, 7)  # 1~9 (앱은 채팅 9까지 봤다)
    add_user_chats(db, fresh_room(db, offer_id), runner.id, 1)  # 그 사이 채팅 10 저장

    response = parallel.call("POST", f"/v1/chat-room/{room.id}/read", sample_user, {"seq": 9})

    assert response.status_code == 200
    assert response.json()["data"] == {"roomId": room.id, "lastReadSeq": 9, "unreadCount": 1}


@pytest.mark.scenario("CHAT-TS-095")
@pytest.mark.parametrize("canceller", ["orderer", "admin"])
def test_matching_racing_with_a_cancel_follows_only_the_winner(parallel, db, factory, sample_user, monkeypatch, canceller):
    from app.models.proposal import Proposal

    runner = runner_with_account(factory, "01077000011", "꼬붕 하나")
    proposal = open_proposal(factory, sample_user)
    offer_id = p_apply(parallel, proposal, runner)
    meet_before(monkeypatch, (Offer, "accept"), (Proposal, "cancel"), (Proposal, "mark_refund_pending"))
    if canceller == "orderer":
        cancel_request = ("POST", f"/v1/proposal/{proposal.id}/cancel", sample_user, None)
    else:
        cancel_request = ("POST", f"/v1/admin/proposal/{proposal.id}/cancel", None, {"adminNote": "운영 취소"}, parallel.admin_headers)

    accept, cancel = parallel.at_once(("POST", f"/v1/offer/{offer_id}/accept", sample_user, None), cancel_request)

    assert accept.status_code in (201, 409) and cancel.status_code in (200, 409), (accept.json(), cancel.json())
    room = fresh_room(db, offer_id)
    events = system_events(db, room.id)
    if accept.status_code == 201 and cancel.status_code == 200:
        # 매칭이 먼저 확정되고, 관리자 취소가 매칭 후 취소로 처리됐다
        assert canceller == "admin"
        assert events == ["OFFER_CREATED", "MATCHED", "ADMIN_CANCELLED_AFTER_MATCH"]
    elif accept.status_code == 201:
        assert (room.status.value, events) == ("ACTIVE", ["OFFER_CREATED", "MATCHED"])
    else:
        assert cancel.status_code == 200
        assert room.status.value == "CLOSED"
        assert events == ["OFFER_CREATED", "PROPOSAL_CANCELLED"]


@pytest.mark.scenario("CHAT-TS-096")
def test_completion_racing_with_a_dispute_applies_in_a_valid_order(parallel, db, factory, sample_user, monkeypatch):
    from app.models.proposal import Proposal

    runner = runner_with_account(factory, "01077000012", "꼬붕 하나")
    proposal = open_proposal(factory, sample_user)
    offer_id = p_apply(parallel, proposal, runner)
    p_accept(parallel, offer_id, sample_user)
    question_id = dispute_question(db, "ORDER")
    meet_before(monkeypatch, (Offer, "confirm_runner_completion"), (Proposal, "raise_dispute"))

    complete, dispute = parallel.at_once(
        ("POST", f"/v1/offer/{offer_id}/complete-delivery", runner, None),
        ("POST", f"/v1/proposal/{proposal.id}/dispute", sample_user, {"reasonQuestionId": question_id, "detailReason": "물건이 달라요"}),
    )

    assert dispute.status_code == 200, dispute.json()
    assert complete.status_code in (200, 409), complete.json()
    room = fresh_room(db, offer_id)
    assert (room.status.value, room.status_reason.value) == ("INACTIVE", "ORDERER_DISPUTED")
    events = system_events(db, room.id)
    if complete.status_code == 200:
        assert events == ["OFFER_CREATED", "MATCHED", "RUNNER_COMPLETED", "DISPUTE_RAISED"]
    else:
        assert events == ["OFFER_CREATED", "MATCHED", "DISPUTE_RAISED"]


@pytest.mark.scenario("CHAT-TS-097")
def test_chat_saved_while_read_all_runs_stays_unread(parallel, db, factory, sample_user, monkeypatch):
    from app.services.chat.chat_read_service import ChatReadService

    runner = runner_with_account(factory, "01077000013", "꼬붕 하나")
    offer_id = p_apply(parallel, open_proposal(factory, sample_user), runner)
    room = fresh_room(db, offer_id)
    add_user_chats(db, room, runner.id, 8)  # 1~10
    targets_taken, chat_saved = threading.Event(), threading.Event()
    original_targets = ChatReadService.read_all_targets
    original_apply = ChatReadService.apply_read_targets

    def take_targets(*args, **kwargs):
        targets = original_targets(*args, **kwargs)
        targets_taken.set()
        return targets

    def apply_after_chat(*args, **kwargs):
        chat_saved.wait(timeout=5)  # 전체 읽음 처리 중에 채팅 11이 저장된다
        return original_apply(*args, **kwargs)

    monkeypatch.setattr(ChatReadService, "read_all_targets", staticmethod(take_targets))
    monkeypatch.setattr(ChatReadService, "apply_read_targets", staticmethod(apply_after_chat))

    result = {}
    orderer_headers = factory.headers_for(sample_user)
    worker = threading.Thread(
        target=lambda: result.setdefault("read_all", parallel.call("POST", "/v1/chat-room/read-all", headers=orderer_headers))
    )
    worker.start()
    assert targets_taken.wait(timeout=5)
    sent = parallel.call("POST", f"/v1/chat-room/{room.id}/messages", runner, {"clientMessageId": "late-11", "content": "채팅 11"})
    chat_saved.set()
    worker.join(timeout=10)

    assert sent.status_code == 201 and sent.json()["data"]["seq"] == 11
    assert result["read_all"].status_code == 200
    assert fresh_room(db, offer_id).orderer_last_read_seq == 10
    unread = parallel.call("GET", "/v1/chat-room/unread-count", sample_user).json()["data"]
    assert unread["totalUnreadCount"] == 1


# ================================================================== 4-9 관리자 조회·기존 지원 채팅방 생성


@pytest.mark.scenario("CHAT-TS-007")
def test_admin_can_read_rooms_and_chats_but_not_send_or_change_read_positions(client, db, factory, sample_user, admin_headers):
    runner = runner_with_account(factory, "01078000001", "꼬붕 하나")
    room = setup_room(db, factory, sample_user, runner, title="관리자 조회 요청")
    add_user_chats(db, room, sample_user.id, 2)  # 3, 4
    assert read(client, factory, room.id, runner, 3).status_code == 200
    before = (room_detail(client, factory, room.id, sample_user)["myLastReadSeq"], room_detail(client, factory, room.id, runner)["myLastReadSeq"])

    rooms = client.get("/v1/admin/chat-room", params={"proposalId": room.proposal_id}, headers=admin_headers)
    chats = client.get(f"/v1/admin/chat-room/{room.id}/messages", headers=admin_headers)
    sent = client.post(
        f"/v1/chat-room/{room.id}/messages", json={"clientMessageId": "admin-1", "content": "관리자 채팅"}, headers=admin_headers
    )

    assert rooms.status_code == 200, rooms.json()
    [item] = rooms.json()["data"]
    assert (item["id"], item["offerId"], item["ordererName"], item["runnerName"], item["status"]) == (
        room.id, room.offer_id, sample_user.name, "꼬붕 하나", "ACTIVE"
    )
    assert (item["ordererLastReadSeq"], item["runnerLastReadSeq"]) == (0, 3)
    assert chats.status_code == 200, chats.json()
    content = chats.json()["data"]["content"]
    assert [m["seq"] for m in content] == [1, 2, 3, 4]
    system = content[0]
    assert (system["systemEvent"], system["content"], system["runnerContent"]) == ("OFFER_CREATED", OFFER_CREATED_TEXT, "지원이 정상적으로 접수됐어요. 행님의 선택을 기다려주세요.")
    assert (content[1]["senderRole"], content[1]["content"]) == ("RUNNER", GREETING)
    assert sent.status_code == 403
    assert sent.json()["error"]["code"] == "FORBIDDEN"
    after = (room_detail(client, factory, room.id, sample_user)["myLastReadSeq"], room_detail(client, factory, room.id, runner)["myLastReadSeq"])
    assert after == before
    assert message_count(db, room.id) == 4
    # 관리자가 아닌 사용자는 관리자 API를 쓸 수 없다
    assert client.get("/v1/admin/chat-room", params={"proposalId": room.proposal_id}, headers=factory.headers_for(sample_user)).status_code == 403


def backfill_chat_rooms(connection) -> None:
    """배포 때 실행하는 데이터 마이그레이션(0037)의 채팅방 생성 함수를 그대로 부른다."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0037_backfill_chat_rooms.py"
    spec = importlib.util.spec_from_file_location("backfill_chat_rooms_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.backfill_chat_rooms(connection)


@pytest.mark.scenario("CHAT-TS-069")
def test_backfill_creates_one_room_per_existing_offer_matching_its_status(db, factory, sample_user):
    from app.models.chat import ChatMessage, ChatRoom
    from app.models.mission import MissionResolution, MissionStatus
    from tests.conftest import TEST_ENGINE

    def runner(phone):
        return factory.user(phone, name=f"꼬붕 {phone[-2:]}")

    waiting_p = factory.proposal(sample_user.id, ProposalStatus.OFFERED, title="대기")
    waiting = factory.offer(waiting_p.id, runner("01078000010").id)

    matched_p = factory.proposal(sample_user.id, ProposalStatus.MATCHED, title="매칭")
    accepted = factory.offer(matched_p.id, runner("01078000011").id, OfferStatus.ACCEPTED)
    factory.mission(matched_p, accepted)
    not_selected = factory.offer(matched_p.id, runner("01078000012").id, OfferStatus.REJECTED)

    disputed_p = factory.proposal(sample_user.id, ProposalStatus.DISPUTED, title="분쟁")
    disputed = factory.offer(disputed_p.id, runner("01078000013").id, OfferStatus.DISPUTED)
    factory.mission(disputed_p, disputed, MissionStatus.DISPUTED)
    factory.dispute_evidence(disputed_p, disputed, actor_id=sample_user.id)  # 행님이 접수

    done_p = factory.proposal(sample_user.id, ProposalStatus.ALL_COMPLETED, title="완료")
    done = factory.offer(done_p.id, runner("01078000014").id, OfferStatus.ALL_COMPLETED)
    factory.mission(done_p, done, MissionStatus.COMPLETED)

    failed_p = factory.proposal(sample_user.id, ProposalStatus.REFUND_PENDING, title="분쟁 실패")
    failed = factory.offer(failed_p.id, runner("01078000015").id, OfferStatus.CANCELLED)
    factory.mission(failed_p, failed, MissionStatus.FAILED, resolution=MissionResolution.FAILED.value)

    cancelled_p = factory.proposal(sample_user.id, ProposalStatus.OFFERED, title="지원 취소")
    cancelled = factory.offer(cancelled_p.id, runner("01078000016").id, OfferStatus.CANCELLED)

    withdrawn_p = factory.proposal(sample_user.id, ProposalStatus.CANCELLED, title="요청 취소")
    rejected_by_cancel = factory.offer(withdrawn_p.id, runner("01078000017").id, OfferStatus.REJECTED)

    already = setup_room(db, factory, sample_user, runner_with_account(factory, "01078000018", "꼬붕 기존"), title="이미 있음")
    messages_before = db.query(ChatMessage).count()

    for _ in range(2):  # 두 번 실행해도 결과가 같다
        with TEST_ENGINE.begin() as connection:
            backfill_chat_rooms(connection)

    db.rollback()
    expected = {
        waiting.id: ("ACTIVE", None),
        accepted.id: ("ACTIVE", None),
        not_selected.id: ("CLOSED", "NOT_SELECTED"),
        disputed.id: ("INACTIVE", "ORDERER_DISPUTED"),
        done.id: ("CLOSED", "ALL_CONFIRMED"),
        failed.id: ("CLOSED", "DISPUTE_FAILED"),
        cancelled.id: ("CLOSED", "OFFER_CANCELLED"),
        rejected_by_cancel.id: ("CLOSED", "PROPOSAL_CANCELLED"),
        already.offer_id: ("ACTIVE", None),
    }
    rooms = db.query(ChatRoom).all()
    assert sorted(r.offer_id for r in rooms) == sorted(expected)  # 지원마다 1개
    for room in rooms:
        state = (room.status.value, room.status_reason.value if room.status_reason else None)
        assert state == expected[room.offer_id], room.offer_id
        assert room.last_seq == (2 if room.offer_id == already.offer_id else 0)
    assert db.query(ChatMessage).count() == messages_before  # 시스템 채팅은 생기지 않는다


@pytest.mark.scenario("CHAT-TS-099")
def test_new_offer_during_backfill_gets_exactly_one_room_with_its_chats(parallel, db, factory, sample_user):
    import time

    from app.models.chat import ChatMessage, ChatRoom
    from tests.conftest import TEST_ENGINE

    legacy_p = factory.proposal(sample_user.id, ProposalStatus.OFFERED, title="기존")
    legacy = factory.offer(legacy_p.id, factory.user("01078000020", name="기존 꼬붕").id)
    proposal = open_proposal(factory, sample_user)
    runner = runner_with_account(factory, "01078000021", "새 꼬붕")
    headers = factory.headers_for(runner)
    result = {}

    with TEST_ENGINE.connect() as connection:
        transaction = connection.begin()
        backfill_chat_rooms(connection)  # 생성 작업이 커밋하기 전에
        worker = threading.Thread(
            target=lambda: result.setdefault(
                "apply", parallel.call("POST", "/v1/offer", json={"proposalId": proposal.id, "greeting": GREETING}, headers=headers)
            )
        )
        worker.start()  # 새 지원이 들어온다
        time.sleep(0.5)
        transaction.commit()
    worker.join(timeout=30)

    assert result["apply"].status_code == 201, result["apply"].json()
    new_offer_id = result["apply"].json()["data"]["id"]
    with TEST_ENGINE.begin() as connection:
        backfill_chat_rooms(connection)  # 생성 작업을 한 번 더 돌려도 새 지원 채팅방은 그대로
    db.rollback()
    [new_room] = db.query(ChatRoom).filter(ChatRoom.offer_id == new_offer_id).all()
    kinds = [(m.type.value, m.system_event.value if m.system_event else None) for m in db.query(ChatMessage).filter(ChatMessage.room_id == new_room.id).order_by(ChatMessage.seq)]
    assert kinds == [("SYSTEM", "OFFER_CREATED"), ("USER", None)]
    assert db.query(ChatRoom).filter(ChatRoom.offer_id == legacy.id).count() == 1
