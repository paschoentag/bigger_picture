import base64
import csv
import io
import uuid
import zipfile

import pytest
from PIL import Image as PILImage


@pytest.fixture
def scientist(seed_user, login_as):
    user = seed_user(username="sci-export", role="scientist", expert_level=5)
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
    u = _new_uuid()
    resp = client.post(
        "/api/v1/dataset/images/create",
        json={
            "uuid": u,
            "filename": filepath,
            "filepath": filepath,
            "dive_uuid": dive,
            "image": _png_b64(),
        },
    )
    assert resp.status_code == 201, resp.text
    return u


def _open_pair(client, image_a, image_b):
    assert client.post(
        "/api/v1/dataset/pairs/create", json={"image_a": image_a, "image_b": image_b}
    ).status_code == 201
    resp = client.post(
        "/api/v1/dataset/pairs/batch/status-change/open",
        json=[{"image_a": image_a, "image_b": image_b}],
    )
    assert resp.status_code == 200, resp.text


def _create_point_annotation(client, image_a, image_b, x1=1, y1=2, x2=3, y2=4) -> str:
    u = _new_uuid()
    resp = client.post(
        "/api/v1/annotate/points/create",
        json={"uuid": u, "image_a": image_a, "image_b": image_b, "x1": x1, "y1": y1, "x2": x2, "y2": y2},
    )
    assert resp.status_code == 201, resp.text
    return u


def _open_candidate(client, image_a, image_b):
    assert client.post(
        "/api/v1/dataset/candidates/create", json={"image_a": image_a, "image_b": image_b}
    ).status_code == 201
    resp = client.post(
        "/api/v1/dataset/candidates/batch/status-change/open",
        json=[{"image_a": image_a, "image_b": image_b}],
    )
    assert resp.status_code == 200, resp.text


def _create_candidate_annotation(client, image_a, image_b, no_overlap=False) -> str:
    u = _new_uuid()
    resp = client.post(
        "/api/v1/annotate/candidate/create",
        json={"uuid": u, "image_a": image_a, "image_b": image_b, "no_overlap": no_overlap},
    )
    assert resp.status_code == 201, resp.text
    return u


def _create_fun_fact(client, title, with_image=False) -> str:
    u = _new_uuid()
    payload = {"uuid": u, "title": title, "fact": {"text": title}}
    if with_image:
        payload["image"] = _png_b64()
        payload["image_filename"] = "fact.png"
    resp = client.post("/api/v1/dataset/fun-facts/create", json=payload)
    assert resp.status_code == 201, resp.text
    return u


def _zip_from_response(resp) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(resp.content))


# --------------------------------------------------------------------------
# Role gating
# --------------------------------------------------------------------------

_EXPORT_GET_URLS = [
    "/api/v1/dataset/export/full",
    "/api/v1/dataset/export/full-csv-only",
    "/api/v1/dataset/export/points-flat",
    "/api/v1/dataset/export/candidates-flat",
    "/api/v1/dataset/export/fun-facts",
    "/api/v1/dataset/export/fun-facts-zip",
]


@pytest.mark.parametrize("url", _EXPORT_GET_URLS)
def test_export_role_gating_annotator_forbidden(client, seed_user, login_as, url):
    login_as(seed_user(username="ann-export", role="annotator"))
    assert client.get(url).status_code == 403


@pytest.mark.parametrize("url", _EXPORT_GET_URLS)
def test_export_role_gating_no_cookie_unauthorized(client, url):
    assert client.get(url).status_code == 401


def test_export_dive_zip_role_gating_annotator_forbidden(client, scientist, seed_user, login_as):
    dive = _make_dive(client, title="gate-dive")
    login_as(seed_user(username="ann-export-2", role="annotator"))
    resp = client.get(f"/api/v1/dataset/export/dive?dive={dive}")
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# Fun facts CSV (#3)
# --------------------------------------------------------------------------


