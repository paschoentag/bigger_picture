from sqlalchemy import text

from src import config
from src.csrf import CSRF_HEADER_NAME


def _signup(client, username):
    resp = client.post(
        "/api/v1/auth/signup", json={"username": username, "password": "correct horse battery staple"}
    )
    assert resp.status_code == 201, resp.text
    # Echo the fresh CSRF cookie into the default header, mirroring what the
    # frontend does automatically - needed so a subsequent _signup() call for
    # a different user (still an unsafe request under the current session)
    # doesn't get rejected by the CSRF check.
    client.headers[CSRF_HEADER_NAME] = client.cookies[config.CSRF_COOKIE_NAME]
    return resp.json()["uuid"]


def _set_exp(client, username, exp):
    engine = client.app.state.engine
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET exp = :exp WHERE username = :username"),
            {"exp": exp, "username": username},
        )


def _entries(client, query=""):
    resp = client.get(f"/api/v1/annotate/leaderboard{query}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _only(entries, usernames):
    """Ranked usernames restricted to the set we created, order preserved."""
    wanted = set(usernames)
    return [e["username"] for e in entries if e["username"] in wanted]


def test_leaderboard_requires_auth(client):
    assert client.get("/api/v1/annotate/leaderboard").status_code == 401


def test_leaderboard_orders_by_exp_descending(client):
    _signup(client, "low")
    _signup(client, "high")
    _signup(client, "mid")
    _set_exp(client, "low", 5)
    _set_exp(client, "high", 100)
    _set_exp(client, "mid", 50)

    body = _entries(client)
    assert _only(body["entries"], ["low", "high", "mid"]) == ["high", "mid", "low"]
    by_name = {e["username"]: e for e in body["entries"]}
    assert by_name["high"]["exp"] == 100
    # Ranks are 1-based and strictly increasing down the list.
    ranks = [e["rank"] for e in body["entries"]]
    assert ranks == list(range(1, len(ranks) + 1))
    assert body["total"] == len(body["entries"])


def test_leaderboard_paginates_with_limit_offset(client):
    # High exp so these five outrank any seeded (exp 0) account and stay on top.
    for i in range(5):
        _signup(client, f"user{i}")
        _set_exp(client, f"user{i}", 1000 - i)

    first = _entries(client, "?limit=2&offset=0")
    assert [e["username"] for e in first["entries"]] == ["user0", "user1"]
    assert [e["rank"] for e in first["entries"]] == [1, 2]

    second = _entries(client, "?limit=2&offset=2")
    assert [e["username"] for e in second["entries"]] == ["user2", "user3"]
    assert [e["rank"] for e in second["entries"]] == [3, 4]

    # Total is stable across pages.
    assert first["total"] == second["total"]
    assert first["total"] >= 5


def test_leaderboard_tie_broken_by_account_age(client):
    _signup(client, "older")
    _signup(client, "newer")
    _set_exp(client, "older", 42)
    _set_exp(client, "newer", 42)

    body = _entries(client)
    assert _only(body["entries"], ["older", "newer"]) == ["older", "newer"]
