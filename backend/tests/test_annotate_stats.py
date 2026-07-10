import base64
import io
import uuid

import pytest
from PIL import Image as PILImage
from sqlalchemy import text


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _png_b64(width=10, height=10) -> str:
    img = PILImage.new("RGB", (width, height), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _make_dive(client, title="dive") -> str:
    region = _new_uuid()
    assert client.post("/api/v1/dataset/regions/create", json={"uuid": region, "title": title + "-r"}).status_code == 201
    camera = _new_uuid()
    assert client.post("/api/v1/dataset/cameras/create", json={"uuid": camera, "title": title + "-c"}).status_code == 201
    u = _new_uuid()
    resp = client.post(
        "/api/v1/dataset/dives/create",
        json={"uuid": u, "title": title, "region": region, "camera": camera},
    )
    assert resp.status_code == 201, resp.text
    return u


def _make_image(client, dive, filepath) -> str:
    u = _new_uuid()
    resp = client.post(
        "/api/v1/dataset/images/create",
        json={"uuid": u, "filename": filepath, "filepath": filepath, "dive_uuid": dive, "image": _png_b64()},
    )
    assert resp.status_code == 201, resp.text
    return u


def _open_candidate(client, image_a, image_b):
    assert client.post("/api/v1/dataset/candidates/create", json={"image_a": image_a, "image_b": image_b}).status_code == 201
    resp = client.post(
        "/api/v1/dataset/candidates/batch/status-change/open",
        json=[{"image_a": image_a, "image_b": image_b}],
    )
    assert resp.status_code == 200, resp.text


def _open_pair(client, image_a, image_b):
    assert client.post("/api/v1/dataset/pairs/create", json={"image_a": image_a, "image_b": image_b}).status_code == 201
    resp = client.post(
        "/api/v1/dataset/pairs/batch/status-change/open",
        json=[{"image_a": image_a, "image_b": image_b}],
    )
    assert resp.status_code == 200, resp.text


@pytest.fixture
def dataset(client, seed_user, login_as):
    """Scientist-built dataset: 3 images with an open candidate pair and open image pair for each edge."""
    sci = seed_user(username="sci", role="scientist", expert_level=5)
    login_as(sci)
    dive = _make_dive(client)
    imgs = [_make_image(client, dive, f"img{i}.png") for i in range(3)]
    for a, b in ((imgs[0], imgs[1]), (imgs[1], imgs[2])):
        _open_candidate(client, a, b)
        _open_pair(client, a, b)
    return {"scientist": sci, "images": imgs, "dive": dive}


@pytest.fixture
def ann(client, seed_user, login_as, dataset):
    """The player under test (expert_level 1)."""
    user = seed_user(username="ann", role="annotator", expert_level=1)
    login_as(user)
    return user


def _vote(client, image_a, image_b, no_overlap) -> str:
    u = _new_uuid()
    resp = client.post(
        "/api/v1/annotate/candidate/create",
        json={"uuid": u, "image_a": image_a, "image_b": image_b, "no_overlap": no_overlap},
    )
    assert resp.status_code == 201, resp.text
    return u


def _point(client, image_a, image_b) -> str:
    u = _new_uuid()
    resp = client.post(
        "/api/v1/annotate/points/create",
        json={"uuid": u, "image_a": image_a, "image_b": image_b, "x1": 1, "y1": 2, "x2": 3, "y2": 4},
    )
    assert resp.status_code == 201, resp.text
    return u


def _review_candidate(client, u, decision):
    assert client.post(f"/api/v1/annotate/candidate/review/{u}/{decision}").status_code == 200


def _review_point(client, u, decision):
    assert client.post(f"/api/v1/annotate/points/review/{u}/{decision}").status_code == 200


def _age_point(client, u, created_at):
    engine = client.app.state.engine
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE point_annotations SET created_at = :ts WHERE uuid = :u"),
            {"ts": created_at, "u": uuid.UUID(u).bytes},
        )


def _get_stats(client, window=None):
    path = "/api/v1/annotate/stats/me"
    if window is not None:
        path += f"?window={window}"
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ------------------------- overlap -------------------------


