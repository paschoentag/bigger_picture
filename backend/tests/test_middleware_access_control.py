import uuid

from src import config
from src.constants import Role

ENDPOINTS = {
    "annotate": "/api/v1/annotate/labels",
    "dataset": "/api/v1/dataset/summary",
    "admin": "/api/v1/admin/users",
}


def test_anonymous_gets_401_on_protected_paths(client):
    for name, path in ENDPOINTS.items():
        assert client.get(path).status_code == 401, name


def test_anonymous_can_reach_public_paths(client):
    resp = client.post(
        "/api/v1/auth/signup", json={"username": "pub", "password": "correct horse battery staple"}
    )
    assert resp.status_code == 201
    assert client.get("/assets/").status_code not in (401, 403)


def test_unknown_uuid_cookie_is_401(client):
    client.cookies.set(config.COOKIE_NAME, uuid.uuid4().hex)
    assert client.get(ENDPOINTS["annotate"]).status_code == 401


def test_annotator_access(client, seed_user, login_as):
    user = seed_user(username="ann", role=Role.ANNOTATOR)
    login_as(user)
    assert client.get(ENDPOINTS["annotate"]).status_code == 200
    assert client.get(ENDPOINTS["dataset"]).status_code == 403
    assert client.get(ENDPOINTS["admin"]).status_code == 403


def test_scientist_access(client, seed_user, login_as):
    user = seed_user(username="sci", role=Role.SCIENTIST)
    login_as(user)
    assert client.get(ENDPOINTS["annotate"]).status_code == 200
    assert client.get(ENDPOINTS["dataset"]).status_code == 200
    assert client.get(ENDPOINTS["admin"]).status_code == 403


def test_admin_access(client, seed_user, login_as):
    user = seed_user(username="adm", role=Role.ADMIN)
    login_as(user)
    assert client.get(ENDPOINTS["annotate"]).status_code == 200
    assert client.get(ENDPOINTS["dataset"]).status_code == 200
    assert client.get(ENDPOINTS["admin"]).status_code == 200
