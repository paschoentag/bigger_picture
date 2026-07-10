from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

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
    CommunityAnnotateStats,
    CommunityOverlapStats,
    CommunityStatsResponse,
    CommunityVerifyStats,
    MyStatsResponse,
    OverlapStats,
    VerifyStats,
)
from src.schema.candidate_annotations import CandidateAnnotation
from src.schema.candidate_pairs import CandidatePair
from src.schema.dives import Dive
from src.schema.images import Image
from src.schema.point_annotations import PointAnnotation
from src.schema.regions import Region
from src.schema.users import User

router = APIRouter()

REVIEWED_STATUSES = (ANNOTATION_APPROVED, ANNOTATION_REVIEW_FAILED)
CANDIDATE_HAS_OVERLAP = CANDIDATE_STATUS_INT[CandidateStatus.HAS_OVERLAP]
CANDIDATE_NO_OVERLAP = CANDIDATE_STATUS_INT[CandidateStatus.NO_OVERLAP]
CANDIDATE_OPEN = CANDIDATE_STATUS_INT[CandidateStatus.OPEN]


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


def _community_overlap_stats(db: Session) -> CommunityOverlapStats:
    votes_cast = db.execute(
        select(func.count())
        .select_from(CandidateAnnotation)
        .where(CandidateAnnotation.status_id != ANNOTATION_DELETED)
    ).scalar_one()
    pairs_with_overlap = db.execute(
        select(func.count()).select_from(CandidatePair).where(CandidatePair.status_id == CANDIDATE_HAS_OVERLAP)
    ).scalar_one()
    pairs_no_overlap = db.execute(
        select(func.count()).select_from(CandidatePair).where(CandidatePair.status_id == CANDIDATE_NO_OVERLAP)
    ).scalar_one()
    pairs_still_open = db.execute(
        select(func.count()).select_from(CandidatePair).where(CandidatePair.status_id == CANDIDATE_OPEN)
    ).scalar_one()
    return CommunityOverlapStats(
        votes_cast=votes_cast,
        pairs_with_overlap=pairs_with_overlap,
        pairs_no_overlap=pairs_no_overlap,
        pairs_still_open=pairs_still_open,
    )


def _community_annotate_stats(db: Session) -> CommunityAnnotateStats:
    active = PointAnnotation.status_id != ANNOTATION_DELETED
    points_submitted = db.execute(
        select(func.count()).select_from(PointAnnotation).where(active)
    ).scalar_one()
    points_verified = db.execute(
        select(func.count())
        .select_from(PointAnnotation)
        .where(active, PointAnnotation.status_id == ANNOTATION_APPROVED)
    ).scalar_one()
    points_pending_review = db.execute(
        select(func.count())
        .select_from(PointAnnotation)
        .where(active, PointAnnotation.status_id == ANNOTATION_REVIEW_PENDING)
    ).scalar_one()
    pairs_annotated = db.execute(
        select(func.count(func.distinct(PointAnnotation.pair_id))).where(active)
    ).scalar_one()
    return CommunityAnnotateStats(
        points_submitted=points_submitted,
        points_verified=points_verified,
        points_pending_review=points_pending_review,
        pairs_annotated=pairs_annotated,
    )


def _community_verify_stats(db: Session) -> CommunityVerifyStats:
    reviews_completed = accepted = rejected = 0
    for model in (CandidateAnnotation, PointAnnotation):
        row = db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((model.status_id == ANNOTATION_APPROVED, 1), else_=0)), 0),
                func.coalesce(func.sum(case((model.status_id == ANNOTATION_REVIEW_FAILED, 1), else_=0)), 0),
            )
            .select_from(model)
            .where(model.reviewed_by.is_not(None))
        ).one()
        reviews_completed += row[0]
        accepted += row[1]
        rejected += row[2]
    return CommunityVerifyStats(reviews_completed=reviews_completed, accepted=accepted, rejected=rejected)


@router.get(
    "/overall",
    response_model=CommunityStatsResponse,
    summary="Get Community Statistics",
    description="""
Return aggregate, site-wide statistics across the whole database - dataset size plus totals for all three game stages, summed over every player rather than scoped to the caller. Requires the annotator role (or any higher role).
""",
)
def get_community_stats(db: Session = Depends(get_db)):
    users_total = db.execute(select(func.count()).select_from(User)).scalar_one()
    regions_total = db.execute(select(func.count()).select_from(Region)).scalar_one()
    dives_total = db.execute(select(func.count()).select_from(Dive)).scalar_one()
    images_total = db.execute(select(func.count()).select_from(Image)).scalar_one()

    return CommunityStatsResponse(
        users_total=users_total,
        regions_total=regions_total,
        dives_total=dives_total,
        images_total=images_total,
        overlap=_community_overlap_stats(db),
        annotate=_community_annotate_stats(db),
        verify=_community_verify_stats(db),
    )


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
        overlap=_overlap_stats(db, user.id, window),
        annotate=_annotate_stats(db, user.id, window),
        verify=_verify_stats(db, user.id),
    )