def test_overlap_counters_and_accuracy(client, dataset, ann, login_as):
    imgs = dataset["images"]
    v_overlap = _vote(client, imgs[0], imgs[1], no_overlap=False)  # found an overlap
    v_none = _vote(client, imgs[1], imgs[2], no_overlap=True)  # no overlap

    login_as(dataset["scientist"])
    _review_candidate(client, v_overlap, "approve")
    _review_candidate(client, v_none, "fail")

    login_as(ann)
    overlap = _get_stats(client)["overlap"]
    assert overlap["pairs_marked"] == 2
    assert overlap["overlaps_found"] == 1
    assert overlap["accuracy_all_time"] == {"correct": 1, "reviewed": 2, "accuracy": 0.5}


# ------------------------- annotating -------------------------


def test_annotate_counters_and_accuracy(client, dataset, ann, login_as):
    imgs = dataset["images"]
    a1 = _point(client, imgs[0], imgs[1])  # pair 0-1
    a2 = _point(client, imgs[0], imgs[1])  # pair 0-1 (second annotation, same pair)
    _point(client, imgs[1], imgs[2])  # pair 1-2, left pending

    login_as(dataset["scientist"])
    _review_point(client, a1, "approve")
    _review_point(client, a2, "fail")

    login_as(ann)
    annotate = _get_stats(client)["annotate"]
    assert annotate["annotations"] == 3
    assert annotate["annotations_verified"] == 1
    assert annotate["pairs_marked"] == 2
    assert annotate["pairs_verified"] == 1  # only pair 0-1 has an approved annotation
    assert annotate["accuracy_all_time"] == {"correct": 1, "reviewed": 2, "accuracy": 0.5}


def test_annotate_accuracy_window(client, dataset, ann, login_as):
    imgs = dataset["images"]
    a_old = _point(client, imgs[0], imgs[1])
    a_mid = _point(client, imgs[0], imgs[1])
    a_new = _point(client, imgs[0], imgs[1])
    _age_point(client, a_old, 100)
    _age_point(client, a_mid, 200)
    _age_point(client, a_new, 300)

    login_as(dataset["scientist"])
    _review_point(client, a_old, "approve")
    _review_point(client, a_mid, "approve")
    _review_point(client, a_new, "fail")

    login_as(ann)
    annotate = _get_stats(client, window=2)["annotate"]
    # All-time: 2 of 3 approved.
    assert annotate["accuracy_all_time"] == {"correct": 2, "reviewed": 3, "accuracy": 2 / 3}
    # Window of 2 newest (a_mid approved, a_new failed): 1 of 2.
    assert annotate["accuracy_window"] == {"correct": 1, "reviewed": 2, "accuracy": 0.5}


# ------------------------- verification -------------------------


def test_verification_counters_across_tables(client, dataset, ann, seed_user, login_as):
    imgs = dataset["images"]
    # A lower-expert user produces annotations that `ann` (expert 1) can review.
    junior = seed_user(username="junior", role="annotator", expert_level=0)
    login_as(junior)
    p1 = _point(client, imgs[0], imgs[1])
    p2 = _point(client, imgs[1], imgs[2])
    c1 = _vote(client, imgs[0], imgs[1], no_overlap=False)

    login_as(ann)
    _review_point(client, p1, "approve")
    _review_point(client, p2, "fail")
    _review_candidate(client, c1, "approve")

    verify = _get_stats(client)["verify"]
    assert verify["verified"] == 3
    assert verify["accepted"] == 2
    assert verify["faulty_found"] == 1


# ------------------------- edges -------------------------


def test_no_annotations_gives_null_accuracy(client, dataset, ann):
    stats = _get_stats(client)
    assert stats["overlap"]["pairs_marked"] == 0
    assert stats["overlap"]["accuracy_all_time"] == {"correct": 0, "reviewed": 0, "accuracy": None}
    assert stats["annotate"]["accuracy_all_time"]["accuracy"] is None
    assert stats["verify"] == {"verified": 0, "accepted": 0, "faulty_found": 0}
    assert stats["window"] == 100


