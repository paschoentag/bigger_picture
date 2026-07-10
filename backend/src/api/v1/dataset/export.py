import io
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import get_db
from src.schema.dives import Dive
from src.services.dataset_export import (
    build_dive_zip,
    build_full_dataset_zip,
    build_fun_facts_zip,
    write_candidate_annotation_flat_csv,
    write_fun_facts_csv,
    write_point_annotation_flat_csv,
)

router = APIRouter()


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _csv_response(csv_text: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _resolve_dive_ids(db: Session, dive: list[UUID] | None) -> list[int] | None:
    """Resolve requested dive uuids to their integer ids. 404s if any is unknown."""
    if not dive:
        return None
    dive_rows = db.execute(select(Dive).where(Dive.uuid.in_([d.bytes for d in dive]))).scalars().all()
    if len(dive_rows) != len(set(dive)):
        raise HTTPException(status_code=404, detail="Dive not found")
    return [row.id for row in dive_rows]


def _zip_response(background_tasks: BackgroundTasks, build_fn, filename: str) -> FileResponse:
    tmp_dir = tempfile.mkdtemp(prefix="dataset_export_")
    zip_path = Path(tmp_dir) / "export.zip"
    try:
        build_fn(zip_path)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    background_tasks.add_task(shutil.rmtree, tmp_dir, ignore_errors=True)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=filename,
        background=background_tasks,
    )


@router.get(
    "/full",
    summary="Export Full Dataset as Zip",
    description="""
Export every content table (users, labels, cameras, regions, dives, images, image pairs,
candidate pairs, point annotations, candidate annotations, fun facts, helper images, seen facts,
quest claims) as CSV, with every internal id dropped and every foreign key resolved to the
referenced row's uuid, packaged into a zip alongside images/ and helper_images/ folders
containing the actual asset files. Requires the scientist role.

Image pairs and candidate pairs have no uuid of their own - they are identified purely by the
uuids of their two constituent images, both in their own CSV and in any other table's reference
to them, so datasets from separate deployments can merge without pair-identity conflicts.
""",
)
def export_full_dataset_zip(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _zip_response(
        background_tasks,
        lambda zip_path: build_full_dataset_zip(db, zip_path),
        f"dataset_export_full_{_timestamp()}.zip",
    )


@router.get(
    "/full-csv-only",
    summary="Export Full Dataset as Zip, CSVs Only",
    description="""
Same as /full, but without the images/ and helper_images/ asset folders - just the CSVs. Use this
for large datasets where the asset files would make the full export impractically large (potentially
hundreds of GB); this endpoint's output is typically a few MB regardless of dataset size. Requires
the scientist role.
""",
)
def export_full_dataset_csv_only_zip(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _zip_response(
        background_tasks,
        lambda zip_path: build_full_dataset_zip(db, zip_path, include_images=False),
        f"dataset_export_full_csv_only_{_timestamp()}.zip",
    )


@router.get(
    "/points-flat",
    summary="Export Point Annotations Flat View as CSV",
    description="""
Export the `view_point_annotation_flat` SQL view as CSV (one row per point annotation, joined to
its pair/images/dive/label context, with usernames and status titles already resolved), minus its
leaked internal id columns. Requires the scientist role.

Use repeated `dive` query parameters to limit the export to one or more dives. If omitted, exports
across all dives.
""",
)
def export_points_flat_csv(
    dive: list[UUID] | None = Query(default=None, description="Optional repeated dive UUIDs to filter export."),
    db: Session = Depends(get_db),
):
    dive_ids = _resolve_dive_ids(db, dive)
    buffer = io.StringIO()
    write_point_annotation_flat_csv(db, buffer, dive_ids=dive_ids)
    buffer.seek(0)
    return _csv_response(buffer.getvalue(), f"point_annotations_flat_{_timestamp()}.csv")


@router.get(
    "/candidates-flat",
    summary="Export Candidate Annotations Flat View as CSV",
    description="""
Export the `view_candidate_annotation_flat` SQL view as CSV (one row per candidate vote, joined to
its candidate pair/images/dive context, with usernames and status titles already resolved), minus
its leaked internal id columns. Requires the scientist role.

Use repeated `dive` query parameters to limit the export to one or more dives. If omitted, exports
across all dives.
""",
)
def export_candidates_flat_csv(
    dive: list[UUID] | None = Query(default=None, description="Optional repeated dive UUIDs to filter export."),
    db: Session = Depends(get_db),
):
    dive_ids = _resolve_dive_ids(db, dive)
    buffer = io.StringIO()
    write_candidate_annotation_flat_csv(db, buffer, dive_ids=dive_ids)
    buffer.seek(0)
    return _csv_response(buffer.getvalue(), f"candidate_annotations_flat_{_timestamp()}.csv")


@router.get(
    "/fun-facts",
    summary="Export Fun Facts as CSV",
    description="""
Export every fun fact as CSV only (no images), with internal ids dropped and region/image foreign
keys resolved to uuids. Requires the scientist role.
""",
)
def export_fun_facts_csv(db: Session = Depends(get_db)):
    buffer = io.StringIO()
    write_fun_facts_csv(db, buffer)
    buffer.seek(0)
    return _csv_response(buffer.getvalue(), f"fun_facts_{_timestamp()}.csv")


@router.get(
    "/fun-facts-zip",
    summary="Export Fun Facts With Helper Images as Zip",
    description="""
Export every fun fact as CSV plus a helper_images/ folder (and matching helper_images.csv)
containing only the helper images actually referenced by an exported fun fact - not every helper
image in the system. Requires the scientist role.
""",
)
def export_fun_facts_zip(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _zip_response(
        background_tasks,
        lambda zip_path: build_fun_facts_zip(db, zip_path),
        f"fun_facts_{_timestamp()}.zip",
    )


@router.get(
    "/dive",
    summary="Export One Dive as Zip",
    description="""
Export a single dive as a zip containing points.csv and candidates.csv (the same flat-view CSVs as
/points-flat and /candidates-flat, filtered to this dive) plus an images/ folder with every image
belonging to the dive, regardless of whether it appears in any pair or annotation. Requires the
scientist role.

Fails with 404 if the dive does not exist.
""",
)
def export_dive_zip(dive: UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    dive_row = db.execute(select(Dive).where(Dive.uuid == dive.bytes)).scalar_one_or_none()
    if dive_row is None:
        raise HTTPException(status_code=404, detail="Dive not found")
    return _zip_response(
        background_tasks,
        lambda zip_path: build_dive_zip(db, dive_row.id, zip_path),
        f"dive_export_{dive}_{_timestamp()}.zip",
    )
