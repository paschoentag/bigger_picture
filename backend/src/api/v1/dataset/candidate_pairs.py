from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from src.api.deps import require_current_user
from src.constants import (
    CANDIDATE_STATUS_INT,
    INT_CANDIDATE_STATUS,
    CandidateStatus,
)
from src.db import get_db
from src.models.dataset import (
    CandidatePairListResponse,
    CandidatePairResponse,
    DivePublishRequest,
    ImagePairRef,
    PublishCandidatesResponse,
    StrideCandidatePairRequest,
    StrideCandidatePairResponse,
)
from src.schema.candidate_pairs import CandidatePair
from src.schema.dives import Dive
from src.schema.images import Image
from src.schema.users import User
from src.services.candidate_pairs import create_candidate_pair as _create_candidate_pair_row
from src.services.candidate_pairs import ensure_candidate_pair
from src.services.errors import ConflictError, SameDiveError
from src.services.image_pairs import ensure_image_pair
from src.services.images import resolve_dive_id as _resolve_dive_id_or_none
from src.services.lookups import get_by_uuid, resolve_sorted_image_pair

router = APIRouter()

PUBLISH_BATCH_SIZE = 100


def _to_response(pair: CandidatePair, db: Session) -> CandidatePairResponse:
    image_a = db.get(Image, pair.image1_id)
    image_b = db.get(Image, pair.image2_id)
    creator = db.get(User, pair.created_by)
    status = None
    if pair.status_id is not None:
        status_enum = INT_CANDIDATE_STATUS.get(pair.status_id)
        status = str(status_enum) if status_enum is not None else None
    return CandidatePairResponse(
        created_at=pair.created_at,
        created_by=UUID(bytes=creator.uuid),
        image_a=UUID(bytes=image_a.uuid),
        image_b=UUID(bytes=image_b.uuid),
        image_a_filename=image_a.filename,
        image_b_filename=image_b.filename,
        status=status,
    )


def _resolve_pair_ids(db: Session, image_a: UUID, image_b: UUID) -> tuple[int, int]:
    """Resolve two image uuids to sorted ids, mapping errors to HTTP responses."""
    ids = resolve_sorted_image_pair(db, image_a, image_b)
    if ids is None:
        raise HTTPException(status_code=404, detail="Image not found")
    if ids[0] == ids[1]:
        raise HTTPException(status_code=422, detail="image_a and image_b must differ")
    return ids


def _resolve_dive_id(db: Session, dive_uuid: UUID) -> int:
    dive_id = _resolve_dive_id_or_none(db, dive_uuid)
    if dive_id is None:
        raise HTTPException(status_code=404, detail="Dive not found")
    return dive_id


def _dive_candidates_query(dive_id: int):
    """Select CandidatePair rows whose images both belong to dive_id."""
    Image1 = aliased(Image)
    Image2 = aliased(Image)
    return (
        select(CandidatePair)
        .join(Image1, CandidatePair.image1_id == Image1.id)
        .join(Image2, CandidatePair.image2_id == Image2.id)
        .where(Image1.dive_id == dive_id, Image2.dive_id == dive_id)
    )


