"""채팅 통합 테스트 (API + MySQL, tests/conftest.py 의 client/db fixture 사용).

시나리오 정본: docs/domains/chat/test-scenarios.md 의 CHAT-TS-*
TDD 흐름: docs/design-docs/tdd-workflow.md
"""

from __future__ import annotations

import pytest

from app.models.offer import Offer
from app.models.proposal import Proposal, ProposalStatus

GREETING = "안녕하세요! 근처에 있어서 바로 갈 수 있어요."
OFFER_CREATED_TEXT = "지원으로 채팅이 시작됐어요."


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
        assert chats[0]["content"] == OFFER_CREATED_TEXT
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
    sent_at = datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00"))
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

    assert runner_item["lastMessage"]["content"] == "이번에는 매칭되지 않았어요. 채팅이 자동으로 종료돼요."
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
