from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from src import config
from src.api.deps import require_current_user
from src.api.v1.dataset._metadata import decode_metadata
from src.constants import (
    ANNOTATION_APPROVED,
    ANNOTATION_REVIEW_FAILED,
    ANNOTATION_REVIEW_PENDING,
    CANDIDATE_STATUS_INT,
    INT_ANNOTATION_STATUS,
    INT_CANDIDATE_STATUS,
    INT_IMAGE_STATUS,
    CandidateStatus,
    Role,
)
from src.db import get_db
from src.models.annotate import (
    CandidateAnnotationCorrectionRequest,
    CandidateAnnotationCreateRequest,
    CandidateAnnotationResponse,
    NextCandidateResponse,
    NextPairImageResponse,
)
from src.schema.candidate_annotations import CandidateAnnotation
from src.schema.candidate_pairs import CandidatePair
from src.schema.dives import Dive
from src.schema.images import Image
from src.schema.users import User
from src.services.experience import grant_exp
from src.services.image_pairs import ensure_image_pair
from src.services.lookups import get_by_uuid, resolve_sorted_image_pair
from src.services.random_pool import sample_pool
from src.util import now_ms

router = APIRouter()

CANDIDATE_OPEN = CANDIDATE_STATUS_INT[CandidateStatus.OPEN]
COUNTED_ANNOTATION_STATUSES = {ANNOTATION_REVIEW_PENDING, ANNOTATION_APPROVED}


def _to_response(annotation: CandidateAnnotation, db: Session) -> CandidateAnnotationResponse:
    candidate = db.get(CandidatePair, annotation.candidate_id)
    image_a = db.get(Image, candidate.image1_id)
    image_b = db.get(Image, candidate.image2_id)
    status_enum = INT_ANNOTATION_STATUS.get(annotation.status_id)
    creator = db.get(User, annotation.created_by)
    reviewed_by = None
    if annotation.reviewed_by is not None:
        reviewer = db.get(User, annotation.reviewed_by)
        reviewed_by = UUID(bytes=reviewer.uuid)
    return CandidateAnnotationResponse(
        uuid=UUID(bytes=annotation.uuid),
        image_a=UUID(bytes=image_a.uuid),
        image_b=UUID(bytes=image_b.uuid),
        no_overlap=annotation.no_overlap,
        expert_level=annotation.expert_level,
        status=str(status_enum) if status_enum is not None else str(annotation.status_id),
        created_at=annotation.created_at,
        created_by=UUID(bytes=creator.uuid),
        reviewed_at=annotation.reviewed_at,
        reviewed_by=reviewed_by,
    )