@router.get(
    "",
    response_model=CandidatePairListResponse,
    summary="List Candidate Pairs In Dive",
    description="""
Return a page of the candidate pairs whose images both belong to the given dive, ordered by creation time. Requires the scientist role.

Fails with 404 if the dive does not exist.
""",
)
def list_candidate_pairs(
    dive: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    dive_row = get_by_uuid(db, Dive, dive.bytes)
    if dive_row is None:
        raise HTTPException(status_code=404, detail="Dive not found")

    base_query = _dive_candidates_query(dive_row.id)
    total = db.execute(select(func.count()).select_from(base_query.subquery())).scalar_one()
    hidden_count = db.execute(
        select(func.count()).select_from(
            base_query.where(
                CandidatePair.status_id == CANDIDATE_STATUS_INT[CandidateStatus.HIDDEN]
            ).subquery()
        )
    ).scalar_one()
    pairs = db.execute(
        base_query.order_by(CandidatePair.created_at).limit(page_size).offset((page - 1) * page_size)
    ).scalars().all()
    return CandidatePairListResponse(
        candidates=[_to_response(pair, db) for pair in pairs], total=total, hidden_count=hidden_count
    )


@router.post(
    "/create",
    response_model=CandidatePairResponse,
    status_code=201,
    summary="Create Candidate Pair",
    description="""
Create a new candidate pair from two existing images, to be reviewed for overlap. Requires the scientist role. The order of image_a and image_b does not matter and the backend ensures bidirectional uniqueness.

The pair is always created with status "hidden".

Fails with 404 if either image does not exist, 422 if image_a and image_b are the same image or belong to different dives, or 409 if a candidate pair for this image combination already exists.
""",
)
def create_candidate_pair(
    payload: ImagePairRef, request: Request, db: Session = Depends(get_db)
):
    user = require_current_user(request)
    ids = _resolve_pair_ids(db, payload.image_a, payload.image_b)

    try:
        pair = _create_candidate_pair_row(
            db,
            image1_id=ids[0],
            image2_id=ids[1],
            status_id=CANDIDATE_STATUS_INT[CandidateStatus.HIDDEN],
            creator_id=user.id,
        )
    except SameDiveError:
        db.rollback()
        raise HTTPException(status_code=422, detail="Images must belong to the same dive")
    except ConflictError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Candidate pair already exists")
    db.commit()
    db.refresh(pair)
    return _to_response(pair, db)


@router.post(
    "/create-stride",
    response_model=StrideCandidatePairResponse,
    status_code=201,
    summary="Create Candidate Pairs By Stride",
    description="""
Create candidate pairs across all images in a dive using a sliding stride: images are sorted by sort_by (filename or filepath, ascending), and each image at position i is paired with the image at position i+stride, for every valid i. Existing candidate pairs are left unchanged (create-or-ignore). Requires the scientist role.

The pairs are always created with status "hidden".

Fails with 404 if the dive does not exist, or 422 if stride is not a positive integer.
""",
)
def create_candidate_pairs_by_stride(
    payload: StrideCandidatePairRequest, request: Request, db: Session = Depends(get_db)
):
    user = require_current_user(request)
    dive_id = _resolve_dive_id(db, payload.dive_uuid)

    sort_column = Image.filename if payload.sort_by == "filename" else Image.filepath
    images = db.execute(
        select(Image).where(Image.dive_id == dive_id).order_by(sort_column, Image.id)
    ).scalars().all()

    pairs_considered = 0
    pairs_created = 0
    for i in range(len(images) - payload.stride):
        image1_id, image2_id = sorted((images[i].id, images[i + payload.stride].id))
        pairs_considered += 1
        if ensure_candidate_pair(
            db,
            image1_id=image1_id,
            image2_id=image2_id,
            creator_id=user.id,
            status_id=CANDIDATE_STATUS_INT[CandidateStatus.HIDDEN],
        ):
            pairs_created += 1

    db.commit()
    return StrideCandidatePairResponse(
        total_images=len(images),
        pairs_considered=pairs_considered,
        pairs_created=pairs_created,
        pairs_skipped=pairs_considered - pairs_created,
    )


@router.post(
    "/publish",
    response_model=PublishCandidatesResponse,
    summary="Publish Hidden Candidate Pairs",
    description="""
Move up to 100 hidden candidate pairs in the given dive to status "open", oldest first. Requires the scientist role. Safe to call repeatedly to publish further batches.

Fails with 404 if the dive does not exist.
""",
)
def publish_candidate_pairs(
    payload: DivePublishRequest, request: Request, db: Session = Depends(get_db)
):
    require_current_user(request)
    dive_id = _resolve_dive_id(db, payload.dive_uuid)

    hidden_query = _dive_candidates_query(dive_id).where(
        CandidatePair.status_id == CANDIDATE_STATUS_INT[CandidateStatus.HIDDEN]
    )
    pairs = db.execute(
        hidden_query.order_by(CandidatePair.created_at).limit(PUBLISH_BATCH_SIZE)
    ).scalars().all()

    for pair in pairs:
        pair.status_id = CANDIDATE_STATUS_INT[CandidateStatus.OPEN]

    db.commit()

    remaining_hidden = db.execute(
        select(func.count()).select_from(hidden_query.subquery())
    ).scalar_one()

    return PublishCandidatesResponse(published=len(pairs), remaining_hidden=remaining_hidden)


@router.post(
    "/batch/status-change/{new_status}",
    summary="Batch Change Candidate Pair Status",
    description="""
Set the status of the given candidate pairs, each referenced by its image_a/image_b uuids, to new_status. Requires the scientist role.

Valid statuses are hidden, open, no_overlap, has_overlap, and deleted. Transitioning a pair to has_overlap also creates a corresponding image pair, with status "hidden", for the same image combination, unless one already exists.

Fails with 422 if new_status is not a recognized status, 404 if any item's images or candidate pair cannot be found, or 422 if any item's image_a and image_b are the same image.
""",
)
def batch_status_change(
    new_status: str,
    items: list[ImagePairRef],
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_current_user(request)

    status_id = CANDIDATE_STATUS_INT.get(new_status)
    if status_id is None:
        raise HTTPException(status_code=422, detail="Unknown candidate status")

    # Resolve every item to its existing CandidatePair row before mutating.
    pairs: list[CandidatePair] = []
    for item in items:
        ids = _resolve_pair_ids(db, item.image_a, item.image_b)
        pair = db.execute(
            select(CandidatePair).where(
                CandidatePair.image1_id == ids[0],
                CandidatePair.image2_id == ids[1],
            )
        ).scalar_one_or_none()
        if pair is None:
            raise HTTPException(status_code=404, detail="Candidate pair not found")
        pairs.append(pair)

    for pair in pairs:
        pair.status_id = status_id

    created_image_pairs = 0
    if status_id == CANDIDATE_STATUS_INT[CandidateStatus.HAS_OVERLAP]:
        for pair in pairs:
            if ensure_image_pair(
                db, image1_id=pair.image1_id, image2_id=pair.image2_id, creator_id=user.id
            ):
                created_image_pairs += 1

    db.commit()
    return {"updated": len(pairs), "image_pairs_created": created_image_pairs}