def test_overall_pairs_with_overlap_is_global(client, dataset, ann, login_as):
    imgs = dataset["images"]
    # Resolve one candidate pair to has_overlap at the dataset level (scientist).
    login_as(dataset["scientist"])
    resp = client.post(
        "/api/v1/dataset/candidates/batch/status-change/has_overlap",
        json=[{"image_a": imgs[0], "image_b": imgs[1]}],
    )
    assert resp.status_code == 200, resp.text

    login_as(ann)
    assert _get_stats(client)["overlap"]["overall_pairs_with_overlap"] == 1


def test_window_less_than_one_is_422(client, dataset, ann):
    resp = client.get("/api/v1/annotate/stats/me?window=0")
    assert resp.status_code == 422, resp.text


# ------------------------- community (site-wide) -------------------------


def _get_community_stats(client):
    resp = client.get("/api/v1/annotate/stats/overall")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_community_stats_requires_auth(client):
    assert client.get("/api/v1/annotate/stats/overall").status_code == 401


def test_community_stats_dataset_totals(client, dataset, ann):
    stats = _get_community_stats(client)
    assert stats["users_total"] >= 2  # scientist + ann, at least
    assert stats["regions_total"] >= 1
    assert stats["dives_total"] >= 1
    assert stats["images_total"] >= 3


def test_community_overlap_totals_aggregate_across_players(client, dataset, ann, seed_user, login_as):
    imgs = dataset["images"]
    other = seed_user(username="other", role="annotator", expert_level=0)

    login_as(ann)
    v1 = _vote(client, imgs[0], imgs[1], no_overlap=False)
    login_as(other)
    v2 = _vote(client, imgs[1], imgs[2], no_overlap=True)

    login_as(dataset["scientist"])
    _review_candidate(client, v1, "approve")
    _review_candidate(client, v2, "approve")
    # Resolve both candidate pairs at the dataset level.
    assert client.post(
        "/api/v1/dataset/candidates/batch/status-change/has_overlap",
        json=[{"image_a": imgs[0], "image_b": imgs[1]}],
    ).status_code == 200
    assert client.post(
        "/api/v1/dataset/candidates/batch/status-change/no_overlap",
        json=[{"image_a": imgs[1], "image_b": imgs[2]}],
    ).status_code == 200

    login_as(ann)
    overlap = _get_community_stats(client)["overlap"]
    assert overlap["votes_cast"] == 2  # from both ann and other, not just the caller
    assert overlap["pairs_with_overlap"] == 1
    assert overlap["pairs_no_overlap"] == 1
    assert overlap["pairs_still_open"] == 0


def test_community_annotate_totals_aggregate_across_players(client, dataset, ann, seed_user, login_as):
    imgs = dataset["images"]
    other = seed_user(username="other", role="annotator", expert_level=0)

    login_as(ann)
    p1 = _point(client, imgs[0], imgs[1])
    login_as(other)
    p2 = _point(client, imgs[0], imgs[1])
    _point(client, imgs[1], imgs[2])  # left pending

    login_as(dataset["scientist"])
    _review_point(client, p1, "approve")
    _review_point(client, p2, "fail")

    login_as(ann)
    annotate = _get_community_stats(client)["annotate"]
    assert annotate["points_submitted"] == 3
    assert annotate["points_verified"] == 1
    assert annotate["points_pending_review"] == 1
    assert annotate["pairs_annotated"] == 2


def test_community_verify_totals_aggregate_across_players(client, dataset, ann, seed_user, login_as):
    imgs = dataset["images"]
    junior = seed_user(username="junior", role="annotator", expert_level=0)
    login_as(junior)
    p1 = _point(client, imgs[0], imgs[1])
    p2 = _point(client, imgs[1], imgs[2])
    c1 = _vote(client, imgs[0], imgs[1], no_overlap=False)

    login_as(ann)
    _review_point(client, p1, "approve")
    _review_point(client, p2, "fail")
    _review_candidate(client, c1, "approve")

    verify = _get_community_stats(client)["verify"]
    assert verify["reviews_completed"] == 3
    assert verify["accepted"] == 2
    assert verify["rejected"] == 1