def _resolve_open_candidate(db: Session, image_a: UUID, image_b: UUID) -> CandidatePair:
    """Resolve the open CandidatePair for two image uuids, mapping errors to HTTP."""
    ids = resolve_sorted_image_pair(db, image_a, image_b)
    if ids is None:
        raise HTTPException(status_code=404, detail="Image not found")
    candidate = db.execute(
        select(CandidatePair).where(
            CandidatePair.image1_id == ids[0],
            CandidatePair.image2_id == ids[1],
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate pair not found")
    if candidate.status_id != CANDIDATE_OPEN:
        raise HTTPException(status_code=409, detail="Candidate not open")
    return candidate


def _build_annotation(payload: CandidateAnnotationCreateRequest, user: User, candidate: CandidatePair) -> CandidateAnnotation:
    return CandidateAnnotation(
        uuid=payload.uuid.bytes,
        created_at=now_ms(),
        created_by=user.id,
        candidate_id=candidate.id,
        no_overlap=bool(payload.no_overlap),
        expert_level=user.expert_level,
        status_id=ANNOTATION_REVIEW_PENDING,
    )


def _vote_weight(annotation: CandidateAnnotation) -> int:
    if annotation.expert_level >= config.CANDIDATE_CONSENSUS_EXPERT_LEVEL:
        return config.CANDIDATE_CONSENSUS_EXPERT_WEIGHT
    return 1


def _winning_side(counted: list[CandidateAnnotation]) -> bool | None:
    """Return the winning `no_overlap` value, or None if neither the
    expert-weighted consensus nor the raw count/agreement auto-review
    threshold is met yet.
    """
    overlap_weight = sum(_vote_weight(annotation) for annotation in counted if not annotation.no_overlap)
    no_overlap_weight = sum(_vote_weight(annotation) for annotation in counted if annotation.no_overlap)
    total_weight = overlap_weight + no_overlap_weight
    if total_weight >= config.CANDIDATE_CONSENSUS_MIN_WEIGHT:
        if overlap_weight / total_weight >= config.CANDIDATE_CONSENSUS_MIN_SHARE:
            return False
        if no_overlap_weight / total_weight >= config.CANDIDATE_CONSENSUS_MIN_SHARE:
            return True

    overlap_count = sum(1 for annotation in counted if not annotation.no_overlap)
    no_overlap_count = len(counted) - overlap_count
    if len(counted) >= config.CANDIDATE_MIN_ANNOTATIONS:
        if overlap_count / len(counted) >= config.CANDIDATE_AGREEMENT_THRESHOLD:
            return False
        if no_overlap_count / len(counted) >= config.CANDIDATE_AGREEMENT_THRESHOLD:
            return True

    return None


def _apply_auto_review(
    candidate: CandidatePair, counted: list[CandidateAnnotation], no_overlap_wins: bool, db: Session
) -> None:
    """Close `candidate` via system auto-review: flip every counted
    annotation to approved/review_failed based on agreement with the
    winning side, granting exp only to winning-side creators, then set the
    candidate's terminal status and (for has_overlap) ensure an ImagePair
    exists. There is no human reviewer in this path, so reviewed_by stays
    NULL throughout.
    """
    reviewed_at = now_ms()
    for annotation in counted:
        if annotation.no_overlap == no_overlap_wins:
            annotation.status_id = ANNOTATION_APPROVED
            grant_exp(db, db.get(User, annotation.created_by), config.CANDIDATE_ANNOTATION_REVIEW_EXP)
        else:
            annotation.status_id = ANNOTATION_REVIEW_FAILED
        annotation.reviewed_at = reviewed_at
        annotation.reviewed_by = None

    candidate.status_id = (
        CANDIDATE_STATUS_INT[CandidateStatus.NO_OVERLAP]
        if no_overlap_wins
        else CANDIDATE_STATUS_INT[CandidateStatus.HAS_OVERLAP]
    )
    candidate.reviewed_by = None
    candidate.reviewed_at = reviewed_at

    if not no_overlap_wins:
        ensure_image_pair(
            db,
            image1_id=candidate.image1_id,
            image2_id=candidate.image2_id,
            creator_id=candidate.created_by,
        )


def _recompute_candidate_consensus(candidate: CandidatePair, db: Session) -> None:
    if candidate.status_id != CANDIDATE_OPEN:
        return

    annotations = db.execute(
        select(CandidateAnnotation).where(CandidateAnnotation.candidate_id == candidate.id)
    ).scalars().all()
    counted = [annotation for annotation in annotations if annotation.status_id in COUNTED_ANNOTATION_STATUSES]
    if not counted:
        return

    no_overlap_wins = _winning_side(counted)
    if no_overlap_wins is None:
        return

    _apply_auto_review(candidate, counted, no_overlap_wins, db)


@router.post(
    "/create",
    response_model=CandidateAnnotationResponse,
    status_code=201,
    summary="Create Candidate Pair Annotation",
    description="""
Create a new candidate pair annotation, identified by uuid, for an open candidate pair. Requires the annotator role (or any higher role).

expert_level is copied from the caller at creation time.

Fails with 404 if either image or the candidate pair does not exist, 409 if the candidate pair is not open, or 409 if the uuid is already used by an existing annotation.
""",
)
def create_annotation(
    payload: CandidateAnnotationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_current_user(request)
    candidate = _resolve_open_candidate(db, payload.image_a, payload.image_b)
    annotation = _build_annotation(payload, user, candidate)
    db.add(annotation)
    try:
        db.flush()
        _recompute_candidate_consensus(candidate, db)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Annotation already exists")
    db.refresh(annotation)
    return _to_response(annotation, db)


@router.post(
    "/batch/create",
    summary="Batch Create Candidate Pair Annotations",
    description="""
Create multiple candidate pair annotations in one request, one per item, using the same rules as Create Candidate Pair Annotation. Requires the annotator role (or any higher role).

The batch is all-or-nothing: if any item fails validation, or any uuid collides with an existing annotation, none of the items are created.

Fails with 404 if any item's images or candidate pair do not exist, 409 if any item's candidate pair is not open, or 409 if any item's uuid is already used by an existing annotation.
""",
)
def batch_create_annotations(
    items: list[CandidateAnnotationCreateRequest],
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_current_user(request)

    annotations: list[CandidateAnnotation] = []
    for item in items:
        candidate = _resolve_open_candidate(db, item.image_a, item.image_b)
        annotation = _build_annotation(item, user, candidate)
        db.add(annotation)
        annotations.append(annotation)

    try:
        db.flush()
        for annotation in annotations:
            candidate = db.get(CandidatePair, annotation.candidate_id)
            _recompute_candidate_consensus(candidate, db)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Annotation already exists")
    return {"created": len(annotations)}


@router.post(
    "/correction",
    response_model=CandidateAnnotationResponse,
    summary="Correct a Candidate Pair Annotation",
    description="""
Replace the no_overlap value of an existing candidate pair annotation. Can only be done by the user who created the annotation, within the first hour of creating it, and as long as it is in status "review_pending".

Unlike point annotation correction, no_overlap is always required and always overwritten; there is no partial-update behavior.

Fails with 404 if the annotation does not exist, 403 if the caller is not its creator, 409 if it is not pending review, or 403 if the correction window has expired.
""",
)
def correct_annotation(
    payload: CandidateAnnotationCorrectionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_current_user(request)

    annotation = db.execute(
        select(CandidateAnnotation).where(CandidateAnnotation.uuid == payload.uuid.bytes)
    ).scalar_one_or_none()
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")

    if annotation.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not the annotation creator")
    if annotation.status_id != ANNOTATION_REVIEW_PENDING:
        raise HTTPException(status_code=409, detail="Annotation is not pending review")
    if now_ms() - annotation.created_at >= config.SELF_CORRECTION_TIME_LIMIT_MS:
        raise HTTPException(status_code=403, detail="Correction window expired")

    annotation.no_overlap = bool(payload.no_overlap)
    candidate = db.get(CandidatePair, annotation.candidate_id)
    _recompute_candidate_consensus(candidate, db)
    db.commit()
    db.refresh(annotation)
    return _to_response(annotation, db)


def _load_pending_for_review(db: Session, annotation_uuid: UUID) -> CandidateAnnotation:
    annotation = db.execute(
        select(CandidateAnnotation).where(CandidateAnnotation.uuid == annotation_uuid.bytes)
    ).scalar_one_or_none()
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    if annotation.status_id != ANNOTATION_REVIEW_PENDING:
        raise HTTPException(status_code=409, detail="Annotation is not pending review")
    return annotation


def _authorize_review(caller: User, annotation: CandidateAnnotation) -> None:
    allowed = (caller.id != annotation.created_by) and (
        (caller.expert_level >= config.MIN_REVIEW_EXPERT_LEVEL and caller.expert_level > annotation.expert_level)
        or caller.role in (Role.SCIENTIST, Role.ADMIN)
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Not authorized to review this annotation")


def _apply_review(annotation: CandidateAnnotation, caller: User, status_id: int, db: Session) -> CandidateAnnotationResponse:
    annotation.status_id = status_id
    annotation.reviewed_by = caller.id
    annotation.reviewed_at = now_ms()
    grant_exp(db, db.get(User, caller.id), config.CANDIDATE_ANNOTATION_REVIEW_EXP)
    if status_id == ANNOTATION_APPROVED:
        creator = db.get(User, annotation.created_by)
        grant_exp(db, creator, config.CANDIDATE_ANNOTATION_REVIEW_EXP)
    candidate = db.get(CandidatePair, annotation.candidate_id)
    _recompute_candidate_consensus(candidate, db)
    db.commit()
    db.refresh(annotation)
    return _to_response(annotation, db)


@router.get(
    "/review/next/{dive_uuid}",
    response_model=list[CandidateAnnotationResponse],
    summary="Get Next Candidate Pair Annotations to Review",
    description="""
Return up to n candidate pair annotations from the given dive that are pending review and were not created by the caller. Requires the annotator role (or any higher role).

The caller must either hold the scientist or admin role, or have an expert_level that meets the configured minimum and is strictly greater than an annotation's expert_level for that annotation to be eligible; callers who satisfy neither condition always get an empty list. Unlike point annotation pairs, candidate pairs have no priority to sort by. Up to n items are randomly selected from a pool of up to max(n, NEXT_ITEM_POOL_SIZE) eligible annotations, prioritized by creation time ascending; the returned order is random. n defaults to 1 and must be at least 1; there is no upper bound.

Fails with 404 if the dive does not exist, or 422 if n is less than 1.
""",
)
@router.get(
    "/review/next/{dive_uuid}/{n}",
    response_model=list[CandidateAnnotationResponse],
    summary="Get Next Candidate Pair Annotations to Review",
    description="""
Return up to n candidate pair annotations from the given dive that are pending review and were not created by the caller. Requires the annotator role (or any higher role).

The caller must either hold the scientist or admin role, or have an expert_level that meets the configured minimum and is strictly greater than an annotation's expert_level for that annotation to be eligible; callers who satisfy neither condition always get an empty list. Unlike point annotation pairs, candidate pairs have no priority to sort by. Up to n items are randomly selected from a pool of up to max(n, NEXT_ITEM_POOL_SIZE) eligible annotations, prioritized by creation time ascending; the returned order is random. n defaults to 1 and must be at least 1; there is no upper bound.

Fails with 404 if the dive does not exist, or 422 if n is less than 1.
""",
)
def get_next_review_candidates(
    dive_uuid: UUID, request: Request, n: int = 1, db: Session = Depends(get_db)
):
    user = require_current_user(request)
    if n < 1:
        raise HTTPException(status_code=422, detail="n must be >= 1")

    dive = get_by_uuid(db, Dive, dive_uuid.bytes)
    if dive is None:
        raise HTTPException(status_code=404, detail="Dive not found")

    is_privileged = user.role in (Role.SCIENTIST, Role.ADMIN)
    if not is_privileged and user.expert_level < config.MIN_REVIEW_EXPERT_LEVEL:
        return []

    Image1 = aliased(Image)
    Image2 = aliased(Image)

    conditions = [
        CandidateAnnotation.status_id == ANNOTATION_REVIEW_PENDING,
        CandidateAnnotation.created_by != user.id,
        Image1.dive_id == dive.id,
        Image2.dive_id == dive.id,
    ]
    if not is_privileged:
        conditions.append(CandidateAnnotation.expert_level < user.expert_level)

    stmt = (
        select(CandidateAnnotation)
        .join(CandidatePair, CandidateAnnotation.candidate_id == CandidatePair.id)
        .join(Image1, CandidatePair.image1_id == Image1.id)
        .join(Image2, CandidatePair.image2_id == Image2.id)
        .where(*conditions)
        .order_by(CandidateAnnotation.created_at.asc())
    )
    annotations = sample_pool(db, stmt, n)
    return [_to_response(annotation, db) for annotation in annotations]


@router.post(
    "/review/{annotation_uuid}/fail",
    response_model=CandidateAnnotationResponse,
    summary="Fail Candidate Pair Annotation Review",
    description="""
Mark a pending candidate pair annotation as review_failed. Requires the annotator role (or any higher role); the caller cannot review their own annotation.

The caller must either hold the scientist or admin role, or have an expert_level that meets the configured minimum and is strictly greater than the annotation's expert_level.

Fails with 404 if the annotation does not exist, 409 if it is not pending review, or 403 if the caller is not authorized to review it.
""",
)
def review_fail(annotation_uuid: UUID, request: Request, db: Session = Depends(get_db)):
    caller = require_current_user(request)
    annotation = _load_pending_for_review(db, annotation_uuid)
    _authorize_review(caller, annotation)
    return _apply_review(annotation, caller, ANNOTATION_REVIEW_FAILED, db)


@router.post(
    "/review/{annotation_uuid}/approve",
    response_model=CandidateAnnotationResponse,
    summary="Approve Candidate Pair Annotation Review",
    description="""
Mark a pending candidate pair annotation as approved. Requires the annotator role (or any higher role); the caller cannot review their own annotation.

The caller must either hold the scientist or admin role, or have an expert_level that meets the configured minimum and is strictly greater than the annotation's expert_level.

Fails with 404 if the annotation does not exist, 409 if it is not pending review, or 403 if the caller is not authorized to review it.
""",
)
def review_approve(annotation_uuid: UUID, request: Request, db: Session = Depends(get_db)):
    caller = require_current_user(request)
    annotation = _load_pending_for_review(db, annotation_uuid)
    _authorize_review(caller, annotation)
    return _apply_review(annotation, caller, ANNOTATION_APPROVED, db)


def _to_next_image_response(image: Image, db: Session) -> NextPairImageResponse:
    dive = db.get(Dive, image.dive_id)
    status_enum = INT_IMAGE_STATUS.get(image.status_id)
    return NextPairImageResponse(
        uuid=UUID(bytes=image.uuid),
        filename=image.filename,
        filepath=image.filepath,
        dive_id=UUID(bytes=dive.uuid),
        status=str(status_enum) if status_enum is not None else None,
        size_x=image.size_x,
        size_y=image.size_y,
        metadata=decode_metadata(image.metadata_json),
    )


def _to_next_candidate_response(candidate: CandidatePair, db: Session) -> NextCandidateResponse:
    image1 = db.get(Image, candidate.image1_id)
    image2 = db.get(Image, candidate.image2_id)
    status_enum = INT_CANDIDATE_STATUS.get(candidate.status_id)
    return NextCandidateResponse(
        image1=_to_next_image_response(image1, db),
        image2=_to_next_image_response(image2, db),
        status=str(status_enum) if status_enum is not None else None,
    )


@router.get(
    "/next/{dive_uuid}",
    response_model=list[NextCandidateResponse],
    summary="Get Next Candidate Pairs",
    description="""
Return up to n open candidate pairs from the given dive that the caller has not yet annotated. Requires the annotator role (or any higher role).

Unlike point annotation pairs, candidate pairs have no difficulty or priority gating. Up to n items are randomly selected from a pool of up to max(n, NEXT_ITEM_POOL_SIZE) eligible candidates, prioritized by creation time ascending; the returned order is random. n defaults to 1 and must be at least 1; there is no upper bound.

Fails with 404 if the dive does not exist, or 422 if n is less than 1.
""",
)
@router.get(
    "/next/{dive_uuid}/{n}",
    response_model=list[NextCandidateResponse],
    summary="Get Next Candidate Pairs",
    description="""
Return up to n open candidate pairs from the given dive that the caller has not yet annotated. Requires the annotator role (or any higher role).

Unlike point annotation pairs, candidate pairs have no difficulty or priority gating. Up to n items are randomly selected from a pool of up to max(n, NEXT_ITEM_POOL_SIZE) eligible candidates, prioritized by creation time ascending; the returned order is random. n defaults to 1 and must be at least 1; there is no upper bound.

Fails with 404 if the dive does not exist, or 422 if n is less than 1.
""",
)
def get_next_candidates(dive_uuid: UUID, request: Request, n: int = 1, db: Session = Depends(get_db)):
    user = require_current_user(request)
    if n < 1:
        raise HTTPException(status_code=422, detail="n must be >= 1")

    dive = get_by_uuid(db, Dive, dive_uuid.bytes)
    if dive is None:
        raise HTTPException(status_code=404, detail="Dive not found")

    Image1 = aliased(Image)
    Image2 = aliased(Image)
    annotated_candidate_ids = select(CandidateAnnotation.candidate_id).where(
        CandidateAnnotation.created_by == user.id
    )

    stmt = (
        select(CandidatePair)
        .join(Image1, CandidatePair.image1_id == Image1.id)
        .join(Image2, CandidatePair.image2_id == Image2.id)
        .where(
            CandidatePair.status_id == CANDIDATE_OPEN,
            Image1.dive_id == dive.id,
            Image2.dive_id == dive.id,
            CandidatePair.id.notin_(annotated_candidate_ids),
        )
        .order_by(CandidatePair.id.asc())
    )
    candidates = sample_pool(db, stmt, n)
    return [_to_next_candidate_response(candidate, db) for candidate in candidates]
