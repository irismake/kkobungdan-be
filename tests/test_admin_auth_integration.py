"""관리자 인증·인가 통합 테스트."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.password import hash_password, verify_password
from app.core.time import utcnow_naive
from app.models.proposal import ProposalStatus
from app.models.user import User
from app.services.admin.admin_auth_service import ADMIN_LOGIN_MAX_ATTEMPTS, AdminAuthService


ADMIN_PATHS = [
    ("get", "/v1/admin/summary"),
    ("get", "/v1/admin/proposal"),
    ("get", "/v1/admin/offer"),
    ("get", "/v1/admin/dispute"),
    ("get", "/v1/admin/refund"),
    ("get", "/v1/admin/payout"),
    ("get", "/v1/admin/missions"),
    ("get", "/v1/admin/proposal-reports"),
]


@pytest.mark.scenario("ADMIN-TS-082")
@pytest.mark.parametrize("method,path", ADMIN_PATHS)
def test_admin_paths_reject_missing_token(client, method, path):
    response = getattr(client, method)(path)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.scenario("ADMIN-TS-083")
@pytest.mark.parametrize("method,path", ADMIN_PATHS)
def test_admin_paths_reject_non_admin_user(client, auth_headers, method, path):
    response = getattr(client, method)(path, headers=auth_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.scenario("ADMIN-TS-084")
@pytest.mark.parametrize("method,path", ADMIN_PATHS)
def test_admin_paths_accept_admin_token(client, admin_headers, method, path):
    response = getattr(client, method)(path, headers=admin_headers)

    assert response.status_code == 200


@pytest.mark.scenario("ADMIN-TS-085")
def test_admin_mutation_rejects_non_admin_user(client, factory, sample_user, auth_headers):
    proposal = factory.proposal(sample_user.id, ProposalStatus.HOLDING)

    response = client.post(
        f"/v1/admin/proposal/{proposal.id}/confirm-payment",
        json={"openChatUrl": "https://open.kakao.com/o/example"},
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.scenario("ADMIN-TS-086")
def test_login_issues_tokens_for_admin(client, admin_user):
    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["userId"] == admin_user.id
    assert data["tokenType"] == "Bearer"
    assert data["accessToken"]

    authorized = client.get("/v1/admin/summary", headers={"Authorization": f"Bearer {data['accessToken']}"})
    assert authorized.status_code == 200


@pytest.mark.scenario("ADMIN-TS-087")
def test_login_rejects_wrong_password(client, admin_user):
    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ADMIN_CREDENTIALS_INVALID"


@pytest.mark.scenario("ADMIN-TS-088")
def test_login_rejects_unknown_username_with_same_error(client, admin_user):
    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "nobody", "password": "admin-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ADMIN_CREDENTIALS_INVALID"


def _fail_login(client, times: int) -> None:
    for _ in range(times):
        client.post("/v1/admin/auth/login", json={"username": "admin", "password": "wrong-password"})


@pytest.mark.scenario("ADMIN-TS-089")
def test_login_locks_account_after_repeated_failures(client, admin_user):
    _fail_login(client, ADMIN_LOGIN_MAX_ATTEMPTS)

    # 잠금 중에는 올바른 비밀번호도 거절한다. 그러지 않으면 잠금 응답만으로
    # 비밀번호가 맞았는지 아닌지를 구분할 수 있게 된다.
    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "ADMIN_LOGIN_LOCKED"


@pytest.mark.scenario("ADMIN-TS-090")
def test_login_allows_attempts_below_the_limit(client, admin_user):
    _fail_login(client, ADMIN_LOGIN_MAX_ATTEMPTS - 1)

    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )

    assert response.status_code == 200


@pytest.mark.scenario("ADMIN-TS-091")
def test_successful_login_resets_failure_count(client, db, admin_user):
    _fail_login(client, ADMIN_LOGIN_MAX_ATTEMPTS - 1)
    client.post("/v1/admin/auth/login", json={"username": "admin", "password": "admin-password"})

    db.refresh(admin_user)
    assert admin_user.admin_login_failed_count == 0
    assert admin_user.admin_locked_until is None


@pytest.mark.scenario("ADMIN-TS-092")
def test_lock_expires_after_the_lock_duration(client, db, admin_user):
    _fail_login(client, ADMIN_LOGIN_MAX_ATTEMPTS)

    admin_user.admin_locked_until = utcnow_naive() - timedelta(seconds=1)
    db.commit()

    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )

    assert response.status_code == 200


@pytest.mark.scenario("ADMIN-TS-093")
def test_unknown_username_does_not_lock_the_admin(client, admin_user):
    _fail_login_unknown = [
        client.post("/v1/admin/auth/login", json={"username": "nobody", "password": "x"})
        for _ in range(ADMIN_LOGIN_MAX_ATTEMPTS + 2)
    ]
    assert all(response.status_code == 401 for response in _fail_login_unknown)

    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )

    assert response.status_code == 200


@pytest.mark.scenario("ADMIN-TS-094")
def test_login_rejects_non_admin_account(client, db, sample_user):
    sample_user.admin_username = "notadmin"
    sample_user.password_hash = hash_password("admin-password")
    db.commit()

    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "notadmin", "password": "admin-password"},
    )

    assert response.status_code == 401


@pytest.mark.scenario("ADMIN-TS-095")
def test_refresh_token_from_admin_login_works(client, admin_user):
    login = client.post(
        "/v1/admin/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )
    refresh_token = login.json()["data"]["refreshToken"]

    refreshed = client.post("/v1/auth/refresh", json={"refreshToken": refresh_token})

    assert refreshed.status_code == 200
    access_token = refreshed.json()["data"]["accessToken"]
    assert client.get("/v1/admin/summary", headers={"Authorization": f"Bearer {access_token}"}).status_code == 200


@pytest.mark.scenario("ADMIN-TS-096")
def test_ensure_admin_account_creates_once_and_keeps_password(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "bootstrap-admin")
    monkeypatch.setattr(settings, "admin_initial_password", "first-password")

    created = AdminAuthService.ensure_admin_account(db)

    assert created is not None
    assert created.is_admin is True
    assert verify_password("first-password", created.password_hash)

    # 환경변수를 바꿔도 이미 있는 계정의 비밀번호는 덮어쓰지 않는다.
    monkeypatch.setattr(settings, "admin_initial_password", "second-password")
    again = AdminAuthService.ensure_admin_account(db)

    assert again.id == created.id
    assert verify_password("first-password", again.password_hash)
    assert db.query(User).filter(User.admin_username == "bootstrap-admin").count() == 1


@pytest.mark.scenario("ADMIN-TS-097")
def test_ensure_admin_account_skips_when_unconfigured(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", None)

    assert AdminAuthService.ensure_admin_account(db) is None


@pytest.mark.scenario("ADMIN-TS-098")
def test_ensure_admin_account_skips_without_initial_password(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "no-password-admin")
    monkeypatch.setattr(settings, "admin_initial_password", None)

    assert AdminAuthService.ensure_admin_account(db) is None
    assert db.query(User).filter(User.admin_username == "no-password-admin").count() == 0
