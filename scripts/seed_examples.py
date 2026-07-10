#!/usr/bin/env python3
"""Seed the backend with the bundled example datasets under scripts/example_data.

For each dataset this:
  1. ensures its dive exists (creating the region + dive if needed);
  2. generates images.csv (filename,uuid) and image_pairs.csv via sort_images;
  3. uploads the images, creates the pairs, and publishes them (status -> open)
     so they're ready for annotation.

Idempotent: existing dives are reused (matched by title) and the region/dive
uuids are derived from their titles, so re-running never creates duplicates.

Authentication defaults to logging in as the USERNAME/PASSWORD constants below
(needs the scientist/admin role, which requires a password) - these match the
SEED_ADMIN_USERNAME/SEED_ADMIN_PASSWORD backend auto-seeds on first boot (see
docker-compose.yml and backend/README.md), so the zero-arg form works out of
the box against a freshly started backend. Override with --username/--password
or --session-uuid.

    python scripts/seed_examples.py                # seed every dataset as admin
    python scripts/seed_examples.py north_sea      # seed just one
    python scripts/seed_examples.py --username sci --password <10-127 chars>
"""

import argparse
import uuid
from collections import namedtuple
from pathlib import Path

import sort_images
import upload_dataset

HERE = Path(__file__).resolve().parent
EXAMPLES_DIR = HERE / "example_data"
USERNAME = "admin"
# Matches backend/src/config.py's SEED_ADMIN_PASSWORD default - the password
# the backend auto-seeds for USERNAME on first boot (see docker-compose.yml).
PASSWORD = "change-me-please"
# Fixed namespace so region/dive uuids are derived from their titles and are
# therefore stable across runs (no duplicates on re-run).
UUID_NAMESPACE = uuid.UUID("0b3e5f9a-1c2d-4e6f-8a9b-0c1d2e3f4a5b")

# Each dataset lives in EXAMPLES_DIR/<name>/images and gets its own dive/region.
# `generate` controls whether the CSVs are produced from the image folder with
# sort_images, or already ship with the dataset and are used as-is.
Dataset = namedtuple("Dataset", "name dive_title region_title files_csv pairs_csv generate pair_kind")
DATASETS = [
    # dive1 ships ready-made CSVs (images.csv + pairs.csv); seed as Stage 1
    # candidate (overlap) pairs.
    Dataset("dive1", "Dive 1", "Dive 1 Region", "images.csv", "pairs.csv", False, "candidate"),
    # north_sea has only images; generate CSVs and seed as Stage 2 image pairs.
    Dataset("north_sea", "North Sea", "North Sea Region", "images.csv", "image_pairs.csv", True, "image"),
]


def parse_args(argv=None):
    names = [d.name for d in DATASETS]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("datasets", nargs="*", metavar="DATASET", help=f"datasets to seed (default: all of {names})")
    p.add_argument("--username", default=USERNAME, help=f"log in as this user (default: {USERNAME})")
    p.add_argument(
        "--password",
        default=PASSWORD,
        help=f"password for --username; required for scientist/admin accounts (default: {PASSWORD!r}, "
        "matching the backend's auto-seeded admin password)",
    )
    p.add_argument("--session-uuid", default=None, help="raw session cookie (or set $SESSION_UUID)")
    p.add_argument("--api-base-url", default=None, help=f"backend URL (default {upload_dataset.DEFAULT_BASE_URL})")
    p.add_argument("-n", "--num-subsequent", type=int, default=5, help="images to pair with each image (default: 5)")
    return p.parse_args(argv)


def select_datasets(names):
    if not names:
        return DATASETS
    by_name = {d.name: d for d in DATASETS}
    selected = []
    for name in names:
        if name not in by_name:
            raise SystemExit(f"ERROR: unknown dataset {name!r}; choose from {sorted(by_name)}")
        selected.append(by_name[name])
    return selected


def dataset_paths(ds: Dataset):
    d = EXAMPLES_DIR / ds.name
    return d / "images", d / ds.files_csv, d / ds.pairs_csv


def _authenticated_client(args, base_url):
    """Build an ApiClient authenticated the same way upload_dataset is."""
    client = upload_dataset.ApiClient(base_url, args.session_uuid)
    if args.session_uuid:
        # A raw session cookie never went through login(), so the CSRF cookie
        # (required on every write for scientist/admin sessions) hasn't been
        # captured yet.
        client.refresh_csrf_token()
    else:
        client.login(args.username, args.password)
    return client


