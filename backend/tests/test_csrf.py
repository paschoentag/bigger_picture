from uuid import UUID

from src import config
from src.csrf import CSRF_HEADER_NAME, compute_csrf_token, verify_csrf_token


def test_compute_csrf_token_is_deterministic():
    uuid_bytes = b"0" * 16
    assert compute_csrf_token(uuid_bytes) == compute_csrf_token(uuid_bytes)


def test_compute_csrf_token_differs_per_user():
    assert compute_csrf_token(b"0" * 16) != compute_csrf_token(b"1" * 16)


def test_verify_csrf_token_accepts_correct_token():
    uuid_bytes = b"2" * 16
    assert verify_csrf_token(uuid_bytes, compute_csrf_token(uuid_bytes)) is True


def test_verify_csrf_token_rejects_wrong_token():
    uuid_bytes = b"3" * 16
    assert verify_csrf_token(uuid_bytes, "not-the-right-token") is False


def test_verify_csrf_token_rejects_none():
    assert verify_csrf_token(b"4" * 16, None) is False


def test_verify_csrf_token_rejects_empty_string():
    assert verify_csrf_token(b"5" * 16, "") is False


def _login_scientist(client, seed_user, set_password, username="csrf-sci", password="correct horse battery staple"):
    user = seed_user(username=username, role="scientist")
    set_password(user, password)
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return user


def _login_annotator(client, username="csrf-annotator", password="correct horse battery staple"):
    resp = client.post("/api/v1/auth/signup", json={"username": username, "password": password})
    assert resp.status_code == 201
    return resp.json()


def test_login_scientist_sets_csrf_cookie(client, seed_user, set_password):
    resp_user = _login_scientist(client, seed_user, set_password)
    assert config.CSRF_COOKIE_NAME in client.cookies
    assert client.cookies[config.CSRF_COOKIE_NAME] == compute_csrf_token(resp_user.uuid)


def test_login_annotator_sets_csrf_cookie(client):
    annotator = _login_annotator(client)
    assert config.CSRF_COOKIE_NAME in client.cookies
    assert client.cookies[config.CSRF_COOKIE_NAME] == compute_csrf_token(UUID(annotator["uuid"]).bytes)


def test_mutating_request_without_csrf_header_is_403(client, seed_user, set_password):
    _login_scientist(client, seed_user, set_password)
    client.headers.pop(CSRF_HEADER_NAME, None)
    resp = client.post("/api/v1/auth/password", json={"password": "a brand new password"})
    assert resp.status_code == 403


def test_mutating_request_with_wrong_csrf_header_is_403(client, seed_user, set_password):
    _login_scientist(client, seed_user, set_password)
    resp = client.post(
        "/api/v1/auth/password",
        json={"password": "a brand new password"},
        headers={CSRF_HEADER_NAME: "totally-wrong-token"},
    )
    assert resp.status_code == 403


def test_mutating_request_with_correct_csrf_header_succeeds(client, seed_user, set_password):
    user = _login_scientist(client, seed_user, set_password)
    resp = client.post(
        "/api/v1/auth/password",
        json={"password": "a brand new password"},
        headers={CSRF_HEADER_NAME: compute_csrf_token(user.uuid)},
    )
    assert resp.status_code == 204


def test_annotator_mutating_request_without_csrf_header_is_403(client):
    _login_annotator(client, username="csrf-plain")
    client.headers.pop(CSRF_HEADER_NAME, None)
    resp = client.post("/api/v1/auth/story", json={"story": {"chapter": 1}})
    assert resp.status_code == 403


def test_annotator_mutating_request_with_correct_csrf_header_succeeds(client):
    annotator = _login_annotator(client, username="csrf-plain2")
    resp = client.post(
        "/api/v1/auth/story",
        json={"story": {"chapter": 1}},
        headers={CSRF_HEADER_NAME: compute_csrf_token(UUID(annotator["uuid"]).bytes)},
    )
    assert resp.status_code == 200


def test_safe_method_needs_no_csrf_header(client, seed_user, set_password):
    _login_scientist(client, seed_user, set_password)
    client.headers.pop(CSRF_HEADER_NAME, None)
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200


def test_logout_requires_csrf_header_for_scientist(client, seed_user, set_password):
    _login_scientist(client, seed_user, set_password)
    client.headers.pop(CSRF_HEADER_NAME, None)
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 403


def test_logout_clears_csrf_cookie(client, seed_user, set_password):
    user = _login_scientist(client, seed_user, set_password)
    resp = client.post("/api/v1/auth/logout", headers={CSRF_HEADER_NAME: compute_csrf_token(user.uuid)})
    assert resp.status_code == 204
    assert config.CSRF_COOKIE_NAME not in client.cookies


def test_csrf_token_from_a_different_users_session_is_rejected(client, seed_user, set_password):
    _login_scientist(client, seed_user, set_password, username="csrf-victim")
    other = seed_user(username="csrf-attacker", role="scientist")
    resp = client.post(
        "/api/v1/auth/password",
        json={"password": "whatever new password"},
        headers={CSRF_HEADER_NAME: compute_csrf_token(other.uuid)},
    )
    assert resp.status_code == 403


def test_rotating_secret_invalidates_outstanding_csrf_tokens(client, seed_user, set_password, monkeypatch):
    user = _login_scientist(client, seed_user, set_password)
    stale_token = client.cookies[config.CSRF_COOKIE_NAME]

    monkeypatch.setattr(config, "CSRF_SECRET", b"a-completely-different-secret")

    resp = client.post(
        "/api/v1/auth/password",
        json={"password": "whatever new password"},
        headers={CSRF_HEADER_NAME: stale_token},
    )
    assert resp.status_code == 403

    # Re-fetching /me issues a fresh cookie signed with the new secret, so the
    # session self-heals without requiring a fresh login.
    refreshed = client.get("/api/v1/auth/me")
    assert refreshed.status_code == 200
    assert client.cookies[config.CSRF_COOKIE_NAME] == compute_csrf_token(user.uuid)
