from src import config
from src.csrf import CSRF_HEADER_NAME

PW = "correct horse battery staple"


def _attach_csrf(client):
    """Echo the CSRF cookie into the client's default header, mirroring what the frontend does automatically."""
    client.headers[CSRF_HEADER_NAME] = client.cookies[config.CSRF_COOKIE_NAME]


def test_signup_creates_annotator_and_sets_cookie(client):
    response = client.post("/api/v1/auth/signup", json={"username": "alice", "password": PW})
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "alice"
    assert body["role"] == "annotator"
    assert body["expert_level"] == 0
    assert body["exp"] == 0
    assert config.COOKIE_NAME in response.cookies


def test_signup_duplicate_username_conflicts(client):
    client.post("/api/v1/auth/signup", json={"username": "bob", "password": PW})
    _attach_csrf(client)
    response = client.post("/api/v1/auth/signup", json={"username": "bob", "password": PW})
    assert response.status_code == 409


def test_signup_duplicate_username_case_insensitive(client):
    client.post("/api/v1/auth/signup", json={"username": "Carl", "password": PW})
    _attach_csrf(client)
    response = client.post("/api/v1/auth/signup", json={"username": "carl", "password": PW})
    assert response.status_code == 409


def test_signup_without_password_is_422(client):
    response = client.post("/api/v1/auth/signup", json={"username": "no-pw"})
    assert response.status_code == 422


def test_login_existing_user_sets_cookie_and_resolves_identity(client):
    signup_response = client.post("/api/v1/auth/signup", json={"username": "frank", "password": PW})
    _attach_csrf(client)
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401

    login_response = client.post("/api/v1/auth/login", json={"username": "frank", "password": PW})
    assert login_response.status_code == 200
    assert config.COOKIE_NAME in login_response.cookies
    assert login_response.json()["uuid"] == signup_response.json()["uuid"]
    assert client.get("/api/v1/auth/me").json()["username"] == "frank"


def test_login_is_case_insensitive(client):
    client.post("/api/v1/auth/signup", json={"username": "Grace", "password": PW})
    _attach_csrf(client)
    client.post("/api/v1/auth/logout")

    login_response = client.post("/api/v1/auth/login", json={"username": "grace", "password": PW})
    assert login_response.status_code == 200
    assert login_response.json()["username"] == "Grace"


def test_login_unknown_username_is_404(client):
    response = client.post("/api/v1/auth/login", json={"username": "nobody"})
    assert response.status_code == 404


