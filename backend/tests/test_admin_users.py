import uuid

from src.schema.users import User


def _admin(seed_user, login_as):
    admin = seed_user(username="admin", role="admin")
    login_as(admin)
    return admin


def _new_uuid() -> str:
    return str(uuid.uuid4())


def test_admin_creates_user_defaults(client, seed_user, login_as):
    admin = _admin(seed_user, login_as)
    u = _new_uuid()
    resp = client.post(
        "/api/v1/admin/users/create",
        json={"uuid": u, "username": "newbie", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "newbie"
    assert body["role"] == "annotator"
    assert body["expert_level"] == 0

    factory = client.app.state.session_factory
    with factory() as session:
        row = session.query(User).filter(User.username == "newbie").one()
        assert row.created_by == admin.id
        assert row.uuid == uuid.UUID(u).bytes
        assert row.created_at > 0


def test_admin_creates_user_with_role_ignores_expert_level(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/users/create",
        json={
            "uuid": _new_uuid(),
            "username": "sci",
            "role": "scientist",
            "expert_level": 3,
            "password": "correct horse battery staple",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "scientist"
    assert body["expert_level"] == 0
    assert body["exp"] == 0


def test_create_duplicate_username_conflicts(client, seed_user, login_as):
    _admin(seed_user, login_as)
    client.post(
        "/api/v1/admin/users/create",
        json={"uuid": _new_uuid(), "username": "dup", "password": "correct horse battery staple"},
    )
    resp = client.post(
        "/api/v1/admin/users/create",
        json={"uuid": _new_uuid(), "username": "dup", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 409


def test_create_malformed_uuid_is_422(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/users/create",
        json={"uuid": "not-a-uuid", "username": "bad", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 422


def test_create_invalid_role_is_422(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/users/create",
        json={"uuid": _new_uuid(), "username": "x", "role": "wizard", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 422


def test_update_changes_username(client, seed_user, login_as):
    _admin(seed_user, login_as)
    u = _new_uuid()
    client.post(
        "/api/v1/admin/users/create",
        json={"uuid": u, "username": "before", "password": "correct horse battery staple"},
    )
    resp = client.post("/api/v1/admin/users/update", json={"uuid": u, "username": "after"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "after"


def test_update_explicit_null_is_noop(client, seed_user, login_as):
    _admin(seed_user, login_as)
    u = _new_uuid()
    client.post(
        "/api/v1/admin/users/create",
        json={
            "uuid": u,
            "username": "keep",
            "role": "scientist",
            "expert_level": 2,
            "password": "correct horse battery staple",
        },
    )
    resp = client.post(
        "/api/v1/admin/users/update",
        json={"uuid": u, "username": None, "role": None, "expert_level": None},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "keep"
    assert body["role"] == "scientist"
    assert body["expert_level"] == 0


def test_update_sets_role_but_ignores_expert_level(client, seed_user, login_as):
    _admin(seed_user, login_as)
    u = _new_uuid()
    client.post(
        "/api/v1/admin/users/create",
        json={"uuid": u, "username": "promote", "password": "correct horse battery staple"},
    )
    resp = client.post(
        "/api/v1/admin/users/update",
        json={"uuid": u, "role": "scientist", "expert_level": 5, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "scientist"
    assert body["expert_level"] == 0


def test_update_unknown_uuid_is_404(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post("/api/v1/admin/users/update", json={"uuid": _new_uuid(), "username": "ghost"})
    assert resp.status_code == 404


def test_non_admin_is_403(client, seed_user, login_as):
    scientist = seed_user(username="sci", role="scientist")
    login_as(scientist)
    resp = client.post("/api/v1/admin/users/create", json={"uuid": _new_uuid(), "username": "x"})
    assert resp.status_code == 403


def test_unauthenticated_is_401(client):
    resp = client.post("/api/v1/admin/users/create", json={"uuid": _new_uuid(), "username": "x"})
    assert resp.status_code == 401


def test_create_scientist_without_password_is_422(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/users/create",
        json={"uuid": _new_uuid(), "username": "sci", "role": "scientist"},
    )
    assert resp.status_code == 422


def test_create_admin_without_password_is_422(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/users/create",
        json={"uuid": _new_uuid(), "username": "second-admin", "role": "admin"},
    )
    assert resp.status_code == 422


def test_create_annotator_with_password_succeeds_and_can_login(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/users/create",
        json={"uuid": _new_uuid(), "username": "x", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 201

    client.post("/api/v1/auth/logout")
    login_resp = client.post(
        "/api/v1/auth/login", json={"username": "x", "password": "correct horse battery staple"}
    )
    assert login_resp.status_code == 200


def test_create_annotator_without_password_is_422(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post("/api/v1/admin/users/create", json={"uuid": _new_uuid(), "username": "plain"})
    assert resp.status_code == 422


def test_create_password_too_short_is_422(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/users/create",
        json={"uuid": _new_uuid(), "username": "sci", "role": "scientist", "password": "short"},
    )
    assert resp.status_code == 422


def test_create_password_too_long_is_422(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/users/create",
        json={"uuid": _new_uuid(), "username": "sci", "role": "scientist", "password": "x" * 128},
    )
    assert resp.status_code == 422


def test_create_scientist_with_password_can_then_login(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/users/create",
        json={
            "uuid": _new_uuid(),
            "username": "sci-login",
            "role": "scientist",
            "password": "correct horse battery staple",
        },
    )
    assert resp.status_code == 201

    client.post("/api/v1/auth/logout")
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "sci-login", "password": "correct horse battery staple"},
    )
    assert login_resp.status_code == 200


def test_update_promote_to_scientist_without_password_is_422(client, seed_user, login_as):
    _admin(seed_user, login_as)
    # A legacy annotator with no stored credential (seed_user bypasses the
    # now-mandatory password on the create endpoint, matching pre-existing
    # production accounts created before annotators required passwords).
    legacy = seed_user(username="promote2", role="annotator")
    resp = client.post(
        "/api/v1/admin/users/update", json={"uuid": str(uuid.UUID(bytes=legacy.uuid)), "role": "scientist"}
    )
    assert resp.status_code == 422


def test_update_promote_to_scientist_with_password_succeeds_and_can_login(client, seed_user, login_as):
    _admin(seed_user, login_as)
    u = _new_uuid()
    client.post(
        "/api/v1/admin/users/create",
        json={"uuid": u, "username": "promote3", "password": "correct horse battery staple"},
    )
    resp = client.post(
        "/api/v1/admin/users/update",
        json={"uuid": u, "role": "scientist", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200

    client.post("/api/v1/auth/logout")
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "promote3", "password": "correct horse battery staple"},
    )
    assert login_resp.status_code == 200


def test_update_change_password_for_existing_scientist(client, seed_user, login_as):
    _admin(seed_user, login_as)
    u = _new_uuid()
    client.post(
        "/api/v1/admin/users/create",
        json={"uuid": u, "username": "haspw", "role": "scientist", "password": "correct horse battery staple"},
    )
    resp = client.post(
        "/api/v1/admin/users/update",
        json={"uuid": u, "password": "a different battery staple"},
    )
    assert resp.status_code == 200

    client.post("/api/v1/auth/logout")
    old_login = client.post(
        "/api/v1/auth/login", json={"username": "haspw", "password": "correct horse battery staple"}
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/v1/auth/login", json={"username": "haspw", "password": "a different battery staple"}
    )
    assert new_login.status_code == 200


def test_update_demote_to_annotator_preserves_stored_password(client, seed_user, login_as):
    _admin(seed_user, login_as)
    u = _new_uuid()
    client.post(
        "/api/v1/admin/users/create",
        json={"uuid": u, "username": "demoted", "role": "scientist", "password": "correct horse battery staple"},
    )
    resp = client.post("/api/v1/admin/users/update", json={"uuid": u, "role": "annotator"})
    assert resp.status_code == 200

    # Re-promoting doesn't need a fresh password either - the credential was never deleted.
    # Done here, while still the admin session, since logging in as "demoted"
    # below would replace the client's session/CSRF state.
    resp = client.post("/api/v1/admin/users/update", json={"uuid": u, "role": "scientist"})
    assert resp.status_code == 200

    client.post("/api/v1/auth/logout")
    login_resp = client.post(
        "/api/v1/auth/login", json={"username": "demoted", "password": "correct horse battery staple"}
    )
    assert login_resp.status_code == 200


def test_update_demote_and_set_password_in_same_request_succeeds(client, seed_user, login_as):
    _admin(seed_user, login_as)
    u = _new_uuid()
    client.post(
        "/api/v1/admin/users/create",
        json={"uuid": u, "username": "conflict", "role": "scientist", "password": "correct horse battery staple"},
    )
    resp = client.post(
        "/api/v1/admin/users/update",
        json={"uuid": u, "role": "annotator", "password": "a different battery staple"},
    )
    assert resp.status_code == 200

    client.post("/api/v1/auth/logout")
    login_resp = client.post(
        "/api/v1/auth/login", json={"username": "conflict", "password": "a different battery staple"}
    )
    assert login_resp.status_code == 200


def test_update_role_unchanged_password_omitted_is_noop(client, seed_user, login_as):
    _admin(seed_user, login_as)
    u = _new_uuid()
    client.post(
        "/api/v1/admin/users/create",
        json={"uuid": u, "username": "unchanged", "role": "scientist", "password": "correct horse battery staple"},
    )
    resp = client.post("/api/v1/admin/users/update", json={"uuid": u, "username": "unchanged2"})
    assert resp.status_code == 200

    client.post("/api/v1/auth/logout")
    login_resp = client.post(
        "/api/v1/auth/login", json={"username": "unchanged2", "password": "correct horse battery staple"}
    )
    assert login_resp.status_code == 200


def test_admin_sets_password_for_legacy_annotator_unlocks_login(client, seed_user, login_as):
    _admin(seed_user, login_as)
    legacy = seed_user(username="legacy-locked", role="annotator")

    login_attempt = client.post(
        "/api/v1/auth/login", json={"username": "legacy-locked", "password": "anything1234"}
    )
    assert login_attempt.status_code == 403

    resp = client.post(
        "/api/v1/admin/users/update",
        json={"uuid": str(uuid.UUID(bytes=legacy.uuid)), "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200

    unlocked_login = client.post(
        "/api/v1/auth/login", json={"username": "legacy-locked", "password": "correct horse battery staple"}
    )
    assert unlocked_login.status_code == 200


def test_admin_updates_annotator_username_without_password_stays_locked(client, seed_user, login_as):
    _admin(seed_user, login_as)
    legacy = seed_user(username="legacy-rename", role="annotator")

    resp = client.post(
        "/api/v1/admin/users/update",
        json={"uuid": str(uuid.UUID(bytes=legacy.uuid)), "username": "legacy-renamed"},
    )
    assert resp.status_code == 200

    login_attempt = client.post(
        "/api/v1/auth/login", json={"username": "legacy-renamed", "password": "anything1234"}
    )
    assert login_attempt.status_code == 403
