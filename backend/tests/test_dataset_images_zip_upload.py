import io
import os
import uuid
import zipfile

import pytest
from PIL import Image as PILImage


@pytest.fixture
def scientist(seed_user, login_as):
    user = seed_user(username="sci", role="scientist")
    login_as(user)
    return user


@pytest.fixture
def dive(client):
    region = str(uuid.uuid4())
    assert client.post("/api/v1/dataset/regions/create", json={"uuid": region, "title": "R"}).status_code == 201
    camera = str(uuid.uuid4())
    assert client.post("/api/v1/dataset/cameras/create", json={"uuid": camera, "title": "C"}).status_code == 201
    dive_uuid = str(uuid.uuid4())
    resp = client.post(
        "/api/v1/dataset/dives/create",
        json={"uuid": dive_uuid, "title": "Dive 1", "region": region, "camera": camera},
    )
    assert resp.status_code == 201, resp.text
    return dive_uuid


def _png_bytes(width: int = 8, height: int = 6) -> bytes:
    img = PILImage.new("RGB", (width, height), (10, 20, 30))
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


def _upload(client, dive_uuid: str, files: dict[str, bytes | str]):
    zbuf = _build_zip(files)
    return client.post(
        "/api/v1/dataset/images/zip-upload",
        data={"dive_uuid": dive_uuid},
        files={"file": ("fixture.zip", zbuf, "application/zip")},
    )


def test_zip_upload_images_happy_path_random_uuids(client, scientist, dive):
    resp = _upload(client, dive, {"a.png": _png_bytes(), "b.png": _png_bytes(width=10, height=10)})
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"created": 2, "skipped": 0}

    images = client.get(f"/api/v1/dataset/images?dive={dive}").json()["images"]
    assert {img["filename"] for img in images} == {"a.png", "b.png"}
    for img in images:
        assert img["status"] == "hidden"


def test_zip_upload_images_with_csv_uuid_mapping(client, scientist, dive):
    fixed_uuid = str(uuid.uuid4())
    resp = _upload(
        client,
        dive,
        {
            "images.csv": "filename;uuid\na.png;" + fixed_uuid + "\n",
            "a.png": _png_bytes(),
            "b.png": _png_bytes(width=10, height=10),
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"created": 2, "skipped": 0}  # images.csv itself is excluded, not counted

    images = client.get(f"/api/v1/dataset/images?dive={dive}").json()["images"]
    a = next(img for img in images if img["filename"] == "a.png")
    assert a["uuid"] == fixed_uuid


def test_zip_upload_images_ignores_non_image_files(client, scientist, dive):
    resp = _upload(client, dive, {"a.png": _png_bytes(), "readme.txt": "hello"})
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"created": 1, "skipped": 1}


def test_zip_upload_images_invalid_csv_row(client, scientist, dive):
    resp = _upload(
        client,
        dive,
        {"images.csv": "filename;uuid\na.png;not-a-uuid\n", "a.png": _png_bytes()},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"].startswith("images.csv:")

    images = client.get(f"/api/v1/dataset/images?dive={dive}").json()["images"]
    assert images == []


def test_zip_upload_images_uuid_conflict_rolls_back(client, scientist, dive):
    existing_uuid = str(uuid.uuid4())
    import base64

    resp = client.post(
        "/api/v1/dataset/images/create",
        json={
            "uuid": existing_uuid,
            "filename": "existing.png",
            "filepath": f"{dive}/existing.png",
            "dive_uuid": dive,
            "image": base64.b64encode(_png_bytes()).decode(),
        },
    )
    assert resp.status_code == 201, resp.text

    resp = _upload(
        client,
        dive,
        {
            "images.csv": f"filename;uuid\na.png;{existing_uuid}\n",
            "a.png": _png_bytes(),
            "b.png": _png_bytes(width=10, height=10),
        },
    )
    assert resp.status_code == 422, resp.text

    images = client.get(f"/api/v1/dataset/images?dive={dive}").json()["images"]
    assert len(images) == 1  # only the pre-existing image; b.png's insert was rolled back too


def test_zip_upload_images_nonexistent_dive(client, scientist):
    resp = _upload(client, str(uuid.uuid4()), {"a.png": _png_bytes()})
    assert resp.status_code == 404


def test_zip_upload_images_requires_scientist_role(client, scientist, seed_user, login_as, dive):
    ann = seed_user(username="ann", role="annotator")
    login_as(ann)
    resp = _upload(client, dive, {"a.png": _png_bytes()})
    assert resp.status_code == 403
