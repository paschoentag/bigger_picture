import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from src import config
from src.api.deps import require_current_user
from src.db import get_db
from src.models.dataset import DatasetImportCounts, DatasetImportResponse
from src.services.assets import extract_zip_safely, move_asset
from src.services.dataset_import import DatasetImportError, run_import

router = APIRouter()


@router.post(
    "/zip-upload",
    response_model=DatasetImportResponse,
    status_code=201,
    summary="Bulk Import Dataset From Zip",
    description="""
Upload a zip archive containing up to 9 optional, semicolon-delimited CSVs (labels.csv, cameras.csv, regions.csv, dives.csv, images.csv, candidates.csv, pairs.csv, helper_images.csv, fun_facts.csv) plus images/ and helper_images/ folders, and import them in dependency order. Requires the scientist role.

The whole import is all-or-nothing: any error aborts with nothing persisted and no asset files left behind. On success, returns per-entity created counts - newly minted uuids (from rows using uuid "new") are never echoed back, so reference such rows by title in later rows of the same import.

Fails with 422 identifying the offending file and row if any CSV row is invalid, references a nonexistent entity, or if the zip is malformed or contains an unsafe path.
""",
)
def zip_upload(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
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
            raise DatasetImportError("<zip>", None, str(exc)) from exc

        summary, pending_moves = run_import(db, extract_dir, user.id)
        db.commit()
    except DatasetImportError as exc:
        db.rollback()
        for temp_path, _ in pending_moves:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail={"file": exc.file, "row": exc.row, "reason": exc.reason},
        )
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

    return DatasetImportResponse(
        created=DatasetImportCounts(
            labels=summary.labels,
            cameras=summary.cameras,
            regions=summary.regions,
            dives=summary.dives,
            images=summary.images,
            candidate_pairs=summary.candidate_pairs,
            image_pairs=summary.image_pairs,
            helper_images=summary.helper_images,
            fun_facts=summary.fun_facts,
        )
    )
