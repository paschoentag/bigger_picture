import csv
import io
import json
import uuid
import zipfile

import pytest
from blake3 import blake3
from PIL import Image as PILImage


@pytest.fixture
def admin(seed_user, login_as):
    user = seed_user(username="admin-fun-facts", role="admin")
    login_as(user)
    return user


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _fun_facts_csv(rows: list[dict[str, str]]) -> str:
    columns = ["uuid", "created_at", "created_by_uuid", "title", "fact", "min_level", "region_uuid", "image_uuid"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in columns})
    return buf.getvalue()


def _helper_images_csv(rows: list[dict[str, str]]) -> str:
    columns = ["uuid", "created_at", "created_by_uuid", "filepath", "filename", "blake3_hash"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in columns})
    return buf.getvalue()


def _png_bytes(width: int = 4, height: int = 4) -> bytes:
    img = PILImage.new("RGB", (width, height), (1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_zip(files: dict[str, bytes | str]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def _upload(client, files: dict[str, bytes | str]):
    zbuf = _build_zip(files)
    return client.post(
        "/api/v1/admin/fun-facts/import",
        files={"file": ("fun_facts.zip", zbuf, "application/zip")},
    )


def _upload_facts(client, rows: list[dict[str, str]], extra_files: dict[str, bytes | str] | None = None):
    files: dict[str, bytes | str] = {"fun_facts.csv": _fun_facts_csv(rows)}
    files.update(extra_files or {})
    return _upload(client, files)


def _make_region(client, title="region") -> str:
    u = _new_uuid()
    resp = client.post("/api/v1/dataset/regions/create", json={"uuid": u, "title": title})
    assert resp.status_code == 201, resp.text
    return u


def _make_helper_image_uuid(client, title="seed-fact") -> str:
    """Mint a helper image indirectly by creating a throwaway fun fact with an image attached."""
    png = _png_b64()
    resp = client.post(
        "/api/v1/dataset/fun-facts/create",
        json={"uuid": _new_uuid(), "title": title, "fact": {"text": "seed"}, "image": png, "image_filename": "x.png"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["image"]["uuid"]


def _png_b64() -> str:
    import base64

    return base64.b64encode(_png_bytes()).decode()


def _find_fact(client, fact_uuid: str) -> dict:
    resp = client.get("/api/v1/dataset/fun-facts?page_size=500")
    assert resp.status_code == 200, resp.text
    matches = [f for f in resp.json()["fun_facts"] if f["uuid"] == fact_uuid]
    assert len(matches) == 1, f"expected exactly one fact with uuid {fact_uuid}, found {len(matches)}"
    return matches[0]


# --------------------------------------------------------------------------
# Role gating
# --------------------------------------------------------------------------


def test_import_role_gating_scientist_forbidden(client, seed_user, login_as):
    login_as(seed_user(username="sci-import", role="scientist"))
    resp = _upload_facts(client, [])
    assert resp.status_code == 403


def test_import_role_gating_annotator_forbidden(client, seed_user, login_as):
    login_as(seed_user(username="ann-import", role="annotator"))
    resp = _upload_facts(client, [])
    assert resp.status_code == 403


def test_import_role_gating_no_cookie_unauthorized(client):
    resp = _upload_facts(client, [])
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# Create / update (upsert by uuid)
# --------------------------------------------------------------------------


def test_import_creates_new_fact_attributed_to_importing_admin(client, admin):
    fact_uuid = _new_uuid()
    resp = _upload_facts(
        client,
        [{"uuid": fact_uuid, "title": "octopus", "fact": json.dumps({"text": "3 hearts"}), "min_level": "2"}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 1, "updated": 0}

    fact = _find_fact(client, fact_uuid)
    assert fact["title"] == "octopus"
    assert fact["fact"] == {"text": "3 hearts"}
    assert fact["min_level"] == 2
    assert fact["created_by"] == str(uuid.UUID(bytes=admin.uuid))
    assert fact["region"] is None
    assert fact["image"] is None


def test_import_ignores_created_at_and_created_by_uuid_columns(client, admin):
    fact_uuid = _new_uuid()
    bogus_user_uuid = _new_uuid()
    resp = _upload_facts(
        client,
        [
            {
                "uuid": fact_uuid,
                "created_at": "1",
                "created_by_uuid": bogus_user_uuid,
                "title": "bogus-provenance",
                "fact": json.dumps({"text": "hi"}),
            }
        ],
    )
    assert resp.status_code == 200, resp.text
    fact = _find_fact(client, fact_uuid)
    assert fact["created_by"] != bogus_user_uuid
    assert fact["created_at"] != 1


def test_import_updates_existing_fact_by_uuid_leaving_provenance_unchanged(client, seed_user, login_as):
    admin1 = seed_user(username="admin-creator", role="admin")
    login_as(admin1)
    fact_uuid = _new_uuid()
    resp = _upload_facts(client, [{"uuid": fact_uuid, "title": "v1", "fact": json.dumps({"text": "v1"})}])
    assert resp.status_code == 200
    original = _find_fact(client, fact_uuid)

    admin2 = seed_user(username="admin-updater", role="admin")
    login_as(admin2)
    resp = _upload_facts(
        client,
        [{"uuid": fact_uuid, "title": "v2", "fact": json.dumps({"text": "v2"}), "min_level": "5"}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 0, "updated": 1}

    updated = _find_fact(client, fact_uuid)
    assert updated["title"] == "v2"
    assert updated["fact"] == {"text": "v2"}
    assert updated["min_level"] == 5
    assert updated["created_at"] == original["created_at"]
    assert updated["created_by"] == original["created_by"] == str(uuid.UUID(bytes=admin1.uuid))


def test_import_resolves_region_and_preexisting_image(client, admin):
    region_uuid = _make_region(client)
    image_uuid = _make_helper_image_uuid(client)

    fact_uuid = _new_uuid()
    resp = _upload_facts(
        client,
        [
            {
                "uuid": fact_uuid,
                "title": "with-region-and-image",
                "fact": json.dumps({"text": "hi"}),
                "region_uuid": region_uuid,
                "image_uuid": image_uuid,
            }
        ],
    )
    assert resp.status_code == 200, resp.text
    fact = _find_fact(client, fact_uuid)
    assert fact["region"] == region_uuid
    assert fact["image"]["uuid"] == image_uuid


def test_import_blank_region_and_image_clears_on_update(client, admin):
    region_uuid = _make_region(client)
    image_uuid = _make_helper_image_uuid(client)

    fact_uuid = _new_uuid()
    resp = _upload_facts(
        client,
        [
            {
                "uuid": fact_uuid,
                "title": "to-be-cleared",
                "fact": json.dumps({"text": "hi"}),
                "region_uuid": region_uuid,
                "image_uuid": image_uuid,
            }
        ],
    )
    assert resp.status_code == 200, resp.text
    assert _find_fact(client, fact_uuid)["region"] == region_uuid

    resp = _upload_facts(client, [{"uuid": fact_uuid, "title": "to-be-cleared", "fact": json.dumps({"text": "hi"})}])
    assert resp.status_code == 200, resp.text
    fact = _find_fact(client, fact_uuid)
    assert fact["region"] is None
    assert fact["image"] is None


# --------------------------------------------------------------------------
# Images travel with the zip
# --------------------------------------------------------------------------


def test_import_creates_new_helper_image_from_zip(client, admin, assets_dir):
    image_uuid = _new_uuid()
    fact_uuid = _new_uuid()
    png = _png_bytes()
    digest = blake3(png).hexdigest()
    filepath = f"helper_images/{digest}.png"

    resp = _upload(
        client,
        {
            "fun_facts.csv": _fun_facts_csv(
                [{"uuid": fact_uuid, "title": "brings-its-own-image", "fact": json.dumps({"text": "hi"}), "image_uuid": image_uuid}]
            ),
            "helper_images.csv": _helper_images_csv(
                [{"uuid": image_uuid, "filepath": filepath, "filename": "octopus.png"}]
            ),
            filepath: png,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 1, "updated": 0}

    fact = _find_fact(client, fact_uuid)
    assert fact["image"]["uuid"] == image_uuid
    assert fact["image"]["filename"] == "octopus.png"

    import os

    assert os.path.isfile(os.path.join(assets_dir, "helper_images", f"{digest}.png"))


def test_import_reimporting_same_zip_is_idempotent_for_helper_images(client, admin, assets_dir):
    image_uuid = _new_uuid()
    fact_uuid = _new_uuid()
    png = _png_bytes()
    digest = blake3(png).hexdigest()
    filepath = f"helper_images/{digest}.png"

    files = {
        "fun_facts.csv": _fun_facts_csv(
            [{"uuid": fact_uuid, "title": "repeat-import", "fact": json.dumps({"text": "hi"}), "image_uuid": image_uuid}]
        ),
        "helper_images.csv": _helper_images_csv(
            [{"uuid": image_uuid, "filepath": filepath, "filename": "octopus.png"}]
        ),
        filepath: png,
    }
    resp = _upload(client, files)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 1, "updated": 0}

    resp = _upload(client, files)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 0, "updated": 1}

    helper_images = client.get("/api/v1/dataset/helper-images").json()
    assert helper_images["total"] == 1


def test_import_helper_images_csv_without_folder_is_422(client, admin):
    image_uuid = _new_uuid()
    resp = _upload(
        client,
        {
            "fun_facts.csv": _fun_facts_csv([{"uuid": _new_uuid(), "title": "x", "fact": "{}"}]),
            "helper_images.csv": _helper_images_csv(
                [{"uuid": image_uuid, "filepath": "helper_images/missing.png", "filename": "x.png"}]
            ),
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["file"] == "helper_images.csv"


def test_import_missing_fun_facts_csv_is_422(client, admin):
    resp = _upload(client, {"helper_images.csv": _helper_images_csv([])})
    assert resp.status_code == 422
    assert resp.json()["detail"]["file"] == "fun_facts.csv"


# --------------------------------------------------------------------------
# Validation / atomicity
# --------------------------------------------------------------------------


def test_import_invalid_uuid_is_422(client, admin):
    resp = _upload_facts(client, [{"uuid": "not-a-uuid", "title": "x", "fact": "{}"}])
    assert resp.status_code == 422
    assert resp.json()["detail"]["row"] == 2


def test_import_missing_title_is_422(client, admin):
    resp = _upload_facts(client, [{"uuid": _new_uuid(), "title": "", "fact": "{}"}])
    assert resp.status_code == 422
    assert resp.json()["detail"]["row"] == 2


def test_import_invalid_fact_json_is_422(client, admin):
    resp = _upload_facts(client, [{"uuid": _new_uuid(), "title": "x", "fact": "{not json"}])
    assert resp.status_code == 422
    assert resp.json()["detail"]["row"] == 2


def test_import_invalid_min_level_is_422(client, admin):
    resp = _upload_facts(client, [{"uuid": _new_uuid(), "title": "x", "fact": "{}", "min_level": "abc"}])
    assert resp.status_code == 422


def test_import_nonexistent_region_is_422(client, admin):
    resp = _upload_facts(client, [{"uuid": _new_uuid(), "title": "x", "fact": "{}", "region_uuid": _new_uuid()}])
    assert resp.status_code == 422
    assert "region" in resp.json()["detail"]["reason"]


def test_import_nonexistent_image_is_422(client, admin):
    resp = _upload_facts(client, [{"uuid": _new_uuid(), "title": "x", "fact": "{}", "image_uuid": _new_uuid()}])
    assert resp.status_code == 422
    assert "image" in resp.json()["detail"]["reason"]


def test_import_title_collision_on_create_is_422(client, admin):
    resp = _upload_facts(client, [{"uuid": _new_uuid(), "title": "dup-title", "fact": "{}"}])
    assert resp.status_code == 200, resp.text

    resp = _upload_facts(client, [{"uuid": _new_uuid(), "title": "dup-title", "fact": "{}"}])
    assert resp.status_code == 422


def test_import_is_all_or_nothing_across_rows(client, admin):
    valid_uuid = _new_uuid()
    resp = _upload_facts(
        client,
        [
            {"uuid": valid_uuid, "title": "should-not-persist", "fact": "{}"},
            {"uuid": "not-a-uuid", "title": "bad-row", "fact": "{}"},
        ],
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["row"] == 3

    resp = client.get("/api/v1/dataset/fun-facts?page_size=500")
    assert resp.status_code == 200
    assert not any(f["uuid"] == valid_uuid for f in resp.json()["fun_facts"])


def test_import_is_all_or_nothing_when_helper_image_stage_fails_after_fact_rows(client, admin):
    """A later helper_images.csv failure must not leave earlier fun_facts.csv rows persisted."""
    image_uuid = _new_uuid()
    fact_uuid = _new_uuid()
    resp = _upload(
        client,
        {
            "fun_facts.csv": _fun_facts_csv(
                [{"uuid": fact_uuid, "title": "should-not-persist", "fact": "{}", "image_uuid": image_uuid}]
            ),
            "helper_images.csv": _helper_images_csv(
                [{"uuid": image_uuid, "filepath": "helper_images/missing.png", "filename": "x.png"}]
            ),
        },
    )
    assert resp.status_code == 422

    resp = client.get("/api/v1/dataset/fun-facts?page_size=500")
    assert resp.status_code == 200
    assert not any(f["uuid"] == fact_uuid for f in resp.json()["fun_facts"])
