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
