import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.v1.dataset._metadata import encode_metadata
from src.schema.dives import Dive
from src.schema.images import Image
from src.services.assets import (
    detect_image_extension,
    read_image_dimensions,
    resolve_asset_path,
    stage_source_file,
    write_base64_image,
)
from src.services.errors import ConflictError
from src.services.lookups import get_by_uuid
from src.util import new_uuid, now_ms


def resolve_dive_id(db: Session, dive_uuid: UUID) -> int | None:
    dive = get_by_uuid(db, Dive, dive_uuid.bytes)
    return dive.id if dive is not None else None


def ingest_base64_image(filepath: str, image_b64: str) -> tuple[int, int, Path, bool]:
    """Validate path, write the decoded image, and read its dimensions.

    Returns `(size_x, size_y, path, pre_existed)`. `pre_existed` records whether
    the destination file already existed before writing, so a failed DB insert
    can unlink only the file it actually created (avoiding orphaned assets).

    Used by the single-item image create endpoint, where the image bytes
    arrive base64-encoded in the request body.
    """
    try:
        path = resolve_asset_path(filepath)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid filepath")
    pre_existed = path.exists()
    try:
        write_base64_image(path, image_b64)
    except Exception:  # invalid base64 / write failure
        if not pre_existed:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Invalid image data")
    try:
        size_x, size_y = read_image_dimensions(path)
    except ValueError:
        if not pre_existed:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Could not decode image")
    return size_x, size_y, path, pre_existed


def create_image(
    db: Session,
    *,
    uuid: UUID,
    filename: str,
    filepath: str,
    dive_id: int,
    status_id: int,
    size_x: int,
    size_y: int,
    metadata: Any | None,
    difficulty: int | None,
    priority: int | None,
    creator_id: int,
) -> Image:
    """Build, add, and flush a new `Image` row. Does not commit and does no file I/O.

    Raises `ConflictError` if the uuid or filepath already exists.
    """
    image = Image(
        uuid=uuid.bytes,
        created_at=now_ms(),
        created_by=creator_id,
        filename=filename,
        filepath=filepath,
        dive_id=dive_id,
        status_id=status_id,
        size_x=size_x,
        size_y=size_y,
        metadata_json=encode_metadata(metadata),
        difficulty=difficulty,
        priority=priority,
    )
    db.add(image)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("Image already exists") from exc
    return image


@dataclass
class ImageZipImportError(Exception):
    """A single failure while importing an images-only zip, pinpointing the offending file."""

    file: str
    reason: str

    def __post_init__(self) -> None:
        super().__init__(f"{self.file}: {self.reason}")


def import_images_zip(
    db: Session, extract_dir: Path, *, dive_id: int, dive_uuid: UUID, status_id: int, creator_id: int
) -> tuple[int, int, list[tuple[Path, Path]]]:
    """Create one Image per image file found anywhere under `extract_dir`.

    An optional `images.csv` (semicolon-delimited, columns `filename;uuid`) at the
    root of `extract_dir` maps specific filenames to caller-chosen uuids; any
    image file not named in it gets a fresh random uuid. Non-image files (the csv
    itself, `__MACOSX/` junk, etc.) are counted as skipped rather than erroring -
    "is this an image" is decided by magic-byte sniffing (`detect_image_extension`),
    never by file extension.

    Returns `(created, skipped, pending_moves)`, where `pending_moves` are
    `(temp_path, final_dest)` pairs the caller must move into place after commit,
    mirroring the zip-upload dataset import's all-or-nothing staging pattern.
    Raises `ImageZipImportError` on a bad csv row or a uuid/filepath conflict;
    the caller is responsible for cleaning up any already-staged temp files.
    """
    csv_path = extract_dir / "images.csv"
    uuid_by_filename: dict[str, UUID] = {}
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row_no, row in enumerate(reader, start=2):
                filename = (row.get("filename") or "").strip()
                uuid_raw = (row.get("uuid") or "").strip()
                if not filename or not uuid_raw:
                    raise ImageZipImportError("images.csv", f"row {row_no}: filename and uuid are both required")
                try:
                    uuid_by_filename[filename] = UUID(uuid_raw)
                except ValueError:
                    raise ImageZipImportError("images.csv", f"row {row_no}: invalid uuid {uuid_raw!r}")

    pending: list[tuple[Path, Path]] = []
    created = 0
    skipped = 0
    for path in sorted(extract_dir.rglob("*")):
        if not path.is_file() or path == csv_path:
            continue
        try:
            extension = detect_image_extension(path)
        except ValueError:
            skipped += 1
            continue

        filename = path.name
        image_uuid = uuid_by_filename.get(filename, new_uuid())
        filepath = f"{dive_uuid}/{image_uuid}.{extension}"
        try:
            final_dest = resolve_asset_path(filepath)
        except ValueError as exc:
            raise ImageZipImportError(filename, f"invalid filepath: {exc}") from exc

        temp_path = stage_source_file(path)
        try:
            size_x, size_y = read_image_dimensions(temp_path)
        except ValueError as exc:
            temp_path.unlink(missing_ok=True)
            raise ImageZipImportError(filename, f"could not decode image: {exc}") from exc

        try:
            create_image(
                db,
                uuid=image_uuid,
                filename=filename,
                filepath=filepath,
                dive_id=dive_id,
                status_id=status_id,
                size_x=size_x,
                size_y=size_y,
                metadata=None,
                difficulty=None,
                priority=None,
                creator_id=creator_id,
            )
        except ConflictError as exc:
            temp_path.unlink(missing_ok=True)
            raise ImageZipImportError(filename, str(exc)) from exc

        pending.append((temp_path, final_dest))
        created += 1

    return created, skipped, pending