def test_export_fun_facts_csv_drops_ids_and_resolves_uuids(client, scientist):
    region = _new_uuid()
    assert client.post(
        "/api/v1/dataset/regions/create", json={"uuid": region, "title": "fact-region"}
    ).status_code == 201
    fact = _new_uuid()
    resp = client.post(
        "/api/v1/dataset/fun-facts/create",
        json={"uuid": fact, "title": "octopus", "fact": {"text": "3 hearts"}, "region": region},
    )
    assert resp.status_code == 201, resp.text

    resp = client.get("/api/v1/dataset/export/fun-facts")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {
        "uuid", "created_at", "created_by_uuid", "title", "fact", "min_level", "region_uuid", "image_uuid",
    }
    assert row["uuid"] == fact
    assert row["region_uuid"] == region
    assert row["image_uuid"] == ""
    assert row["title"] == "octopus"


# --------------------------------------------------------------------------
# Flat-view CSV exports (#2, reused by #5)
# --------------------------------------------------------------------------


def test_export_points_flat_filters_by_dive_and_drops_internal_ids(client, scientist):
    dive_a = _make_dive(client, title="flat-a")
    dive_b = _make_dive(client, title="flat-b")
    a1 = _make_image(client, dive_a, "a1.png")
    a2 = _make_image(client, dive_a, "a2.png")
    b1 = _make_image(client, dive_b, "b1.png")
    b2 = _make_image(client, dive_b, "b2.png")
    _open_pair(client, a1, a2)
    _open_pair(client, b1, b2)
    ann_a = _create_point_annotation(client, a1, a2)
    _create_point_annotation(client, b1, b2)

    resp = client.get(f"/api/v1/dataset/export/points-flat?dive={dive_a}")
    assert resp.status_code == 200, resp.text
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 1
    assert rows[0]["uuid"] == ann_a
    assert {rows[0]["image1_uuid"], rows[0]["image2_uuid"]} == {a1, a2}
    assert rows[0]["dive_uuid"] == dive_a
    assert "id" not in rows[0]
    assert "pair_id" not in rows[0]


def test_export_points_flat_unknown_dive_404s(client, scientist):
    resp = client.get(f"/api/v1/dataset/export/points-flat?dive={_new_uuid()}")
    assert resp.status_code == 404


def test_export_candidates_flat_filters_by_dive_and_drops_internal_ids(client, scientist):
    dive_a = _make_dive(client, title="cflat-a")
    dive_b = _make_dive(client, title="cflat-b")
    a1 = _make_image(client, dive_a, "ca1.png")
    a2 = _make_image(client, dive_a, "ca2.png")
    b1 = _make_image(client, dive_b, "cb1.png")
    b2 = _make_image(client, dive_b, "cb2.png")
    _open_candidate(client, a1, a2)
    _open_candidate(client, b1, b2)
    vote_a = _create_candidate_annotation(client, a1, a2)
    _create_candidate_annotation(client, b1, b2)

    resp = client.get(f"/api/v1/dataset/export/candidates-flat?dive={dive_a}")
    assert resp.status_code == 200, resp.text
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 1
    assert rows[0]["uuid"] == vote_a
    assert {rows[0]["image1_uuid"], rows[0]["image2_uuid"]} == {a1, a2}
    assert "id" not in rows[0]
    assert "candidate_pair_id" not in rows[0]


def test_export_candidates_flat_unknown_dive_404s(client, scientist):
    resp = client.get(f"/api/v1/dataset/export/candidates-flat?dive={_new_uuid()}")
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# Full dataset zip (#1)
# --------------------------------------------------------------------------


