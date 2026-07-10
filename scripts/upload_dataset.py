#!/usr/bin/env python3
"""Upload images and create image pairs against the Sea the Bigger Picture dataset API.

Given a folder of images, a CSV mapping each filename to the uuid it should be
assigned, and a CSV listing image pairs (by those uuids), this script:

  1. validates everything locally (files exist, uuids well-formed, pairs
     reference known images) so it fails before touching the API;
  2. resolves the target dive (interactively if --dive-uuid is omitted);
  3. uploads each image via POST /api/v1/dataset/images/create (the image is
     sent base64-encoded in the JSON body; the server writes it to disk and
     reads its dimensions);
  4. creates each pair - image pairs (Stage 2) via /api/v1/dataset/pairs/create
     by default, or candidate overlap pairs (Stage 1) with --pair-kind candidate;
  5. (optional, --publish) flips the uploaded images and pairs from their
     default `hidden` status to `open` via the batch status-change endpoints,
     so they become available for annotation (e.g. /annotate/points/next).

Progress is recorded in a local ledger (default: <files-csv>.state.json) after
each successful upload/pair, so rerunning the script skips work already done
without re-reading files or round-tripping the API. Progress is tracked
per-dive, so uploading the same CSVs to a different --dive-uuid starts fresh for
that dive rather than skipping everything. Delete the ledger to force a full
re-run. Override its location with --state-file.

Authentication needs a user with the `scientist` or `admin` role (the
/api/v1/dataset/* routes require it). Two ways to authenticate:

  --username NAME     log in as an existing user via POST /api/v1/auth/login;
                      the session cookie is captured from the response. Also
                      reads $UPLOAD_USERNAME. Scientist/admin accounts require
                      a password too - pass --password or set $UPLOAD_PASSWORD
                      (annotator accounts have none and ignore it).
  --session-uuid HEX  use a raw session cookie value directly (e.g. the hex
                      string printed by `python -m src.bootstrap_admin`). Also
                      reads $SESSION_UUID.

CSV formats (header row required):

    files CSV:   filename,uuid
    pairs CSV:   image1,image2      (aliases: image_a,image_b)

Both `image1`/`image2` are uuids that must also appear in the files CSV.

Example:

    python scripts/upload_dataset.py \
        --images-dir ./dive_042_photos \
        --files-csv files.csv \
        --pairs-csv pairs.csv \
        --session-uuid 3f2a...e1 \
        --api-base-url http://localhost:8000
"""

import argparse
import base64
import csv
import json
import os
import sys
import uuid as uuidlib
from http.cookies import SimpleCookie
from pathlib import Path
from urllib import error, request

DEFAULT_BASE_URL = "http://localhost:8000"
COOKIE_NAME = "session_uuid"
# Scientist/admin sessions also get a non-httponly CSRF cookie (see
# backend/src/csrf.py), which must be echoed back as this header on every
# state-changing request. Annotator sessions never receive one and are exempt.
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

FILES_FILENAME_KEYS = ("filename",)
FILES_UUID_KEYS = ("uuid",)
PAIRS_A_KEYS = ("image1", "image_a")
PAIRS_B_KEYS = ("image2", "image_b")

