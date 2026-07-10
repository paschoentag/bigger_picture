import io
import re
import sqlite3
import zipfile
from pathlib import Path

import pytest

from src.password_auth.hashing import verify_password


def _admin(seed_user, login_as):
    admin = seed_user(username="admin", role="admin")
    login_as(admin)
    return admin


_FILENAME_RE = re.compile(r"^db_backup_\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(-\d+)?\.zip$")


def _build_zip(files: dict[str, bytes | str]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def test_create_backup_produces_downloadable_zip_with_db_entry(client, seed_user, login_as, backup_dir):
    _admin(seed_user, login_as)
    resp = client.post("/api/v1/admin/backups/create")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert _FILENAME_RE.match(body["filename"])
    assert body["size_bytes"] > 0
    assert body["created_at"] is not None

    zip_path = Path(backup_dir) / body["filename"]
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["app.db"]
        assert zf.read("app.db")[:16] == b"SQLite format 3\x00"


def test_create_backup_reflects_committed_data(client, seed_user, login_as, backup_dir, tmp_path):
    _admin(seed_user, login_as)
    create_resp = client.post("/api/v1/admin/users/create", json={
        "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2", "username": "snapshotted",
        "password": "correct horse battery staple",
    })
    assert create_resp.status_code == 201, create_resp.text

    resp = client.post("/api/v1/admin/backups/create")
    assert resp.status_code == 201, resp.text
    filename = resp.json()["filename"]

    with zipfile.ZipFile(Path(backup_dir) / filename) as zf:
        extracted = tmp_path / "extracted.db"
        extracted.write_bytes(zf.read("app.db"))

    conn = sqlite3.connect(extracted)
    row = conn.execute("SELECT username FROM users WHERE username = 'snapshotted'").fetchone()
    conn.close()
    assert row is not None


def test_create_backup_omits_auth_db_when_no_password_ever_set(client, seed_user, login_as, backup_dir):
    _admin(seed_user, login_as)
    resp = client.post("/api/v1/admin/backups/create")
    assert resp.status_code == 201, resp.text

    with zipfile.ZipFile(Path(backup_dir) / resp.json()["filename"]) as zf:
        assert zf.namelist() == ["app.db"]


def test_create_backup_includes_auth_db_when_a_password_exists(
    client, seed_user, login_as, set_password, backup_dir, tmp_path
):
    admin = _admin(seed_user, login_as)
    set_password(admin, "correct horse battery staple")

    resp = client.post("/api/v1/admin/backups/create")
    assert resp.status_code == 201, resp.text

    with zipfile.ZipFile(Path(backup_dir) / resp.json()["filename"]) as zf:
        assert set(zf.namelist()) == {"app.db", "auth.db"}
        assert zf.read("auth.db")[:16] == b"SQLite format 3\x00"

        extracted = tmp_path / "extracted-auth.db"
        extracted.write_bytes(zf.read("auth.db"))

    conn = sqlite3.connect(extracted)
    row = conn.execute("SELECT password_hash FROM password_credentials WHERE user_uuid = ?", (admin.uuid,)).fetchone()
    conn.close()
    assert row is not None
    assert verify_password("correct horse battery staple", row[0])


def test_list_backups_returns_size_and_parsed_timestamp(client, seed_user, login_as):
    _admin(seed_user, login_as)
    first = client.post("/api/v1/admin/backups/create").json()["filename"]
    second = client.post("/api/v1/admin/backups/create").json()["filename"]

    resp = client.get("/api/v1/admin/backups")
    assert resp.status_code == 200
    filenames = [b["filename"] for b in resp.json()["backups"]]
    assert first in filenames
    assert second in filenames
    for backup in resp.json()["backups"]:
        assert backup["size_bytes"] > 0
        assert backup["created_at"] is not None
    # sorted newest-first
    assert filenames == sorted(filenames, reverse=True)


def test_list_ignores_tmp_staging_dir(client, seed_user, login_as, backup_dir):
    _admin(seed_user, login_as)
    stray_dir = Path(backup_dir) / ".tmp" / "some-job"
    stray_dir.mkdir(parents=True)
    (stray_dir / "partial.zip").write_bytes(b"not finished")

    resp = client.get("/api/v1/admin/backups")
    assert resp.status_code == 200
    assert resp.json()["backups"] == []


def test_list_includes_hand_added_file_with_null_created_at(client, seed_user, login_as, backup_dir):
    _admin(seed_user, login_as)
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    (Path(backup_dir) / "manually-copied.zip").write_bytes(b"hand added")

    resp = client.get("/api/v1/admin/backups")
    assert resp.status_code == 200
    entry = next(b for b in resp.json()["backups"] if b["filename"] == "manually-copied.zip")
    assert entry["created_at"] is None


def test_download_backup_returns_zip_bytes(client, seed_user, login_as, backup_dir):
    _admin(seed_user, login_as)
    filename = client.post("/api/v1/admin/backups/create").json()["filename"]

    resp = client.get(f"/api/v1/admin/backups/{filename}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert resp.content == (Path(backup_dir) / filename).read_bytes()


def test_download_missing_filename_is_404(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.get("/api/v1/admin/backups/db_backup_2020-01-01T00:00:00.zip/download")
    assert resp.status_code == 404


def test_download_traversal_filename_is_404(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.get("/api/v1/admin/backups/%2e%2e%2fapp.db/download")
    assert resp.status_code == 404


def test_delete_backup_removes_file(client, seed_user, login_as, backup_dir):
    _admin(seed_user, login_as)
    filename = client.post("/api/v1/admin/backups/create").json()["filename"]
    assert (Path(backup_dir) / filename).is_file()

    resp = client.post(f"/api/v1/admin/backups/{filename}/delete")
    assert resp.status_code == 204
    assert not (Path(backup_dir) / filename).exists()

    resp = client.post(f"/api/v1/admin/backups/{filename}/delete")
    assert resp.status_code == 404


def test_upload_accepts_valid_zip_with_server_generated_filename(client, seed_user, login_as):
    _admin(seed_user, login_as)
    zbuf = _build_zip({"app.db": b"fake db bytes"})
    resp = client.post(
        "/api/v1/admin/backups/upload",
        files={"file": ("fixture.zip", zbuf, "application/zip")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["filename"] != "fixture.zip"
    assert _FILENAME_RE.match(body["filename"])
    assert body["size_bytes"] > 0


def test_upload_rejects_non_zip_is_422(client, seed_user, login_as):
    _admin(seed_user, login_as)
    resp = client.post(
        "/api/v1/admin/backups/upload",
        files={"file": ("fixture.zip", io.BytesIO(b"not a zip file"), "application/zip")},
    )
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/v1/admin/backups/create"),
        ("get", "/api/v1/admin/backups"),
        ("get", "/api/v1/admin/backups/db_backup_2020-01-01T00:00:00.zip/download"),
        ("post", "/api/v1/admin/backups/db_backup_2020-01-01T00:00:00.zip/delete"),
        ("post", "/api/v1/admin/backups/upload"),
    ],
)
def test_non_admin_is_403(client, seed_user, login_as, method, path):
    scientist = seed_user(username="sci", role="scientist")
    login_as(scientist)
    resp = getattr(client, method)(path)
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/v1/admin/backups/create"),
        ("get", "/api/v1/admin/backups"),
        ("get", "/api/v1/admin/backups/db_backup_2020-01-01T00:00:00.zip/download"),
        ("post", "/api/v1/admin/backups/db_backup_2020-01-01T00:00:00.zip/delete"),
        ("post", "/api/v1/admin/backups/upload"),
    ],
)
def test_unauthenticated_is_401(client, method, path):
    resp = getattr(client, method)(path)
    assert resp.status_code == 401
