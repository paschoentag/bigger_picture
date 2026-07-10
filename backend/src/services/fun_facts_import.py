"""Admin zip import for fun facts: upserts by uuid, images and all.

Consumes exactly the zip format `dataset_export.py::build_fun_facts_zip`
produces: fun_facts.csv, helper_images.csv (both comma-delimited, matching
`write_fun_facts_csv`/`write_helper_images_csv`), and a helper_images/ folder
holding the referenced image files at the exact `filepath` recorded in
helper_images.csv. A plain CSV isn't enough on its own since fun facts can
reference helper images that don't exist in this database yet - the images
have to travel with the import.

created_at/created_by_uuid in fun_facts.csv are accepted for round-trip
compatibility with that export but are otherwise ignored - a new fact is
always attributed to the importing admin and stamped with the current time,
and an existing fact's created_at/created_by are never touched by an update.
Same for helper_images.csv's created_at/created_by_uuid.
"""

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from blake3 import blake3
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.v1.dataset._metadata import encode_metadata
from src.schema.fun_facts import FunFact
from src.schema.helper_images import HelperImage
from src.schema.regions import Region
from src.services.assets import read_image_dimensions, resolve_asset_path, stage_source_file
from src.services.errors import ConflictError
from src.services.fun_facts import create_fun_fact
from src.services.helper_images import create_helper_image
from src.services.lookups import get_by_uuid


@dataclass
class FunFactImportError(Exception):
    """A single import failure, pinpointing which file/row caused it.

    `row` is the 1-based CSV row number including the header (so the first
    data row is row 2), or `None` for file-level errors (e.g. a missing
    helper_images/ folder).
    """

    file: str
    row: int | None
    reason: str

    def __post_init__(self) -> None:
        location = f"{self.file} row {self.row}" if self.row is not None else self.file
        super().__init__(f"{location}: {self.reason}")


@dataclass
class FunFactImportSummary:
    created: int = 0
    updated: int = 0
    helper_images_created: int = 0