def test_me_without_cookie_is_401(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_resolves_signed_up_identity(client):
    signup_response = client.post("/api/v1/auth/signup", json={"username": "dana", "password": PW})
    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "dana"
    assert me_response.json()["uuid"] == signup_response.json()["uuid"]


def test_me_with_garbage_cookie_is_401(client):
    client.cookies.set(config.COOKIE_NAME, "not-a-valid-uuid")
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_logout_clears_cookie(client):
    client.post("/api/v1/auth/signup", json={"username": "erin", "password": PW})
    _attach_csrf(client)
    assert client.get("/api/v1/auth/me").status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_story_defaults_to_null(client):
    client.post("/api/v1/auth/signup", json={"username": "story-default", "password": PW})
    response = client.get("/api/v1/auth/story")
    assert response.status_code == 200
    assert response.json() == {"story": None}


def test_story_round_trips_arbitrary_json(client):
    client.post("/api/v1/auth/signup", json={"username": "story-writer", "password": PW})
    _attach_csrf(client)
    payload = {"chapter": 3, "flags": ["met_octopus"], "done": False}
    response = client.post("/api/v1/auth/story", json={"story": payload})
    assert response.status_code == 200
    assert response.json() == {"story": payload}

    response = client.get("/api/v1/auth/story")
    assert response.status_code == 200
    assert response.json() == {"story": payload}


def test_story_explicit_null_clears_it(client):
    client.post("/api/v1/auth/signup", json={"username": "story-clearer", "password": PW})
    _attach_csrf(client)
    client.post("/api/v1/auth/story", json={"story": {"chapter": 1}})
    response = client.post("/api/v1/auth/story", json={"story": None})
    assert response.status_code == 200
    assert response.json() == {"story": None}


def test_story_is_per_user(client):
    client.post("/api/v1/auth/signup", json={"username": "story-a", "password": PW})
    _attach_csrf(client)
    story_resp = client.post("/api/v1/auth/story", json={"story": {"owner": "a"}})
    assert story_resp.status_code == 200
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 204

    client.post("/api/v1/auth/signup", json={"username": "story-b", "password": PW})
    response = client.get("/api/v1/auth/story")
    assert response.status_code == 200
    assert response.json() == {"story": None}


def test_story_without_cookie_is_401(client):
    response = client.get("/api/v1/auth/story")
    assert response.status_code == 401
    response = client.post("/api/v1/auth/story", json={"story": {}})
    assert response.status_code == 401


def test_login_annotator_requires_correct_password(client):
    client.post("/api/v1/auth/signup", json={"username": "pw-annotator", "password": PW})
    _attach_csrf(client)
    client.post("/api/v1/auth/logout")
    resp = client.post("/api/v1/auth/login", json={"username": "pw-annotator", "password": PW})
    assert resp.status_code == 200


def test_login_annotator_wrong_password_is_401(client):
    client.post("/api/v1/auth/signup", json={"username": "wrong-pw-annotator", "password": PW})
    _attach_csrf(client)
    client.post("/api/v1/auth/logout")
    resp = client.post(
        "/api/v1/auth/login", json={"username": "wrong-pw-annotator", "password": "a totally different password"}
    )
    assert resp.status_code == 401


def test_login_annotator_missing_password_is_401(client):
    client.post("/api/v1/auth/signup", json={"username": "missing-pw-annotator", "password": PW})
    _attach_csrf(client)
    client.post("/api/v1/auth/logout")
    resp = client.post("/api/v1/auth/login", json={"username": "missing-pw-annotator"})
    assert resp.status_code == 401


def test_login_annotator_without_stored_credential_is_403(client, seed_user):
    seed_user(username="legacy-annotator", role="annotator")
    resp = client.post("/api/v1/auth/login", json={"username": "legacy-annotator", "password": "anything1234"})
    assert resp.status_code == 403


def test_login_scientist_missing_password_when_credential_exists_is_401(client, seed_user, set_password):
    sci = seed_user(username="sci", role="scientist")
    set_password(sci, PW)
    resp = client.post("/api/v1/auth/login", json={"username": "sci"})
    assert resp.status_code == 401


def test_login_scientist_without_stored_credential_is_403(client, seed_user):
    seed_user(username="sci-nopw", role="scientist")
    resp = client.post("/api/v1/auth/login", json={"username": "sci-nopw", "password": "anything1234"})
    assert resp.status_code == 403


def test_login_scientist_wrong_password_is_401(client, seed_user, set_password):
    sci = seed_user(username="sci2", role="scientist")
    set_password(sci, PW)
    resp = client.post("/api/v1/auth/login", json={"username": "sci2", "password": "wrong password here"})
    assert resp.status_code == 401


def test_login_scientist_correct_password_succeeds_and_sets_cookie(client, seed_user, set_password):
    sci = seed_user(username="sci3", role="scientist")
    set_password(sci, PW)
    resp = client.post("/api/v1/auth/login", json={"username": "sci3", "password": PW})
    assert resp.status_code == 200
    assert config.COOKIE_NAME in resp.cookies


def test_login_admin_correct_password_succeeds(client, seed_user, set_password):
    admin = seed_user(username="admin2", role="admin")
    set_password(admin, PW)
    resp = client.post("/api/v1/auth/login", json={"username": "admin2", "password": PW})
    assert resp.status_code == 200


def test_login_unknown_username_is_404_even_with_password_supplied(client):
    resp = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "whatever12"})
    assert resp.status_code == 404


def test_set_password_requires_authentication(client):
    resp = client.post("/api/v1/auth/password", json={"password": PW})
    assert resp.status_code == 401


def test_set_password_succeeds_for_annotator(client, seed_user, login_as):
    annotator = seed_user(username="annotator-pw", role="annotator")
    login_as(annotator)
    resp = client.post("/api/v1/auth/password", json={"password": PW})
    assert resp.status_code == 204

    client.post("/api/v1/auth/logout")
    login_resp = client.post("/api/v1/auth/login", json={"username": "annotator-pw", "password": PW})
    assert login_resp.status_code == 200


def test_set_password_too_short_is_422(client, seed_user, login_as):
    sci = seed_user(username="sci4", role="scientist")
    login_as(sci)
    resp = client.post("/api/v1/auth/password", json={"password": "short"})
    assert resp.status_code == 422


def test_set_password_too_long_is_422(client, seed_user, login_as):
    sci = seed_user(username="sci5", role="scientist")
    login_as(sci)
    resp = client.post("/api/v1/auth/password", json={"password": "x" * 128})
    assert resp.status_code == 422


def test_set_password_then_login_with_new_password_succeeds(client, seed_user, login_as):
    sci = seed_user(username="sci6", role="scientist")
    login_as(sci)
    resp = client.post("/api/v1/auth/password", json={"password": "brand new password"})
    assert resp.status_code == 204

    client.post("/api/v1/auth/logout")
    login_resp = client.post("/api/v1/auth/login", json={"username": "sci6", "password": "brand new password"})
    assert login_resp.status_code == 200


def test_set_password_invalidates_old_password(client, seed_user, login_as, set_password):
    sci = seed_user(username="sci7", role="scientist")
    set_password(sci, "old password value")
    login_as(sci)
    client.post("/api/v1/auth/password", json={"password": "brand new password"})

    client.post("/api/v1/auth/logout")
    old_login = client.post("/api/v1/auth/login", json={"username": "sci7", "password": "old password value"})
    assert old_login.status_code == 401
