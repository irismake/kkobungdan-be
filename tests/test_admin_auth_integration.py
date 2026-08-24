"""관리자 인증·인가 통합 테스트."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.password import hash_password, verify_password
from app.models.proposal import ProposalStatus
from app.models.user import User
from app.services.admin.admin_auth_service import AdminAuthService


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


@pytest.mark.parametrize("method,path", ADMIN_PATHS)
def test_admin_paths_reject_missing_token(client, method, path):
    response = getattr(client, method)(path)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.parametrize("method,path", ADMIN_PATHS)
def test_admin_paths_reject_non_admin_user(client, auth_headers, method, path):
    response = getattr(client, method)(path, headers=auth_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("method,path", ADMIN_PATHS)
def test_admin_paths_accept_admin_token(client, admin_headers, method, path):
    response = getattr(client, method)(path, headers=admin_headers)

    assert response.status_code == 200


def test_admin_mutation_rejects_non_admin_user(client, factory, sample_user, auth_headers):
    proposal = factory.proposal(sample_user.id, ProposalStatus.HOLDING)

    response = client.post(
        f"/v1/admin/proposal/{proposal.id}/confirm-payment",
        json={"openChatUrl": "https://open.kakao.com/o/example"},
        headers=auth_headers,
    )

    assert response.status_code == 403


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


def test_login_rejects_wrong_password(client, admin_user):
    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ADMIN_CREDENTIALS_INVALID"


def test_login_rejects_unknown_username_with_same_error(client, admin_user):
    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "nobody", "password": "admin-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ADMIN_CREDENTIALS_INVALID"


def test_login_rejects_non_admin_account(client, db, sample_user):
    sample_user.admin_username = "notadmin"
    sample_user.password_hash = hash_password("admin-password")
    db.commit()

    response = client.post(
        "/v1/admin/auth/login",
        json={"username": "notadmin", "password": "admin-password"},
    )

    assert response.status_code == 401


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


def test_ensure_admin_account_skips_when_unconfigured(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", None)

    assert AdminAuthService.ensure_admin_account(db) is None


def test_ensure_admin_account_skips_without_initial_password(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "no-password-admin")
    monkeypatch.setattr(settings, "admin_initial_password", None)

    assert AdminAuthService.ensure_admin_account(db) is None
    assert db.query(User).filter(User.admin_username == "no-password-admin").count() == 0