def _read_csv(path: Path) -> list[dict[str, str | None]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _parse_row(row: dict[str, str | None], row_no: int) -> dict[str, Any]:
    uuid_raw = (row.get("uuid") or "").strip()
    try:
        fact_uuid = UUID(uuid_raw)
    except ValueError:
        raise FunFactImportError("fun_facts.csv", row_no, f"invalid uuid: {uuid_raw!r}")

    title = (row.get("title") or "").strip()
    if not title:
        raise FunFactImportError("fun_facts.csv", row_no, "title is required")

    fact_raw = (row.get("fact") or "").strip()
    if not fact_raw:
        raise FunFactImportError("fun_facts.csv", row_no, "fact is required")
    try:
        fact = json.loads(fact_raw)
    except ValueError:
        raise FunFactImportError("fun_facts.csv", row_no, f"invalid fact JSON: {fact_raw!r}")

    min_level_raw = (row.get("min_level") or "").strip()
    if min_level_raw:
        try:
            min_level = int(min_level_raw)
        except ValueError:
            raise FunFactImportError("fun_facts.csv", row_no, f"invalid min_level: {min_level_raw!r}")
    else:
        min_level = 0

    return {"uuid": fact_uuid, "title": title, "fact": fact, "min_level": min_level}


def _resolve_region_id(db: Session, row: dict[str, str | None], row_no: int) -> int | None:
    region_uuid_raw = (row.get("region_uuid") or "").strip()
    if not region_uuid_raw:
        return None
    try:
        region_uuid = UUID(region_uuid_raw)
    except ValueError:
        raise FunFactImportError("fun_facts.csv", row_no, f"invalid region_uuid: {region_uuid_raw!r}")
    region = get_by_uuid(db, Region, region_uuid.bytes)
    if region is None:
        raise FunFactImportError("fun_facts.csv", row_no, f"region not found: {region_uuid_raw!r}")
    return region.id


def _resolve_image_id(db: Session, row: dict[str, str | None], row_no: int) -> int | None:
    image_uuid_raw = (row.get("image_uuid") or "").strip()
    if not image_uuid_raw:
        return None
    try:
        image_uuid = UUID(image_uuid_raw)
    except ValueError:
        raise FunFactImportError("fun_facts.csv", row_no, f"invalid image_uuid: {image_uuid_raw!r}")
    helper_image = get_by_uuid(db, HelperImage, image_uuid.bytes)
    if helper_image is None:
        raise FunFactImportError("fun_facts.csv", row_no, f"helper image not found: {image_uuid_raw!r}")
    return helper_image.id


def _import_helper_images(
    db: Session, work_dir: Path, creator_id: int
) -> tuple[int, list[tuple[Path, Path]]]:
    """Upsert helper_images.csv against helper_images/ in `work_dir`.

    A uuid that already exists is left untouched (and its file is not
    re-staged) - reimporting the same fun-facts-zip export must be safe to
    repeat. A new uuid stages its file for a move into `ASSETS_DIR`, applied
    by the caller only after a successful commit.
    """
    csv_path = work_dir / "helper_images.csv"
    if not csv_path.exists():
        return 0, []
    helper_images_root = work_dir / "helper_images"

    pending: list[tuple[Path, Path]] = []
    count = 0
    for row_no, row in enumerate(_read_csv(csv_path), start=2):
        uuid_raw = (row.get("uuid") or "").strip()
        try:
            helper_image_uuid = UUID(uuid_raw)
        except ValueError:
            raise FunFactImportError("helper_images.csv", row_no, f"invalid uuid: {uuid_raw!r}")

        if get_by_uuid(db, HelperImage, helper_image_uuid.bytes) is not None:
            continue

        filepath = (row.get("filepath") or "").strip()
        if not filepath:
            raise FunFactImportError("helper_images.csv", row_no, "filepath is required")
        filename = (row.get("filename") or "").strip() or filepath

        if not helper_images_root.is_dir():
            raise FunFactImportError(
                "helper_images.csv", None, "helper_images/ folder is required when helper_images.csv is present"
            )
        try:
            source_file = resolve_asset_path(filepath, base_dir=work_dir)
        except ValueError as exc:
            raise FunFactImportError("helper_images.csv", row_no, f"invalid filepath: {exc}") from exc
        if not source_file.is_file():
            raise FunFactImportError("helper_images.csv", row_no, f"file not found in zip: {filepath!r}")

        try:
            final_dest = resolve_asset_path(filepath)
        except ValueError as exc:
            raise FunFactImportError("helper_images.csv", row_no, f"invalid filepath: {exc}") from exc

        temp_path = stage_source_file(source_file)
        try:
            read_image_dimensions(temp_path)
        except ValueError as exc:
            temp_path.unlink(missing_ok=True)
            raise FunFactImportError("helper_images.csv", row_no, f"could not decode image: {exc}") from exc

        digest = blake3(temp_path.read_bytes()).digest()

        try:
            create_helper_image(
                db,
                uuid=helper_image_uuid,
                filepath=filepath,
                filename=filename,
                blake3_hash=digest,
                creator_id=creator_id,
            )
        except ConflictError as exc:
            temp_path.unlink(missing_ok=True)
            raise FunFactImportError(
                "helper_images.csv", row_no, "filepath already in use by a different helper image"
            ) from exc

        pending.append((temp_path, final_dest))
        count += 1
    return count, pending


def run_fun_facts_import(
    db: Session, work_dir: Path, creator_id: int
) -> tuple[FunFactImportSummary, list[tuple[Path, Path]]]:
    """Upsert every row of a fun-facts-zip export (fun_facts.csv +
    helper_images.csv + helper_images/) against `work_dir`, an extracted zip
    root.

    helper_images.csv is processed first, so fun_facts.csv rows in the same
    import can reference a helper image the zip is introducing for the first
    time. A fun fact uuid that already exists has its title/fact/min_level/
    region/image fully overwritten from the row - a blank region_uuid/
    image_uuid clears that field, it does not leave the existing value
    unchanged, since each row is the complete desired state, not a partial
    patch. A new uuid is created and attributed to `creator_id`.

    Does not commit; raises `FunFactImportError` on the first invalid row.
    The caller is responsible for rolling back on error and committing on
    success, so the whole import stays all-or-nothing. Returns the summary
    plus pending `(temp_path, final_dest)` file moves for new helper images -
    the caller must apply these only after a successful commit.
    """
    summary = FunFactImportSummary()

    csv_path = work_dir / "fun_facts.csv"
    if not csv_path.exists():
        raise FunFactImportError("fun_facts.csv", None, "fun_facts.csv is required")

    summary.helper_images_created, pending_moves = _import_helper_images(db, work_dir, creator_id)

    for row_no, row in enumerate(_read_csv(csv_path), start=2):
        parsed = _parse_row(row, row_no)
        region_id = _resolve_region_id(db, row, row_no)
        image_id = _resolve_image_id(db, row, row_no)

        existing = get_by_uuid(db, FunFact, parsed["uuid"].bytes)
        if existing is not None:
            existing.title = parsed["title"]
            existing.fact_json = encode_metadata(parsed["fact"])
            existing.min_level = parsed["min_level"]
            existing.region_id = region_id
            existing.image_id = image_id
            try:
                db.flush()
            except IntegrityError as exc:
                raise FunFactImportError(
                    "fun_facts.csv", row_no, "title already in use by a different fact"
                ) from exc
            summary.updated += 1
        else:
            try:
                create_fun_fact(
                    db,
                    uuid=parsed["uuid"],
                    title=parsed["title"],
                    fact=parsed["fact"],
                    min_level=parsed["min_level"],
                    region_id=region_id,
                    image_id=image_id,
                    creator_id=creator_id,
                )
            except ConflictError as exc:
                raise FunFactImportError(
                    "fun_facts.csv", row_no, "title already in use by a different fact"
                ) from exc
            summary.created += 1
    return summary, pending_moves
