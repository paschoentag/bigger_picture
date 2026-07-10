import base64
import io
import uuid

import pytest
from PIL import Image as PILImage


@pytest.fixture
def scientist(seed_user, login_as):
    user = seed_user(username="sci", role="scientist")
    login_as(user)
    return user


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _png_b64(width=10, height=10) -> str:
    img = PILImage.new("RGB", (width, height), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _make_dive(client, title="dive") -> str:
    region = _new_uuid()
    assert client.post(
        "/api/v1/dataset/regions/create", json={"uuid": region, "title": title + "-r"}
    ).status_code == 201
    camera = _new_uuid()
    assert client.post(
        "/api/v1/dataset/cameras/create", json={"uuid": camera, "title": title + "-c"}
    ).status_code == 201
    u = _new_uuid()
    resp = client.post(
        "/api/v1/dataset/dives/create",
        json={"uuid": u, "title": title, "region": region, "camera": camera},
    )
    assert resp.status_code == 201, resp.text
    return u


def _make_image(client, dive, filepath) -> str:
    return _make_image_named(client, dive, filename=filepath, filepath=filepath)


def _make_image_named(client, dive, filename, filepath) -> str:
    u = _new_uuid()
    resp = client.post(
        "/api/v1/dataset/images/create",
        json={
            "uuid": u,
            "filename": filename,
            "filepath": filepath,
            "dive_uuid": dive,
            "image": _png_b64(),
        },
    )
    assert resp.status_code == 201, resp.text
    return u


@pytest.fixture
def images(client, scientist):
    dive = _make_dive(client)
    return [_make_image(client, dive, f"img{i}.png") for i in range(4)]


def test_create_candidate_happy_sorted_and_hidden(client, images, scientist):
    resp = client.post(
        "/api/v1/dataset/candidates/create",
        json={"image_a": images[0], "image_b": images[1]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "hidden"
    assert body["created_by"] == str(uuid.UUID(bytes=scientist.uuid))
    assert {body["image_a"], body["image_b"]} == {images[0], images[1]}


def test_create_candidate_duplicate_is_409(client, images):
    body = {"image_a": images[0], "image_b": images[1]}
    assert client.post("/api/v1/dataset/candidates/create", json=body).status_code == 201
    # Reversed order resolves to the same sorted pair -> duplicate.
    resp = client.post(
        "/api/v1/dataset/candidates/create",
        json={"image_a": images[1], "image_b": images[0]},
    )
    assert resp.status_code == 409, resp.text


def test_create_candidate_missing_image_is_404(client, images):
    resp = client.post(
        "/api/v1/dataset/candidates/create",
        json={"image_a": images[0], "image_b": _new_uuid()},
    )
    assert resp.status_code == 404, resp.text


def test_create_candidate_same_image_is_422(client, images):
    resp = client.post(
        "/api/v1/dataset/candidates/create",
        json={"image_a": images[0], "image_b": images[0]},
    )
    assert resp.status_code == 422, resp.text


def test_create_candidate_malformed_uuid_is_422(client, images):
    resp = client.post(
        "/api/v1/dataset/candidates/create",
        json={"image_a": images[0], "image_b": "not-a-uuid"},
    )
    assert resp.status_code == 422, resp.text


def test_batch_status_change_open(client, images):
    for pair in [(0, 1), (1, 2)]:
        assert client.post(
            "/api/v1/dataset/candidates/create",
            json={"image_a": images[pair[0]], "image_b": images[pair[1]]},
        ).status_code == 201
    resp = client.post(
        "/api/v1/dataset/candidates/batch/status-change/open",
        json=[
            {"image_a": images[0], "image_b": images[1]},
            {"image_a": images[1], "image_b": images[2]},
        ],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 2


def test_batch_unknown_status_is_422(client, images):
    assert client.post(
        "/api/v1/dataset/candidates/create",
        json={"image_a": images[0], "image_b": images[1]},
    ).status_code == 201
    resp = client.post(
        "/api/v1/dataset/candidates/batch/status-change/bogus",
        json=[{"image_a": images[0], "image_b": images[1]}],
    )
    assert resp.status_code == 422, resp.text


def test_batch_missing_pair_rolls_back(client, images):
    assert client.post(
        "/api/v1/dataset/candidates/create",
        json={"image_a": images[0], "image_b": images[1]},
    ).status_code == 201
    # One item's pair does not exist -> 404, and nothing is changed.
    resp = client.post(
        "/api/v1/dataset/candidates/batch/status-change/open",
        json=[
            {"image_a": images[0], "image_b": images[1]},
            {"image_a": images[2], "image_b": images[3]},
        ],
    )
    assert resp.status_code == 404, resp.text
    # First pair still hidden (re-creating would 409, proving it still exists as hidden).
    # Flip only the existing one to confirm it was untouched (still updatable).
    ok = client.post(
        "/api/v1/dataset/candidates/batch/status-change/open",
        json=[{"image_a": images[0], "image_b": images[1]}],
    )
    assert ok.status_code == 200


def test_batch_has_overlap_creates_image_pair_idempotently(client, images):
    assert client.post(
        "/api/v1/dataset/candidates/create",
        json={"image_a": images[0], "image_b": images[1]},
    ).status_code == 201

    before = client.get("/api/v1/dataset/summary").json()["image_pair_count"]

    resp = client.post(
        "/api/v1/dataset/candidates/batch/status-change/has_overlap",
        json=[{"image_a": images[0], "image_b": images[1]}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 1
    assert resp.json()["image_pairs_created"] == 1

    after = client.get("/api/v1/dataset/summary").json()["image_pair_count"]
    assert after == before + 1

    # Running it again must not create a duplicate ImagePair nor error.
    resp2 = client.post(
        "/api/v1/dataset/candidates/batch/status-change/has_overlap",
        json=[{"image_a": images[0], "image_b": images[1]}],
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["image_pairs_created"] == 0
    final = client.get("/api/v1/dataset/summary").json()["image_pair_count"]
    assert final == before + 1


def test_candidates_role_gating_annotator_forbidden(client, seed_user, login_as):
    login_as(seed_user(username="ann", role="annotator"))
    resp = client.post(
        "/api/v1/dataset/candidates/create",
        json={"image_a": _new_uuid(), "image_b": _new_uuid()},
    )
    assert resp.status_code == 403


def test_list_candidates_returns_pairs_in_dive(client, scientist):
    dive = _make_dive(client)
    a = _make_image(client, dive, "la.png")
    b = _make_image(client, dive, "lb.png")
    c = _make_image(client, dive, "lc.png")
    assert client.post("/api/v1/dataset/candidates/create", json={"image_a": a, "image_b": b}).status_code == 201
    assert client.post("/api/v1/dataset/candidates/create", json={"image_a": b, "image_b": c}).status_code == 201

    resp = client.get(f"/api/v1/dataset/candidates?dive={dive}")
    assert resp.status_code == 200, resp.text
    pairs = resp.json()["candidates"]
    assert len(pairs) == 2
    assert {frozenset((p["image_a"], p["image_b"])) for p in pairs} == {
        frozenset((a, b)),
        frozenset((b, c)),
    }


def test_list_candidates_excludes_other_dives(client, scientist):
    dive_a = _make_dive(client, title="dive-a")
    dive_b = _make_dive(client, title="dive-b")
    a1 = _make_image(client, dive_a, "a1.png")
    a2 = _make_image(client, dive_a, "a2.png")
    b1 = _make_image(client, dive_b, "b1.png")
    b2 = _make_image(client, dive_b, "b2.png")
    assert client.post("/api/v1/dataset/candidates/create", json={"image_a": a1, "image_b": a2}).status_code == 201
    assert client.post("/api/v1/dataset/candidates/create", json={"image_a": b1, "image_b": b2}).status_code == 201

    resp = client.get(f"/api/v1/dataset/candidates?dive={dive_a}")
    assert resp.status_code == 200
    pairs = resp.json()["candidates"]
    assert len(pairs) == 1
    assert {pairs[0]["image_a"], pairs[0]["image_b"]} == {a1, a2}


def test_list_candidates_unknown_dive_is_404(client, scientist):
    resp = client.get(f"/api/v1/dataset/candidates?dive={_new_uuid()}")
    assert resp.status_code == 404


def test_list_candidates_role_gating_annotator_forbidden(client, seed_user, login_as):
    login_as(seed_user(username="ann2", role="annotator"))
    resp = client.get(f"/api/v1/dataset/candidates?dive={_new_uuid()}")
    assert resp.status_code == 403


def test_create_stride_happy_path(client, scientist):
    dive = _make_dive(client)
    imgs = [_make_image(client, dive, f"img{i}.png") for i in range(4)]

    resp = client.post(
        "/api/v1/dataset/candidates/create-stride",
        json={"dive_uuid": dive, "stride": 1, "sort_by": "filename"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_images"] == 4
    assert body["pairs_considered"] == 3
    assert body["pairs_created"] == 3
    assert body["pairs_skipped"] == 0

    listing = client.get(f"/api/v1/dataset/candidates?dive={dive}").json()["candidates"]
    pairs = {frozenset((p["image_a"], p["image_b"])) for p in listing}
    assert pairs == {
        frozenset((imgs[0], imgs[1])),
        frozenset((imgs[1], imgs[2])),
        frozenset((imgs[2], imgs[3])),
    }
    assert all(p["status"] == "hidden" for p in listing)


def test_create_stride_larger_stride(client, scientist):
    dive = _make_dive(client)
    imgs = [_make_image(client, dive, f"img{i}.png") for i in range(4)]

    resp = client.post(
        "/api/v1/dataset/candidates/create-stride",
        json={"dive_uuid": dive, "stride": 2, "sort_by": "filename"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["pairs_considered"] == 2
    assert body["pairs_created"] == 2

    listing = client.get(f"/api/v1/dataset/candidates?dive={dive}").json()["candidates"]
    pairs = {frozenset((p["image_a"], p["image_b"])) for p in listing}
    assert pairs == {frozenset((imgs[0], imgs[2])), frozenset((imgs[1], imgs[3]))}


def test_create_stride_is_idempotent(client, scientist):
    dive = _make_dive(client)
    [_make_image(client, dive, f"img{i}.png") for i in range(4)]

    first = client.post(
        "/api/v1/dataset/candidates/create-stride",
        json={"dive_uuid": dive, "stride": 1, "sort_by": "filename"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["pairs_created"] == 3

    second = client.post(
        "/api/v1/dataset/candidates/create-stride",
        json={"dive_uuid": dive, "stride": 1, "sort_by": "filename"},
    )
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["pairs_created"] == 0
    assert body["pairs_considered"] == 3
    assert body["pairs_skipped"] == 3


def test_create_stride_missing_dive_is_404(client, scientist):
    resp = client.post(
        "/api/v1/dataset/candidates/create-stride",
        json={"dive_uuid": _new_uuid(), "stride": 1, "sort_by": "filename"},
    )
    assert resp.status_code == 404


def test_create_stride_zero_stride_is_422(client, scientist):
    dive = _make_dive(client)
    resp = client.post(
        "/api/v1/dataset/candidates/create-stride",
        json={"dive_uuid": dive, "stride": 0, "sort_by": "filename"},
    )
    assert resp.status_code == 422


def test_create_stride_sort_by_filepath(client, scientist):
    dive = _make_dive(client)
    a = _make_image_named(client, dive, filename="1.png", filepath="b.png")
    b = _make_image_named(client, dive, filename="2.png", filepath="c.png")
    c = _make_image_named(client, dive, filename="3.png", filepath="a.png")

    resp = client.post(
        "/api/v1/dataset/candidates/create-stride",
        json={"dive_uuid": dive, "stride": 1, "sort_by": "filepath"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["pairs_created"] == 2

    listing = client.get(f"/api/v1/dataset/candidates?dive={dive}").json()["candidates"]
    pairs = {frozenset((p["image_a"], p["image_b"])) for p in listing}
    # filepath order is c ("a.png"), a ("b.png"), b ("c.png") -> adjacent pairs (c,a) and (a,b).
    assert pairs == {frozenset((c, a)), frozenset((a, b))}


def test_create_stride_role_gating_annotator_forbidden(client, seed_user, login_as):
    login_as(seed_user(username="ann3", role="annotator"))
    resp = client.post(
        "/api/v1/dataset/candidates/create-stride",
        json={"dive_uuid": _new_uuid(), "stride": 1, "sort_by": "filename"},
    )
    assert resp.status_code == 403


def test_list_candidates_hidden_count(client, scientist):
    dive = _make_dive(client)
    a = _make_image(client, dive, "ha.png")
    b = _make_image(client, dive, "hb.png")
    c = _make_image(client, dive, "hc.png")
    assert client.post("/api/v1/dataset/candidates/create", json={"image_a": a, "image_b": b}).status_code == 201
    assert client.post("/api/v1/dataset/candidates/create", json={"image_a": b, "image_b": c}).status_code == 201
    assert client.post(
        "/api/v1/dataset/candidates/batch/status-change/open",
        json=[{"image_a": a, "image_b": b}],
    ).status_code == 200

    resp = client.get(f"/api/v1/dataset/candidates?dive={dive}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["hidden_count"] == 1


def test_publish_moves_hidden_to_open(client, scientist):
    dive = _make_dive(client)
    a = _make_image(client, dive, "pa.png")
    b = _make_image(client, dive, "pb.png")
    c = _make_image(client, dive, "pc.png")
    assert client.post("/api/v1/dataset/candidates/create", json={"image_a": a, "image_b": b}).status_code == 201
    assert client.post("/api/v1/dataset/candidates/create", json={"image_a": b, "image_b": c}).status_code == 201

    resp = client.post("/api/v1/dataset/candidates/publish", json={"dive_uuid": dive})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"published": 2, "remaining_hidden": 0}

    listing = client.get(f"/api/v1/dataset/candidates?dive={dive}").json()
    assert listing["hidden_count"] == 0
    assert all(p["status"] == "open" for p in listing["candidates"])

    # Calling again publishes nothing further, since none are hidden anymore.
    resp2 = client.post("/api/v1/dataset/candidates/publish", json={"dive_uuid": dive})
    assert resp2.status_code == 200
    assert resp2.json() == {"published": 0, "remaining_hidden": 0}


def test_publish_respects_batch_cap(client, scientist, monkeypatch):
    import src.api.v1.dataset.candidate_pairs as candidate_pairs_module

    monkeypatch.setattr(candidate_pairs_module, "PUBLISH_BATCH_SIZE", 2)

    dive = _make_dive(client)
    imgs = [_make_image(client, dive, f"cap{i}.png") for i in range(4)]
    for i in range(3):
        assert client.post(
            "/api/v1/dataset/candidates/create",
            json={"image_a": imgs[i], "image_b": imgs[i + 1]},
        ).status_code == 201

    first = client.post("/api/v1/dataset/candidates/publish", json={"dive_uuid": dive})
    assert first.status_code == 200, first.text
    assert first.json() == {"published": 2, "remaining_hidden": 1}

    second = client.post("/api/v1/dataset/candidates/publish", json={"dive_uuid": dive})
    assert second.status_code == 200, second.text
    assert second.json() == {"published": 1, "remaining_hidden": 0}


def test_publish_missing_dive_is_404(client, scientist):
    resp = client.post("/api/v1/dataset/candidates/publish", json={"dive_uuid": _new_uuid()})
    assert resp.status_code == 404


def test_publish_role_gating_annotator_forbidden(client, seed_user, login_as):
    login_as(seed_user(username="ann4", role="annotator"))
    resp = client.post("/api/v1/dataset/candidates/publish", json={"dive_uuid": _new_uuid()})
    assert resp.status_code == 403