# Pair kinds map to their REST resource segment under /api/v1/dataset/:
#   image     -> image_pairs   (Stage 2, feeds /annotate/points/next)
#   candidate -> candidate_pairs (Stage 1 overlap, feeds /annotate/candidate/next)
PAIR_ENDPOINTS = {"image": "pairs", "candidate": "candidates"}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class ApiClient:
    """Minimal stdlib HTTP client that carries the auth cookie on every call.

    The `session_uuid` cookie may be supplied up front (a raw hex value) or
    obtained by `login()`. Every response is scanned for `Set-Cookie` headers,
    so both the session cookie the server issues at login and the scientist/
    admin CSRF cookie are captured automatically - the `httponly` flag only
    hides the session cookie from browser JavaScript, not from a raw HTTP
    client like this one. The captured CSRF token is echoed back as
    X-CSRF-Token on every state-changing request, as the frontend does.
    """

    def __init__(self, base_url: str, session_uuid: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.session_uuid = session_uuid
        self.csrf_token: str | None = None

    def _capture_cookie(self, headers) -> None:
        for raw in headers.get_all("Set-Cookie", []):
            jar = SimpleCookie()
            jar.load(raw)
            if COOKIE_NAME in jar:
                self.session_uuid = jar[COOKIE_NAME].value
            if CSRF_COOKIE_NAME in jar:
                self.csrf_token = jar[CSRF_COOKIE_NAME].value

    def _request(self, method: str, path: str, body=None):
        url = f"{self.base_url}{path}"
        headers = {}
        if self.session_uuid:
            headers["Cookie"] = f"{COOKIE_NAME}={self.session_uuid}"
        if method.upper() not in SAFE_METHODS and self.csrf_token:
            headers[CSRF_HEADER_NAME] = self.csrf_token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = request.Request(url, data=data, method=method, headers=headers)
        try:
            with request.urlopen(req) as resp:
                self._capture_cookie(resp.headers)
                return resp.status, _parse_json(resp.read())
        except error.HTTPError as exc:
            self._capture_cookie(exc.headers)
            return exc.code, _parse_json(exc.read())
        except error.URLError as exc:
            raise SystemExit(f"ERROR: cannot reach API at {url}: {exc.reason}")

    def get(self, path: str):
        return self._request("GET", path)

    def post(self, path: str, body):
        return self._request("POST", path, body)

    def refresh_csrf_token(self) -> dict:
        """GET /api/v1/auth/me to (re)capture the CSRF cookie for the current session.

        Needed when the session was supplied as a raw --session-uuid rather than
        obtained via login() - the CSRF cookie is only ever set by the login/
        signup/me responses, never assumed from a bare session cookie. A no-op
        for annotator sessions, which never receive a CSRF cookie. Returns the
        user record; raises SystemExit if the session isn't valid.
        """
        status, payload = self.get("/api/v1/auth/me")
        if status != 200:
            raise SystemExit(f"ERROR: session is not valid (HTTP {status}): {_detail(payload)}")
        return payload if isinstance(payload, dict) else {}

    def login(self, username: str, password: str | None = None) -> dict:
        """Log in by username and capture the session cookie.

        `password` is required for scientist/admin accounts and ignored for
        annotator accounts (which have none). Returns the user record
        (includes `role`). Raises SystemExit on an unknown username, missing
        or wrong password, or any other non-200 response.
        """
        status, payload = self.post("/api/v1/auth/login", {"username": username, "password": password})
        if status == 404:
            raise SystemExit(f"ERROR: login failed - unknown username {username!r}.")
        if status == 401:
            raise SystemExit(
                f"ERROR: login failed - invalid credentials for {username!r}. "
                "Scientist/admin accounts need --password (or $UPLOAD_PASSWORD)."
            )
        if status != 200 or not self.session_uuid:
            raise SystemExit(f"ERROR: login failed (HTTP {status}): {_detail(payload)}")
        return payload if isinstance(payload, dict) else {}


def _parse_json(raw: bytes):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return {"detail": raw.decode(errors="replace")}


def _detail(payload) -> str:
    if isinstance(payload, dict) and "detail" in payload:
        return str(payload["detail"])
    return str(payload)


# --------------------------------------------------------------------------- #
# Progress ledger
# --------------------------------------------------------------------------- #
class ProgressState:
    """A local record of what has already been persisted server-side, so reruns
    can skip finished work without re-encoding files or round-tripping the API.

    Progress is scoped per target dive: the ledger file holds a separate record
    for each dive uuid, so uploading the same images.csv to a different dive is
    tracked independently and never wrongly skipped. Within a dive, images are
    keyed by their uuid and pairs by the two uuids sorted (matching how the
    server orders them, so (a, b) and (b, a) are the same pair). The file is
    written atomically after each new entry, so an interrupted run keeps
    whatever progress it made, and records for other dives are preserved.

    File layout:
        {"dives": {"<dive_uuid>": {"images": [...], "pairs": [[a, b], ...]}}}
    """

    def __init__(self, path: Path, dive_uuid: str):
        self.path = path
        self.dive_uuid = dive_uuid
        self._all: dict = {}  # full file contents, keyed by dive uuid
        self.images: set[str] = set()
        self.pairs: set[tuple[str, str]] = set()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            self._all = data["dives"] if isinstance(data, dict) and "dives" in data else {}
            record = self._all.get(self.dive_uuid, {})
            self.images = set(record.get("images", []))
            self.pairs = {tuple(sorted(p)) for p in record.get("pairs", [])}
        except (ValueError, OSError, TypeError, KeyError) as exc:
            print(
                f"WARNING: ignoring unreadable progress file {self.path} ({exc}); starting fresh.",
                file=sys.stderr,
            )
            self._all, self.images, self.pairs = {}, set(), set()

    def _save(self) -> None:
        self._all[self.dive_uuid] = {
            "images": sorted(self.images),
            "pairs": sorted(list(p) for p in self.pairs),
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({"dives": self._all}, indent=2))
        os.replace(tmp, self.path)  # atomic on the same filesystem

    def has_image(self, image_uuid: str) -> bool:
        return image_uuid in self.images

    def mark_image(self, image_uuid: str) -> None:
        self.images.add(image_uuid)
        self._save()

    @staticmethod
    def pair_key(a: str, b: str) -> tuple[str, str]:
        return tuple(sorted((a, b)))

    def has_pair(self, a: str, b: str) -> bool:
        return self.pair_key(a, b) in self.pairs

    def mark_pair(self, a: str, b: str) -> None:
        self.pairs.add(self.pair_key(a, b))
        self._save()


# --------------------------------------------------------------------------- #
# CSV loading + validation
# --------------------------------------------------------------------------- #
def _pick_column(fieldnames, candidates, csv_path):
    lowered = {name.lower().strip(): name for name in (fieldnames or [])}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    raise SystemExit(
        f"ERROR: {csv_path}: expected a column named one of {candidates}; "
        f"found {list(fieldnames or [])}"
    )


def _valid_uuid(value: str) -> str:
    """Return the canonical uuid string, or raise ValueError."""
    return str(uuidlib.UUID(value.strip()))


def load_files_csv(csv_path: Path):
    """Return an ordered list of (filename, uuid_str)."""
    with csv_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        fn_col = _pick_column(reader.fieldnames, FILES_FILENAME_KEYS, csv_path)
        uuid_col = _pick_column(reader.fieldnames, FILES_UUID_KEYS, csv_path)
        rows = []
        for lineno, row in enumerate(reader, start=2):
            filename = (row.get(fn_col) or "").strip()
            raw_uuid = (row.get(uuid_col) or "").strip()
            if not filename and not raw_uuid:
                continue  # skip blank lines
            if not filename:
                raise SystemExit(f"ERROR: {csv_path}:{lineno}: empty filename")
            try:
                canonical = _valid_uuid(raw_uuid)
            except ValueError:
                raise SystemExit(f"ERROR: {csv_path}:{lineno}: invalid uuid {raw_uuid!r}")
            rows.append((filename, canonical))
    return rows


def load_pairs_csv(csv_path: Path):
    """Return an ordered list of (uuid_a, uuid_b)."""
    with csv_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        a_col = _pick_column(reader.fieldnames, PAIRS_A_KEYS, csv_path)
        b_col = _pick_column(reader.fieldnames, PAIRS_B_KEYS, csv_path)
        rows = []
        for lineno, row in enumerate(reader, start=2):
            raw_a = (row.get(a_col) or "").strip()
            raw_b = (row.get(b_col) or "").strip()
            if not raw_a and not raw_b:
                continue
            try:
                a = _valid_uuid(raw_a)
                b = _valid_uuid(raw_b)
            except ValueError:
                raise SystemExit(f"ERROR: {csv_path}:{lineno}: invalid uuid in pair")
            rows.append((a, b))
    return rows


def validate(files_rows, pairs_rows, images_dir: Path):
    """Fail fast on any local problem before we start hitting the API."""
    errors = []

    seen_uuids = {}
    seen_filenames = {}
    for filename, image_uuid in files_rows:
        if image_uuid in seen_uuids and seen_uuids[image_uuid] != filename:
            errors.append(f"uuid {image_uuid} is assigned to more than one file")
        seen_uuids[image_uuid] = filename
        if filename in seen_filenames and seen_filenames[filename] != image_uuid:
            errors.append(f"file {filename} is assigned more than one uuid")
        seen_filenames[filename] = image_uuid
        if not (images_dir / filename).is_file():
            errors.append(f"file not found in --images-dir: {filename}")

    known = set(seen_uuids)
    for a, b in pairs_rows:
        if a == b:
            errors.append(f"pair references the same image twice: {a}")
        for ref in (a, b):
            if ref not in known:
                errors.append(f"pair references uuid not in files CSV: {ref}")

    if errors:
        print(f"Found {len(errors)} validation error(s):", file=sys.stderr)
        for msg in errors:
            print(f"  - {msg}", file=sys.stderr)
        raise SystemExit(1)


# --------------------------------------------------------------------------- #
# Dive resolution
# --------------------------------------------------------------------------- #
def resolve_dive(client: ApiClient, dive_uuid: str | None) -> str:
    status, payload = client.get("/api/v1/dataset/dives")
    if status == 401:
        raise SystemExit("ERROR: not authenticated - check --session-uuid.")
    if status == 403:
        raise SystemExit("ERROR: session user lacks the 'scientist'/'admin' role.")
    if status != 200:
        raise SystemExit(f"ERROR: could not list dives (HTTP {status}): {_detail(payload)}")

    dives = payload.get("dives", []) if isinstance(payload, dict) else []
    by_uuid = {d["uuid"]: d for d in dives}

    if dive_uuid is not None:
        if dive_uuid not in by_uuid:
            raise SystemExit(f"ERROR: dive {dive_uuid} not found among {len(dives)} dive(s).")
        return dive_uuid

    if not dives:
        raise SystemExit("ERROR: no dives exist yet; create one before uploading images.")

    print("Available dives:")
    for i, d in enumerate(dives, start=1):
        print(f"  [{i}] {d['title']}  ({d['uuid']})")
    while True:
        choice = input(f"Select a dive [1-{len(dives)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(dives):
            return dives[int(choice) - 1]["uuid"]
        print("  invalid selection, try again")


# --------------------------------------------------------------------------- #
# Upload phases
# --------------------------------------------------------------------------- #
def upload_images(client, files_rows, images_dir: Path, dive_uuid: str, state: ProgressState, dry_run: bool):
    created = skipped = failed = 0
    for filename, image_uuid in files_rows:
        filepath = f"{dive_uuid}/{filename}"
        if state.has_image(image_uuid):
            skipped += 1
            print(f"  skip     {filename} (done in a previous run)")
            continue
        if dry_run:
            print(f"  DRY-RUN would upload {filename} -> {image_uuid} at {filepath}")
            continue
        image_b64 = base64.b64encode((images_dir / filename).read_bytes()).decode()
        body = {
            "uuid": image_uuid,
            "filename": filename,
            "filepath": filepath,
            "dive_uuid": dive_uuid,
            "image": image_b64,
        }
        status, payload = client.post("/api/v1/dataset/images/create", body)
        # Both a fresh create and a pre-existing row mean the image is on the
        # server, so record either as done to skip it next time.
        if status in (201, 409):
            state.mark_image(image_uuid)
        if status == 201:
            created += 1
            print(f"  uploaded {filename} -> {image_uuid}")
        elif status == 409:
            skipped += 1
            print(f"  skip     {filename} (already on server)")
        else:
            failed += 1
            print(f"  FAIL     {filename} (HTTP {status}): {_detail(payload)}", file=sys.stderr)
    return created, skipped, failed


def create_pairs(client, pairs_rows, state: ProgressState, pair_kind: str, dry_run: bool):
    endpoint = f"/api/v1/dataset/{PAIR_ENDPOINTS[pair_kind]}/create"
    created = skipped = failed = 0
    for a, b in pairs_rows:
        if state.has_pair(a, b):
            skipped += 1
            print(f"  skip   {a} <-> {b} (done in a previous run)")
            continue
        if dry_run:
            print(f"  DRY-RUN would pair {a} <-> {b}")
            continue
        status, payload = client.post(endpoint, {"image_a": a, "image_b": b})
        if status in (201, 409):
            state.mark_pair(a, b)
        if status == 201:
            created += 1
            print(f"  paired {a} <-> {b}")
        elif status == 409:
            skipped += 1
            print(f"  skip   {a} <-> {b} (already on server)")
        else:
            failed += 1
            print(f"  FAIL   {a} <-> {b} (HTTP {status}): {_detail(payload)}", file=sys.stderr)
    return created, skipped, failed


def publish(client, state: ProgressState, status: str, pair_kind: str, dry_run: bool) -> int:
    """Flip every uploaded image and pair to `status` so they become usable.

    Works off the ledger (`state`), not the raw CSVs, so only items confirmed on
    the server are touched - the batch endpoints 404 the whole request if any
    referenced item is missing. Both endpoints are idempotent, so re-running is
    safe. Returns the number of failed batch calls.
    """
    image_uuids = sorted(state.images)
    pair_refs = [{"image_a": a, "image_b": b} for a, b in sorted(state.pairs)]

    if dry_run:
        print(f"  DRY-RUN would set {len(image_uuids)} image(s) and {len(pair_refs)} pair(s) to {status!r}")
        return 0

    failed = 0
    for label, path, body in (
        ("images", f"/api/v1/dataset/images/batch/status-change/{status}", image_uuids),
        ("pairs", f"/api/v1/dataset/{PAIR_ENDPOINTS[pair_kind]}/batch/status-change/{status}", pair_refs),
    ):
        if not body:
            continue
        code, payload = client.post(path, body)
        if code == 200:
            updated = payload.get("updated") if isinstance(payload, dict) else len(body)
            print(f"  {label} -> {status}: {updated} updated")
        else:
            failed += 1
            print(f"  FAIL {label} -> {status} (HTTP {code}): {_detail(payload)}", file=sys.stderr)
    return failed


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--images-dir", required=True, type=Path, help="folder containing the image files")
    p.add_argument("--files-csv", required=True, type=Path, help="CSV with columns: filename,uuid")
    p.add_argument("--pairs-csv", required=True, type=Path, help="CSV with columns: image1,image2 (uuids)")
    p.add_argument("--dive-uuid", default=None, help="target dive uuid (omit to pick interactively)")
    p.add_argument(
        "--pair-kind",
        choices=sorted(PAIR_ENDPOINTS),
        default="image",
        help="'image' pairs (Stage 2, /annotate/points) or 'candidate' overlap pairs "
        "(Stage 1, /annotate/candidate); default: image",
    )
    p.add_argument(
        "--username",
        default=os.environ.get("UPLOAD_USERNAME"),
        help="authenticate by logging in as this (existing) user; needs scientist/admin role. "
        "Defaults to $UPLOAD_USERNAME.",
    )
    p.add_argument(
        "--password",
        default=os.environ.get("UPLOAD_PASSWORD"),
        help="password for --username; required for scientist/admin accounts, ignored for "
        "annotator accounts. Defaults to $UPLOAD_PASSWORD.",
    )
    p.add_argument(
        "--session-uuid",
        default=os.environ.get("SESSION_UUID"),
        help="auth cookie value (hex) to use instead of --username; defaults to $SESSION_UUID",
    )
    p.add_argument("--api-base-url", default=DEFAULT_BASE_URL, help=f"default {DEFAULT_BASE_URL}")
    p.add_argument(
        "--state-file",
        default=None,
        type=Path,
        help="progress ledger for resumable reruns (default: <files-csv>.state.json)",
    )
    p.add_argument("--dry-run", action="store_true", help="validate and resolve the dive, but make no create calls")
    p.add_argument(
        "--publish",
        action="store_true",
        help="after uploading, set the images and pairs to --publish-status so they become usable",
    )
    p.add_argument(
        "--publish-status",
        default="open",
        help="status to publish images/pairs to when --publish is set (default: open)",
    )
    return p.parse_args(argv)


def _default_state_path(files_csv: Path, pair_kind: str) -> Path:
    # Image runs keep the plain name; other kinds get a suffix so their ledgers
    # don't collide when the same CSVs are uploaded as a different pair kind.
    suffix = ".state.json" if pair_kind == "image" else f".{pair_kind}.state.json"
    return files_csv.with_name(files_csv.name + suffix)


def main(argv=None):
    args = parse_args(argv)

    if not args.username and not args.session_uuid:
        raise SystemExit(
            "ERROR: no credentials; pass --username (login) or --session-uuid "
            "(raw cookie), or set $UPLOAD_USERNAME / $SESSION_UUID."
        )
    if not args.images_dir.is_dir():
        raise SystemExit(f"ERROR: --images-dir is not a directory: {args.images_dir}")

    files_rows = load_files_csv(args.files_csv)
    pairs_rows = load_pairs_csv(args.pairs_csv)
    validate(files_rows, pairs_rows, args.images_dir)
    print(f"Validated {len(files_rows)} image(s) and {len(pairs_rows)} pair(s).")

    client = ApiClient(args.api_base_url, args.session_uuid)
    if args.username:
        user = client.login(args.username, args.password)
    else:
        # A raw --session-uuid never went through login(), so the CSRF cookie
        # (required on every write for scientist/admin sessions) hasn't been
        # captured yet.
        user = client.refresh_csrf_token()
    role = user.get("role")
    print(f"Logged in as {user.get('username')!r} (role: {role}).")
    if role not in ("scientist", "admin"):
        print(
            f"WARNING: role {role!r} cannot write to the dataset; "
            "uploads will be rejected (need scientist/admin).",
            file=sys.stderr,
        )

    dive_uuid = resolve_dive(client, args.dive_uuid)
    print(f"Target dive: {dive_uuid}")

    # The ledger is scoped to the resolved dive, so it must be created after the
    # dive is known - progress for one dive never masks work for another. The
    # default name also carries the pair kind so image and candidate runs over
    # the same CSVs keep separate ledgers.
    state_path = args.state_file or _default_state_path(args.files_csv, args.pair_kind)
    state = ProgressState(state_path, dive_uuid)
    state.load()
    if state.images or state.pairs:
        print(
            f"Resuming from {state_path}: for this dive, "
            f"{len(state.images)} image(s) and {len(state.pairs)} pair(s) already done."
        )
    print()

    print("Uploading images:")
    img_created, img_skipped, img_failed = upload_images(
        client, files_rows, args.images_dir, dive_uuid, state, args.dry_run
    )

    print(f"\nCreating {args.pair_kind} pairs:")
    pair_created, pair_skipped, pair_failed = create_pairs(
        client, pairs_rows, state, args.pair_kind, args.dry_run
    )

    publish_failed = 0
    if args.publish:
        print(f"\nPublishing (status -> {args.publish_status}):")
        publish_failed = publish(client, state, args.publish_status, args.pair_kind, args.dry_run)

    print(
        f"\nDone. images: {img_created} created, {img_skipped} skipped, {img_failed} failed | "
        f"pairs: {pair_created} created, {pair_skipped} skipped, {pair_failed} failed"
    )
    if img_failed or pair_failed or publish_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
