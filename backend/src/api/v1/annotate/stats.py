from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from src import config
from src.api.deps import require_current_user
from src.constants import (
    ANNOTATION_APPROVED,
    ANNOTATION_DELETED,
    ANNOTATION_REVIEW_FAILED,
    ANNOTATION_REVIEW_PENDING,
    CANDIDATE_STATUS_INT,
    CandidateStatus,
)
from src.db import get_db
from src.models.annotate import (
    AccuracyStat,
    AnnotateStats,
    MyStatsResponse,
    OverlapStats,
    VerifyStats,
)
from src.schema.candidate_annotations import CandidateAnnotation
from src.schema.candidate_pairs import CandidatePair
from src.schema.point_annotations import PointAnnotation

router = APIRouter()

REVIEWED_STATUSES = (ANNOTATION_APPROVED, ANNOTATION_REVIEW_FAILED)
CANDIDATE_HAS_OVERLAP = CANDIDATE_STATUS_INT[CandidateStatus.HAS_OVERLAP]


def _accuracy_stat(db: Session, model, user_id: int, window: int | None = None) -> AccuracyStat:
    """Approved/reviewed accuracy over a user's (optionally most-recent `window`) annotations.

    `window` limits to the user's newest `window` non-deleted annotations by
    creation time; `None` covers all of them. Accuracy counts only reviewed
    annotations (approved or review_failed), so unreviewed items never count
    against the player.
    """
    approved = func.coalesce(func.sum(case((model.status_id == ANNOTATION_APPROVED, 1), else_=0)), 0)
    reviewed = func.coalesce(func.sum(case((model.status_id.in_(REVIEWED_STATUSES), 1), else_=0)), 0)

    if window is None:
        stmt = select(approved, reviewed).where(
            model.created_by == user_id,
            model.status_id != ANNOTATION_DELETED,
        )
    else:
        recent = (
            select(model.status_id.label("status_id"))
            .where(model.created_by == user_id, model.status_id != ANNOTATION_DELETED)
            .order_by(model.created_at.desc())
            .limit(window)
            .subquery()
        )
        approved = func.coalesce(func.sum(case((recent.c.status_id == ANNOTATION_APPROVED, 1), else_=0)), 0)
        reviewed = func.coalesce(func.sum(case((recent.c.status_id.in_(REVIEWED_STATUSES), 1), else_=0)), 0)
        stmt = select(approved, reviewed)

    approved_count, reviewed_count = db.execute(stmt).one()
    accuracy = (approved_count / reviewed_count) if reviewed_count else None
    return AccuracyStat(correct=approved_count, reviewed=reviewed_count, accuracy=accuracy)


def _overlap_stats(db: Session, user_id: int, window: int) -> OverlapStats:
    active = (
        CandidateAnnotation.created_by == user_id,
        CandidateAnnotation.status_id != ANNOTATION_DELETED,
    )
    pairs_marked = db.execute(
        select(func.count()).select_from(CandidateAnnotation).where(*active)
    ).scalar_one()
    overlaps_found = db.execute(
        select(func.count())
        .select_from(CandidateAnnotation)
        .where(*active, CandidateAnnotation.no_overlap.is_(False))
    ).scalar_one()
    overall_pairs_with_overlap = db.execute(
        select(func.count())
        .select_from(CandidatePair)
        .where(CandidatePair.status_id == CANDIDATE_HAS_OVERLAP)
    ).scalar_one()
    return OverlapStats(
        pairs_marked=pairs_marked,
        overlaps_found=overlaps_found,
        overall_pairs_with_overlap=overall_pairs_with_overlap,
        accuracy_all_time=_accuracy_stat(db, CandidateAnnotation, user_id),
        accuracy_window=_accuracy_stat(db, CandidateAnnotation, user_id, window),
    )


