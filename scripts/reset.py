#!/usr/bin/env python3
"""Reset local dev state: delete the SQLite databases and upload ledgers.

Removes both backend SQLite databases - the main app database and the
password_auth database (each with their -wal / -shm sidecars) - and every
*.state.json progress ledger under the repo, so the next backend start recreates
empty databases and seed_examples.py re-uploads everything from scratch.

Generated CSVs (images.csv / image_pairs.csv) are left in place, so re-seeding
reuses the same image uuids.

    python scripts/reset.py            # list, then prompt before deleting
    python scripts/reset.py -y         # delete without prompting
    python scripts/reset.py --dry-run  # show what would be removed, delete nothing

Stop the backend first - deleting the database file while it is running leaves
the process writing to an unlinked file until it restarts.
"""

import argparse
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
DEFAULT_DB_PATH = REPO_ROOT / "backend" / "data" / "app.db"
# Separate, self-contained database for scientist/admin password hashes (see
# backend/src/password_auth/) - matches config.AUTH_DATABASE_PATH's default.
DEFAULT_AUTH_DB_PATH = REPO_ROOT / "backend" / "data" / "auth.db"
# WAL journal mode leaves these sidecar files next to the database.
DB_SIDECAR_SUFFIXES = ("", "-wal", "-shm")
# Directories not worth walking when hunting for ledgers.
SKIP_DIRS = {".git", "node_modules", ".venv", ".devenv", "__pycache__"}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--database-path", type=Path, default=DEFAULT_DB_PATH, help=f"main app SQLite file (default: {DEFAULT_DB_PATH})")
    p.add_argument(
        "--auth-database-path",
        type=Path,
        default=DEFAULT_AUTH_DB_PATH,
        help=f"password_auth SQLite file (default: {DEFAULT_AUTH_DB_PATH})",
    )
    p.add_argument("-y", "--yes", action="store_true", help="delete without prompting for confirmation")
    p.add_argument("--dry-run", action="store_true", help="list what would be removed, but delete nothing")
    return p.parse_args(argv)


def find_database_files(db_path: Path) -> list[Path]:
    return [p for suffix in DB_SIDECAR_SUFFIXES if (p := Path(str(db_path) + suffix)).exists()]


def find_state_files(root: Path) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        found += [Path(dirpath) / f for f in filenames if f.endswith(".state.json")]
    return sorted(found)


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main(argv=None):
    args = parse_args(argv)

    targets = (
        find_database_files(args.database_path)
        + find_database_files(args.auth_database_path)
        + find_state_files(REPO_ROOT)
    )
    if not targets:
        print("Nothing to remove; already clean.")
        return

    print("The following will be deleted:")
    for path in targets:
        print(f"  {_display(path)}")

    if args.dry_run:
        print("(dry run - nothing deleted)")
        return

    if not args.yes:
        answer = input(f"\nDelete {len(targets)} file(s)? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return

    for path in targets:
        path.unlink()
        print(f"removed {_display(path)}")
    print(f"Done. Removed {len(targets)} file(s).")


if __name__ == "__main__":
    main()
