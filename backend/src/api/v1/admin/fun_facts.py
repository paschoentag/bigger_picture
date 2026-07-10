import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from src import config
from src.api.deps import require_current_user
from src.db import get_db
from src.models.admin import FunFactImportResponse
from src.services.assets import extract_zip_safely, move_asset
from src.services.fun_facts_import import FunFactImportError, run_fun_facts_import

router = APIRouter()


@router.post(
    "/import",
    response_model=FunFactImportResponse,
    summary="Import Fun Facts from Zip",
    description="""
Upload a zip in the same format as the fun facts zip export (fun_facts.csv, helper_images.csv,
helper_images/) and upsert each fun fact by uuid. Requires the admin role.

A plain CSV isn't accepted: fun facts can reference helper images that don't exist in this
database yet, and those images have to travel with the import rather than being referenced by a
uuid the importer is expected to already have uploaded separately.

helper_images.csv rows whose uuid already exists are left untouched (file included) - reimporting
the same export is safe to repeat. A new helper image uuid is created from the matching file under
helper_images/.

fun_facts.csv's created_at and created_by_uuid are accepted, for round-trip compatibility with the
export, but are ignored: a new fact is always attributed to the importing admin and stamped with
the current time, and an existing fact's created_at/created_by are never modified.

Each fun_facts.csv row fully overwrites the matching fact's title, fact, min_level, region, and
image - a blank region_uuid or image_uuid clears that field, it does not leave the existing value
unchanged.

The whole import is all-or-nothing: any invalid row aborts with nothing persisted and no asset
files left behind.

Fails with 422 identifying the offending file and row if any row is invalid, references a
nonexistent region, or has a title that collides with a different fact's title, or if the zip is
malformed, missing fun_facts.csv, or contains an unsafe path.
""",
)
def import_fun_facts_zip(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = require_current_user(request)

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
            raise FunFactImportError("<zip>", None, str(exc)) from exc

        summary, pending_moves = run_fun_facts_import(db, extract_dir, creator_id=user.id)
        db.commit()
    except FunFactImportError as exc:
        db.rollback()
        for temp_path, _ in pending_moves:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail={"file": exc.file, "row": exc.row, "reason": exc.reason})
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

    return FunFactImportResponse(created=summary.created, updated=summary.updated)