def _annotate_stats(db: Session, user_id: int, window: int) -> AnnotateStats:
    active = (
        PointAnnotation.created_by == user_id,
        PointAnnotation.status_id != ANNOTATION_DELETED,
    )
    annotations = db.execute(
        select(func.count()).select_from(PointAnnotation).where(*active)
    ).scalar_one()
    annotations_verified = db.execute(
        select(func.count())
        .select_from(PointAnnotation)
        .where(*active, PointAnnotation.status_id == ANNOTATION_APPROVED)
    ).scalar_one()
    pairs_marked = db.execute(
        select(func.count(func.distinct(PointAnnotation.pair_id))).where(*active)
    ).scalar_one()
    pairs_verified = db.execute(
        select(func.count(func.distinct(PointAnnotation.pair_id))).where(
            *active, PointAnnotation.status_id == ANNOTATION_APPROVED
        )
    ).scalar_one()
    return AnnotateStats(
        annotations=annotations,
        annotations_verified=annotations_verified,
        pairs_marked=pairs_marked,
        pairs_verified=pairs_verified,
        accuracy_all_time=_accuracy_stat(db, PointAnnotation, user_id),
        accuracy_window=_accuracy_stat(db, PointAnnotation, user_id, window),
    )


def _unconfirmed_exp(db: Session, user_id: int) -> int:
    """Experience the user will earn once their pending submissions are approved.

    Reviewing others' work grants exp immediately (already in `user.exp`); the
    creator's reward is only granted when their annotation is approved, so every
    still-pending annotation represents exp that has not yet been confirmed.
    """
    pending_points = db.execute(
        select(func.count())
        .select_from(PointAnnotation)
        .where(PointAnnotation.created_by == user_id, PointAnnotation.status_id == ANNOTATION_REVIEW_PENDING)
    ).scalar_one()
    pending_candidates = db.execute(
        select(func.count())
        .select_from(CandidateAnnotation)
        .where(CandidateAnnotation.created_by == user_id, CandidateAnnotation.status_id == ANNOTATION_REVIEW_PENDING)
    ).scalar_one()
    return (
        pending_points * config.POINT_ANNOTATION_REVIEW_EXP
        + pending_candidates * config.CANDIDATE_ANNOTATION_REVIEW_EXP
    )


def _verify_stats(db: Session, user_id: int) -> VerifyStats:
    """Counts of reviews the user performed across overlap and point annotations."""
    verified = accepted = faulty_found = 0
    for model in (CandidateAnnotation, PointAnnotation):
        row = db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((model.status_id == ANNOTATION_APPROVED, 1), else_=0)), 0),
                func.coalesce(func.sum(case((model.status_id == ANNOTATION_REVIEW_FAILED, 1), else_=0)), 0),
            )
            .select_from(model)
            .where(model.reviewed_by == user_id)
        ).one()
        verified += row[0]
        accepted += row[1]
        faulty_found += row[2]
    return VerifyStats(verified=verified, accepted=accepted, faulty_found=faulty_found)


@router.get(
    "/me",
    response_model=MyStatsResponse,
    summary="Get My Statistics",
    description="""
Return the signed-in player's own statistics across all three game stages. Requires the annotator role (or any higher role).

Counters cover the player's overlap votes (stage 1), point annotations (stage 2), and the reviews they performed (stage 3). Accuracy is the fraction of the player's *reviewed* annotations that were approved, reported both over all time and over their most recent `window` annotations (default 100). Unreviewed annotations are excluded from accuracy.

Fails with 422 if window is less than 1.
""",
)
def get_my_stats(request: Request, window: int = 100, db: Session = Depends(get_db)):
    user = require_current_user(request)
    if window < 1:
        raise HTTPException(status_code=422, detail="window must be >= 1")

    return MyStatsResponse(
        window=window,
        unconfirmed_exp=_unconfirmed_exp(db, user.id),
        overlap=_overlap_stats(db, user.id, window),
        annotate=_annotate_stats(db, user.id, window),
        verify=_verify_stats(db, user.id),
    )
