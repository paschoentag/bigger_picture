from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.schema.candidate_pairs import CandidatePair
from src.services.errors import ConflictError
from src.services.lookups import require_same_dive
from src.util import now_ms


def create_candidate_pair(
    db: Session,
    *,
    image1_id: int,
    image2_id: int,
    status_id: int,
    creator_id: int,
) -> CandidatePair:
    """Build, add, and flush a new `CandidatePair` row. Does not commit.

    `image1_id`/`image2_id` must already be sorted ascending. Raises
    `SameDiveError` if the two images belong to different dives, or
    `ConflictError` if a candidate pair for this image combination already
    exists.
    """
    require_same_dive(db, image1_id, image2_id)

    pair = CandidatePair(
        created_at=now_ms(),
        created_by=creator_id,
        image1_id=image1_id,
        image2_id=image2_id,
        status_id=status_id,
    )
    db.add(pair)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("Candidate pair already exists") from exc
    return pair


def ensure_candidate_pair(
    db: Session,
    *,
    image1_id: int,
    image2_id: int,
    creator_id: int,
    status_id: int,
) -> bool:
    """Create a CandidatePair for the given (already-sorted) image ids if
    one doesn't already exist. Returns True if created, False if one already
    existed.

    Unlike create_candidate_pair, does not raise on conflict, so it's safe to
    call from within a larger transaction (e.g. a stride batch create) that
    must not be aborted by a duplicate-row race.
    """
    existing = db.execute(
        select(CandidatePair).where(
            CandidatePair.image1_id == image1_id,
            CandidatePair.image2_id == image2_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(
        CandidatePair(
            created_at=now_ms(),
            created_by=creator_id,
            image1_id=image1_id,
            image2_id=image2_id,
            status_id=status_id,
        )
    )
    return True
