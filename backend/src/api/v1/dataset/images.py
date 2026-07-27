import shutil
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src import config
from src.api.deps import require_current_user
from src.api.v1.dataset._metadata import decode_metadata, encode_metadata
from src.constants import IMAGE_STATUS_INT, INT_IMAGE_STATUS, ImageStatus
from src.db import get_db
from src.models.dataset import (
    ImageCreateFromExternalUrlRequest,
    ImageCreateRequest,
    ImageListResponse,
    ImageResponse,
    ImageUpdateRequest,
    ImageZipImportResponse,
)
from src.schema.dives import Dive
from src.schema.images import Image
from src.schema.users import User
from src.services.assets import extract_zip_safely, move_asset, read_image_dimensions, resolve_asset_path, write_temp_image
from src.services.errors import ConflictError
from src.services.images import create_image as _create_image_row
from src.services.images import ImageZipImportError, import_images_zip, ingest_base64_image
from src.services.images import resolve_dive_id as _resolve_dive_id_or_none
from src.services.lookups import get_by_uuid, image_has_point_annotations
from src.util import apply_partial_update

router = APIRouter()


def _to_response(image: Image, db: Session) -> ImageResponse:
    dive = db.get(Dive, image.dive_id)
    creator = db.get(User, image.created_by)
    status = None
    if image.status_id is not None:
        status_enum = INT_IMAGE_STATUS.get(image.status_id)
        status = str(status_enum) if status_enum is not None else None
    return ImageResponse(
        uuid=UUID(bytes=image.uuid),
        created_at=image.created_at,
        created_by=UUID(bytes=creator.uuid),
        filename=image.filename,
        filepath=image.filepath,
        dive=UUID(bytes=dive.uuid),
        status=status,
        size_x=image.size_x,
        size_y=image.size_y,
        metadata=decode_metadata(image.metadata_json),
        difficulty=image.difficulty,
        priority=image.priority,
    )


def _resolve_dive_id(db: Session, dive_uuid: UUID) -> int:
    dive_id = _resolve_dive_id_or_none(db, dive_uuid)
    if dive_id is None:
        raise HTTPException(status_code=404, detail="Dive not found")
    return dive_id