def test_export_full_dataset_zip_contains_all_tables_and_assets(client, scientist):
    dive = _make_dive(client, title="full-dive")
    img_a = _make_image(client, dive, "full_a.png")
    img_b = _make_image(client, dive, "full_b.png")
    _open_pair(client, img_a, img_b)
    _create_point_annotation(client, img_a, img_b)
    _open_candidate(client, img_a, img_b)
    _create_candidate_annotation(client, img_a, img_b)
    _create_fun_fact(client, "full-export-fact", with_image=True)

    resp = client.get("/api/v1/dataset/export/full")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"

    zf = _zip_from_response(resp)
    names = zf.namelist()
    expected_csvs = {
        "users.csv", "labels.csv", "cameras.csv", "regions.csv", "dives.csv", "images.csv",
        "image_pairs.csv", "candidate_pairs.csv", "point_annotations.csv", "candidate_annotations.csv",
        "fun_facts.csv", "helper_images.csv", "seen_facts.csv", "quest_claims.csv",
    }
    assert expected_csvs.issubset(set(names))
    assert any(name.startswith("images/") for name in names)
    assert any(name.startswith("helper_images/") for name in names)

    images_csv = list(csv.DictReader(io.StringIO(zf.read("images.csv").decode())))
    for row in images_csv:
        assert f"images/{row['filepath']}" in names

    pairs_csv = list(csv.DictReader(io.StringIO(zf.read("image_pairs.csv").decode())))
    assert len(pairs_csv) == 1
    assert set(pairs_csv[0].keys()) == {
        "image1_uuid", "image2_uuid", "created_at", "created_by_uuid", "difficulty", "priority", "status",
    }
    assert {pairs_csv[0]["image1_uuid"], pairs_csv[0]["image2_uuid"]} == {img_a, img_b}

    candidate_pairs_csv = list(csv.DictReader(io.StringIO(zf.read("candidate_pairs.csv").decode())))
    assert len(candidate_pairs_csv) == 1
    assert set(candidate_pairs_csv[0].keys()) == {
        "image1_uuid", "image2_uuid", "created_at", "created_by_uuid", "status", "reviewed_at", "reviewed_by_uuid",
    }

    point_annotations_csv = list(csv.DictReader(io.StringIO(zf.read("point_annotations.csv").decode())))
    assert len(point_annotations_csv) == 1
    assert {point_annotations_csv[0]["pair_image1_uuid"], point_annotations_csv[0]["pair_image2_uuid"]} == {img_a, img_b}
    assert "pair_uuid" not in point_annotations_csv[0]

    candidate_annotations_csv = list(csv.DictReader(io.StringIO(zf.read("candidate_annotations.csv").decode())))
    assert len(candidate_annotations_csv) == 1
    assert {
        candidate_annotations_csv[0]["candidate_image1_uuid"],
        candidate_annotations_csv[0]["candidate_image2_uuid"],
    } == {img_a, img_b}
    assert "candidate_uuid" not in candidate_annotations_csv[0]


def test_export_full_dataset_csv_only_zip_excludes_asset_folders(client, scientist):
    dive = _make_dive(client, title="full-csv-dive")
    img_a = _make_image(client, dive, "full_csv_a.png")
    img_b = _make_image(client, dive, "full_csv_b.png")
    _open_pair(client, img_a, img_b)
    _create_fun_fact(client, "full-csv-only-fact", with_image=True)

    resp = client.get("/api/v1/dataset/export/full-csv-only")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"

    zf = _zip_from_response(resp)
    names = zf.namelist()
    expected_csvs = {
        "users.csv", "labels.csv", "cameras.csv", "regions.csv", "dives.csv", "images.csv",
        "image_pairs.csv", "candidate_pairs.csv", "point_annotations.csv", "candidate_annotations.csv",
        "fun_facts.csv", "helper_images.csv", "seen_facts.csv", "quest_claims.csv",
    }
    assert expected_csvs.issubset(set(names))
    assert not any(name.startswith("images/") for name in names)
    assert not any(name.startswith("helper_images/") for name in names)

    images_csv = list(csv.DictReader(io.StringIO(zf.read("images.csv").decode())))
    assert {row["uuid"] for row in images_csv} == {img_a, img_b}


