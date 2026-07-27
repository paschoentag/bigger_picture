from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.constants import PAIR_STATUS_INT, PairStatus
from src.schema.image_pairs import ImagePair
from src.services.errors import ConflictError
from src.services.lookups import require_same_dive
from src.util import now_ms


def create_image_pair(
    db: Session,
    *,
    image1_id: int,
    image2_id: int,
    status_id: int,
    creator_id: int,
) -> ImagePair:
    """Build, add, and flush a new `ImagePair` row. Does not commit.

    `image1_id`/`image2_id` must already be sorted ascending. Raises
    `SameDiveError` if the two images belong to different dives, or
    `ConflictError` if an image pair for this image combination already
    exists. Always created with null difficulty/priority.
    """
    require_same_dive(db, image1_id, image2_id)

    pair = ImagePair(
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
        raise ConflictError("Image pair already exists") from exc
    return pair


def ensure_image_pair(db: Session, *, image1_id: int, image2_id: int, creator_id: int) -> bool:
    """Create an open ImagePair for the given (already-sorted) image ids if
    one doesn't already exist. Returns True if created, False if one already
    existed.

    Unlike create_image_pair, does not raise on conflict, so it's safe to
    call from within a larger transaction (e.g. a batch status change or
    candidate consensus recompute) that must not be aborted by a
    duplicate-row race.

    Auto-created pairs are immediately open (not hidden) so they're playable
    as soon as Stage 1 consensus resolves them, without requiring manual
    scientist intervention to open them.
    """
    existing = db.execute(
        select(ImagePair).where(
            ImagePair.image1_id == image1_id,
            ImagePair.image2_id == image2_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(
        ImagePair(
            created_at=now_ms(),
            created_by=creator_id,
            image1_id=image1_id,
            image2_id=image2_id,
            status_id=PAIR_STATUS_INT[PairStatus.OPEN],
        )
    )
    return True