@router.get(
    "",
    response_model=ImageListResponse,
    summary="List Images In Dive",
    description="""
Return a page of the images belonging to the given dive, ordered by creation time. Requires the scientist role.

Fails with 404 if the dive does not exist.
""",
)
def list_images(
    dive: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    dive_id = _resolve_dive_id(db, dive)
    total = db.execute(
        select(func.count()).select_from(Image).where(Image.dive_id == dive_id)
    ).scalar_one()
    images = db.execute(
        select(Image)
        .where(Image.dive_id == dive_id)
        .order_by(Image.created_at)
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).scalars().all()
    return ImageListResponse(images=[_to_response(image, db) for image in images], total=total)


@router.post(
    "/create",
    response_model=ImageResponse,
    status_code=201,
    summary="Create Image",
    description="""
Upload a new image, identified by uuid, into an existing dive. The image bytes are supplied base64-encoded and written to disk at filepath; width and height are computed from the decoded image. Requires the scientist role.

The image is always created with status "hidden".

Fails with 404 if the dive does not exist, 422 if filepath is invalid or the image data cannot be decoded, or 409 if an image with this uuid or filepath already exists.
""",
)
def create_image(payload: ImageCreateRequest, request: Request, db: Session = Depends(get_db)):
    user = require_current_user(request)

    dive_id = _resolve_dive_id(db, payload.dive_uuid)

    size_x, size_y, path, pre_existed = ingest_base64_image(payload.filepath, payload.image)

    try:
        image = _create_image_row(
            db,
            uuid=payload.uuid,
            filename=payload.filename,
            filepath=payload.filepath,
            dive_id=dive_id,
            status_id=IMAGE_STATUS_INT[ImageStatus.HIDDEN],
            size_x=size_x,
            size_y=size_y,
            metadata=payload.metadata,
            difficulty=payload.difficulty,
            priority=payload.priority,
            creator_id=user.id,
        )
    except ConflictError:
        db.rollback()
        # Remove the file we just wrote so a failed create leaves no orphan,
        # but only if it did not pre-exist this request.
        if not pre_existed:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Image already exists")
    db.commit()
    db.refresh(image)
    return _to_response(image, db)


@router.post(
    "/create-from-url",
    response_model=ImageResponse,
    status_code=201,
    summary="Create Image From External URL",
    description="""
Link a new image from an external URL-based source (e.g., an image broker) instead of uploading bytes.
The image is never stored locally; the URL is saved as filepath. Requires the scientist role.

The image is always created with status "hidden". Width and height can be supplied explicitly 
(recommended for performance) or omitted to fetch them from the remote source (slower).

Fails with 404 if the dive does not exist, 422 if filepath is not a valid http(s) URL, 422 if 
size_x/size_y are needed but cannot be fetched, or 409 if an image with this uuid or filepath already exists.
""",
)
def create_image_from_url(payload: ImageCreateFromExternalUrlRequest, request: Request, db: Session = Depends(get_db)):
    user = require_current_user(request)
    
    # Validate filepath is a full external URL
    if not (payload.filepath.startswith("http://") or payload.filepath.startswith("https://")):
        raise HTTPException(status_code=422, detail="filepath must be a full http(s) URL")
    
    dive_id = _resolve_dive_id(db, payload.dive_uuid)
    
    size_x = payload.size_x
    size_y = payload.size_y
    
    # If dimensions not provided, try to fetch them from the URL
    if size_x is None or size_y is None:
        try:
            import tempfile
            import urllib.request
            
            # Download image to temp file
            with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as tmp:
                with urllib.request.urlopen(payload.filepath, timeout=10) as response:
                    if response.status != 200:
                        raise HTTPException(status_code=422, detail=f"Failed to fetch image from URL: HTTP {response.status}")
                    tmp.write(response.read())
                tmp_path = Path(tmp.name)
            
            try:
                fetched_x, fetched_y = read_image_dimensions(tmp_path)
                if size_x is None:
                    size_x = fetched_x
                if size_y is None:
                    size_y = fetched_y
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not fetch image dimensions from URL: {str(e)}")
    
    if size_x is None or size_y is None:
        raise HTTPException(status_code=422, detail="size_x and size_y could not be determined and must be provided explicitly")
    
    try:
        image = _create_image_row(
            db,
            uuid=payload.uuid,
            filename=payload.filename,
            filepath=payload.filepath,
            dive_id=dive_id,
            status_id=IMAGE_STATUS_INT[ImageStatus.HIDDEN],
            size_x=size_x,
            size_y=size_y,
            metadata=payload.metadata,
            difficulty=payload.difficulty,
            priority=payload.priority,
            creator_id=user.id,
        )
    except ConflictError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Image already exists")
    db.commit()
    db.refresh(image)
    return _to_response(image, db)


@router.post(
    "/zip-upload",
    response_model=ImageZipImportResponse,
    status_code=201,
    summary="Bulk Import Images From Zip",
    description="""
Upload a zip archive of image files into an existing dive. Requires the scientist role.

Every file in the zip is inspected by its magic bytes; anything that isn't a recognized image
format is ignored (counted as skipped) rather than erroring, so an optional CSV manifest and
incidental junk (e.g. __MACOSX/) can sit alongside the images.

If the zip also contains a semicolon-delimited `images.csv` at its root, with columns `filename`
and `uuid`, each listed filename is created with that uuid instead of a random one; every other
image gets a fresh random uuid. All images are created with status "hidden".

The whole import is all-or-nothing: any error aborts with nothing persisted and no asset files
left behind.

Fails with 404 if the dive does not exist, or 422 if the zip is malformed, contains an unsafe
path, has an invalid images.csv row, or an image's filename/uuid collides with an existing image.
""",
)
def zip_upload_images(
    request: Request,
    dive_uuid: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = require_current_user(request)
    dive_id = _resolve_dive_id(db, dive_uuid)

    job_id = uuid4()
    work_dir = Path(config.IMPORT_DIR) / str(job_id)
    work_dir.mkdir(parents=True)
    pending_moves: list[tuple[Path, Path]] = []

    try:
        zip_path = work_dir / "upload.zip"
        with open(zip_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        extract_dir = work_dir / "extracted"
        try:
            extract_zip_safely(zip_path, extract_dir)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"<zip>: {exc}")

        created, skipped, pending_moves = import_images_zip(
            db,
            extract_dir,
            dive_id=dive_id,
            dive_uuid=dive_uuid,
            status_id=IMAGE_STATUS_INT[ImageStatus.HIDDEN],
            creator_id=user.id,
        )
        db.commit()
    except ImageZipImportError as exc:
        db.rollback()
        for temp_path, _ in pending_moves:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"{exc.file}: {exc.reason}")
    except Exception:
        db.rollback()
        for temp_path, _ in pending_moves:
            temp_path.unlink(missing_ok=True)
        raise
    else:
        for temp_path, final_dest in pending_moves:
            move_asset(temp_path, final_dest)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return ImageZipImportResponse(created=created, skipped=skipped)


@router.post(
    "/update",
    response_model=ImageResponse,
    summary="Update Image",
    description="""
Partially update an existing image, identified by uuid, optionally replacing its file. Requires the scientist role.

Only the fields supplied in the request are changed; omitted fields are left as-is. Sending an explicit null for filename, filepath, or dive_uuid is a no-op, but sending an explicit null for metadata, difficulty, or priority clears it.

Fails with 404 if the uuid or dive_uuid is not found, 422 if filepath is invalid or the replacement image data cannot be decoded, or 409 if the new image data would change the image's dimensions while point annotations referencing it exist, or if an image with the new filepath already exists.
""",
)
def update_image(payload: ImageUpdateRequest, request: Request, db: Session = Depends(get_db)):
    require_current_user(request)

    image = get_by_uuid(db, Image, payload.uuid.bytes)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    # Snapshot the current on-disk state before any DB mutation, so file ops
    # (deferred until after a successful commit) can reference the old location.
    old_filepath = image.filepath
    old_resolved = resolve_asset_path(old_filepath)
    old_size = (image.size_x, image.size_y)

    updates = apply_partial_update(
        payload,
        nullable_columns={"metadata_json", "difficulty", "priority"},
        field_map={
            "filename": "filename",
            "filepath": "filepath",
            "metadata": "metadata_json",
            "difficulty": "difficulty",
            "priority": "priority",
        },
    )
    if updates.get("metadata_json") is not None:
        updates["metadata_json"] = encode_metadata(updates["metadata_json"])
    for column, value in updates.items():
        setattr(image, column, value)

    if "dive_uuid" in payload.model_fields_set and payload.dive_uuid is not None:
        image.dive_id = _resolve_dive_id(db, payload.dive_uuid)

    # Determine the target (final) on-disk path. `apply_partial_update` already
    # applied `image.filepath` above when the key was present + non-null.
    filepath_changing = (
        "filepath" in payload.model_fields_set
        and payload.filepath is not None
        and payload.filepath != old_filepath
    )
    if "filepath" in payload.model_fields_set and payload.filepath is not None:
        try:
            new_resolved = resolve_asset_path(image.filepath)
        except ValueError:
            db.rollback()
            raise HTTPException(status_code=422, detail="Invalid filepath")
    else:
        new_resolved = old_resolved

    temp_path: Path | None = None
    if "image" in payload.model_fields_set and payload.image is not None:
        try:
            temp_path = write_temp_image(payload.image)
        except ValueError:
            db.rollback()
            raise HTTPException(status_code=422, detail="Invalid image data")
        try:
            new_size = read_image_dimensions(temp_path)
        except ValueError:
            temp_path.unlink(missing_ok=True)
            db.rollback()
            raise HTTPException(status_code=422, detail="Could not decode image")

        if new_size != old_size and image_has_point_annotations(db, image.id):
            # Reject before anything on disk has moved; disk stays untouched.
            temp_path.unlink(missing_ok=True)
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Cannot change image dimensions while point annotations exist",
            )
        image.size_x, image.size_y = new_size

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Image already exists")

    # DB committed. Now perform file ops: move the existing file first, then
    # swap the new blob in at the final path.
    if filepath_changing:
        move_asset(old_resolved, new_resolved)
    if temp_path is not None:
        move_asset(temp_path, new_resolved)

    db.refresh(image)
    return _to_response(image, db)


@router.post(
    "/batch/status-change/{new_status}",
    summary="Batch Change Image Status",
    description="""
Set the status of every image in the given list of uuids to new_status. Requires the scientist role.

Valid statuses are hidden, open, review_pending, finalized, and deleted.

Fails with 422 if new_status is not a recognized status, or 404 if any uuid does not resolve to an existing image (no images are updated in that case).
""",
)
def batch_status_change(
    new_status: str,
    uuids: list[UUID],
    request: Request,
    db: Session = Depends(get_db),
):
    require_current_user(request)

    status_id = IMAGE_STATUS_INT.get(new_status)
    if status_id is None:
        raise HTTPException(status_code=422, detail="Unknown image status")

    images: list[Image] = []
    for image_uuid in uuids:
        image = get_by_uuid(db, Image, image_uuid.bytes)
        if image is None:
            raise HTTPException(status_code=404, detail="Image not found")
        images.append(image)

    for image in images:
        image.status_id = status_id

    db.commit()
    return {"updated": len(images)}