def test_full_dataset_export_covers_every_schema_table(client, scientist):
    """Regression test: every table in the schema is either covered by the full
    export or explicitly excluded (status lookup tables, field_documentation).

    Written after a real bug where a new table (quest_claims, added by a
    concurrently-merged feature) was silently missing from the export because
    the writer list was a hand-maintained snapshot from when the export was
    built. This compares against SQLAlchemy's actual table registry instead of
    another hand-maintained list, so a future forgotten table fails here rather
    than shipping silently.
    """
    import src.schema.annotation_statuses  # noqa: F401
    import src.schema.cameras  # noqa: F401
    import src.schema.candidate_annotations  # noqa: F401
    import src.schema.candidate_pairs  # noqa: F401
    import src.schema.candidate_statuses  # noqa: F401
    import src.schema.dives  # noqa: F401
    import src.schema.field_documentation  # noqa: F401
    import src.schema.fun_facts  # noqa: F401
    import src.schema.helper_images  # noqa: F401
    import src.schema.image_pairs  # noqa: F401
    import src.schema.image_statuses  # noqa: F401
    import src.schema.images  # noqa: F401
    import src.schema.labels  # noqa: F401
    import src.schema.pair_statuses  # noqa: F401
    import src.schema.point_annotations  # noqa: F401
    import src.schema.quest_claims  # noqa: F401
    import src.schema.regions  # noqa: F401
    import src.schema.seen_facts  # noqa: F401
    import src.schema.users  # noqa: F401
    from src.schema.base import Base
    from src.services.dataset_export import _FULL_EXPORT_WRITERS

    excluded_tables = {
        "image_statuses", "pair_statuses", "candidate_statuses", "annotation_statuses",
        "field_documentation",
    }
    exported_tables = {filename[: -len(".csv")] for filename, _writer in _FULL_EXPORT_WRITERS}
    all_tables = set(Base.metadata.tables.keys())

    assert all_tables - excluded_tables == exported_tables


# --------------------------------------------------------------------------
# Fun facts zip (#4)
# --------------------------------------------------------------------------


def test_export_fun_facts_zip_includes_only_referenced_helper_images(client, scientist):
    _create_fun_fact(client, "fact-with-image", with_image=True)
    _create_fun_fact(client, "fact-without-image", with_image=False)

    resp = client.get("/api/v1/dataset/export/fun-facts-zip")
    assert resp.status_code == 200, resp.text
    zf = _zip_from_response(resp)
    names = zf.namelist()
    assert "fun_facts.csv" in names
    assert "helper_images.csv" in names

    fun_facts_csv = list(csv.DictReader(io.StringIO(zf.read("fun_facts.csv").decode())))
    assert len(fun_facts_csv) == 2

    helper_images_csv = list(csv.DictReader(io.StringIO(zf.read("helper_images.csv").decode())))
    assert len(helper_images_csv) == 1

    helper_image_files = [name for name in names if name.startswith("helper_images/") and not name.endswith(".csv")]
    assert len(helper_image_files) == 1


# --------------------------------------------------------------------------
# Per-dive zip (#5)
# --------------------------------------------------------------------------


def test_export_dive_zip_includes_all_dive_images_regardless_of_pairing(client, scientist):
    dive = _make_dive(client, title="dive-zip")
    paired_a = _make_image(client, dive, "paired_a.png")
    paired_b = _make_image(client, dive, "paired_b.png")
    unpaired = _make_image(client, dive, "unpaired.png")
    _open_pair(client, paired_a, paired_b)
    _create_point_annotation(client, paired_a, paired_b)

    resp = client.get(f"/api/v1/dataset/export/dive?dive={dive}")
    assert resp.status_code == 200, resp.text
    zf = _zip_from_response(resp)
    names = zf.namelist()
    assert "points.csv" in names
    assert "candidates.csv" in names
    assert "images/paired_a.png" in names
    assert "images/paired_b.png" in names
    assert "images/unpaired.png" in names

    points_csv = list(csv.DictReader(io.StringIO(zf.read("points.csv").decode())))
    assert len(points_csv) == 1
    assert {points_csv[0]["image1_uuid"], points_csv[0]["image2_uuid"]} == {paired_a, paired_b}


def test_export_dive_zip_unknown_dive_404s(client, scientist):
    resp = client.get(f"/api/v1/dataset/export/dive?dive={_new_uuid()}")
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# Background cleanup
# --------------------------------------------------------------------------


def test_export_full_dataset_zip_cleans_up_temp_dir(client, scientist, tmp_path, monkeypatch):
    created_dirs = []
    import src.api.v1.dataset.export as export_module

    real_mkdtemp = export_module.tempfile.mkdtemp

    def _tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created_dirs.append(path)
        return path

    monkeypatch.setattr(export_module.tempfile, "mkdtemp", _tracking_mkdtemp)

    resp = client.get("/api/v1/dataset/export/full")
    assert resp.status_code == 200

    assert created_dirs, "expected export endpoint to create a temp dir"
    import os

    assert not os.path.exists(created_dirs[0])