def _find_dive_by_title(client, title):
    status, payload = client.get("/api/v1/dataset/dives")
    if status != 200:
        raise SystemExit(f"ERROR: could not list dives (HTTP {status}): {upload_dataset._detail(payload)}")
    for dive in payload.get("dives", []):
        if dive.get("title") == title:
            return dive["uuid"]
    return None


def ensure_dive(client, dive_title: str, region_title: str) -> str:
    """Return the dive uuid for `dive_title`, creating it (and its region) if missing.

    A dive requires a region; the camera is optional (the backend falls back to
    its well-known "Unknown Camera"), so we don't create one.
    """
    existing = _find_dive_by_title(client, dive_title)
    if existing is not None:
        print(f"  dive {dive_title!r} already exists: {existing}")
        return existing

    region_uuid = str(uuid.uuid5(UUID_NAMESPACE, region_title))
    status, payload = client.post(
        "/api/v1/dataset/regions/create", {"uuid": region_uuid, "title": region_title}
    )
    if status == 201:
        print(f"  created region {region_title!r}: {region_uuid}")
    elif status == 409:
        print(f"  region {region_title!r} already exists: {region_uuid}")
    else:
        raise SystemExit(f"ERROR: region create failed (HTTP {status}): {upload_dataset._detail(payload)}")

    dive_uuid = str(uuid.uuid5(UUID_NAMESPACE, dive_title))
    status, payload = client.post(
        "/api/v1/dataset/dives/create",
        {"uuid": dive_uuid, "title": dive_title, "region": region_uuid},
    )
    if status == 201:
        print(f"  created dive {dive_title!r}: {dive_uuid}")
        return dive_uuid
    if status == 409:
        # A same-titled dive appeared between the list and the create; find it.
        found = _find_dive_by_title(client, dive_title)
        if found is not None:
            return found
    raise SystemExit(f"ERROR: dive create failed (HTTP {status}): {upload_dataset._detail(payload)}")


def seed_dataset(ds: Dataset, args, base_url, client) -> None:
    images_dir, files_csv, pairs_csv = dataset_paths(ds)
    print(f"\n=== {ds.name} ===")
    if not images_dir.is_dir():
        raise SystemExit(f"ERROR: expected images at {images_dir}")

    print(f"[1/3] Ensuring the {ds.dive_title!r} dive exists ...")
    dive_uuid = ensure_dive(client, ds.dive_title, ds.region_title)

    if ds.generate:
        print(f"[2/3] Generating CSVs for {images_dir} ...")
        sort_images.main([
            str(images_dir),
            "-o", str(pairs_csv),
            "-u", str(files_csv),
            "-n", str(args.num_subsequent),
        ])
    else:
        print(f"[2/3] Using existing CSVs ({files_csv.name} + {pairs_csv.name}) ...")
        for path in (files_csv, pairs_csv):
            if not path.is_file():
                raise SystemExit(f"ERROR: expected CSV {path}")

    print("[3/3] Uploading to the backend ...")
    upload_argv = [
        "--images-dir", str(images_dir),
        "--files-csv", str(files_csv),
        "--pairs-csv", str(pairs_csv),
        "--dive-uuid", dive_uuid,
        "--pair-kind", ds.pair_kind,
        # Flip the uploaded images and pairs to `open` so they're immediately
        # available for annotation instead of sitting in the default `hidden`.
        "--publish",
    ]
    # A raw session cookie takes precedence; otherwise log in by username (which
    # defaults to admin). Passing both would let the login override the cookie.
    if args.session_uuid:
        upload_argv += ["--session-uuid", args.session_uuid]
    else:
        upload_argv += ["--username", args.username]
        if args.password:
            upload_argv += ["--password", args.password]
    if args.api_base_url:
        upload_argv += ["--api-base-url", args.api_base_url]

    upload_dataset.main(upload_argv)


def main(argv=None):
    args = parse_args(argv)
    selected = select_datasets(args.datasets)

    base_url = args.api_base_url or upload_dataset.DEFAULT_BASE_URL
    client = _authenticated_client(args, base_url)

    for ds in selected:
        seed_dataset(ds, args, base_url, client)


if __name__ == "__main__":
    main()
