from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LabelResponse(BaseModel):
    """A label that can be assigned to a point annotation."""

    uuid: UUID = Field(description="Unique identifier of the label.")
    scope: str = Field(
        description="Caller-defined namespace for the label. Combined with title, must be unique."
    )
    title: str = Field(description="Display name of the label.")
    description: str | None = Field(
        description="Optional free-text description of the label."
    )


class LabelListResponse(BaseModel):
    labels: list[LabelResponse] = Field(description="All labels in the system.")


class CandidateAnnotationCreateRequest(BaseModel):
    """Request used to create a new candidate pair annotation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "image_a": "1a6ccf07-c766-4934-a6a5-0ca6dbdb5a0b",
                "image_b": "2b7ddf18-d877-5a45-c7b6-1db7ecec6b1f",
                "no_overlap": False,
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier to assign to the new annotation.")

    image_a: UUID = Field(
        description="Unique identifier of one image of the open candidate pair to annotate."
    )

    image_b: UUID = Field(
        description="Unique identifier of the other image of the open candidate pair to annotate."
    )

    no_overlap: bool = Field(description="Whether the two images have no overlap.")


class CandidateAnnotationCorrectionRequest(BaseModel):
    """Request used to correct an existing candidate pair annotation.

    Unlike point annotation correction, no_overlap is always required and
    always overwritten; there is no partial-update behavior.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "no_overlap": True,
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier of the annotation to update.")

    no_overlap: bool = Field(
        description="New value for whether the two images have no overlap."
    )


class CandidateAnnotationResponse(BaseModel):
    """A candidate pair annotation."""

    uuid: UUID = Field(description="Unique identifier of the annotation.")
    image_a: UUID = Field(
        description="Unique identifier of one image of the annotated pair."
    )
    image_b: UUID = Field(
        description="Unique identifier of the other image of the annotated pair."
    )
    no_overlap: bool = Field(description="Whether the two images have no overlap.")
    expert_level: int = Field(
        description="expert_level of the user who created the annotation, captured at creation time."
    )
    status: str = Field(
        description="Lifecycle status of the annotation: review_pending, review_failed, or approved."
    )
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the annotation was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the annotation."
    )
    reviewed_at: Optional[int] = Field(
        description="Unix epoch time in milliseconds when the annotation was reviewed, or null if not yet reviewed."
    )
    reviewed_by: Optional[UUID] = Field(
        description="Unique identifier of the user who reviewed the annotation, or null if not yet reviewed."
    )


class PointAnnotationCreateRequest(BaseModel):
    """Request used to create a new point annotation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "image_a": "1a6ccf07-c766-4934-a6a5-0ca6dbdb5a0b",
                "image_b": "2b7ddf18-d877-5a45-c7b6-1db7ecec6b1f",
                "label_id": None,
                "x1": 125,
                "y1": 240,
                "x2": 89,
                "y2": 247,
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier to assign to the new annotation.")

    image_a: UUID = Field(
        description="Unique identifier of one image of the open image pair to annotate."
    )

    image_b: UUID = Field(
        description="Unique identifier of the other image of the open image pair to annotate."
    )

    label_id: Optional[UUID] = Field(
        default=None,
        description="Optional label for the annotation. Omitting it or sending null both leave the annotation unlabeled.",
    )

    x1: int = Field(ge=0, description="X coordinate of image 1 in pixels.")

    y1: int = Field(ge=0, description="Y coordinate of image 1 in pixels.")

    x2: int = Field(ge=0, description="X coordinate of image 2 in pixels.")

    y2: int = Field(ge=0, description="Y coordinate of image 2 in pixels.")


class PointAnnotationCorrectionRequest(BaseModel):
    """Request used to correct an existing point annotation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "label_id": "1a6ccf07-c766-4934-a6a5-0ca6dbdb5a0b",
                "x1": 125,
                "y1": 240,
                "x2": 89,
                "y2": 247,
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier of the annotation to update.")

    label_id: Optional[UUID] = Field(
        default=None,
        description="Optional new label for the annotation. If omitted, the current label is kept.",
    )

    x1: int = Field(ge=0, description="X coordinate of image 1 in pixels.")

    y1: int = Field(ge=0, description="Y coordinate of image 1 in pixels.")

    x2: int = Field(ge=0, description="X coordinate of image 2 in pixels.")

    y2: int = Field(ge=0, description="Y coordinate of image 2 pixels.")


class PointAnnotationResponse(BaseModel):
    """A point annotation on an image pair."""

    uuid: UUID = Field(description="Unique identifier of the annotation.")
    image_a: UUID = Field(
        description="Unique identifier of one image of the annotated pair."
    )
    image_b: UUID = Field(
        description="Unique identifier of the other image of the annotated pair."
    )
    label_id: Optional[UUID] = Field(
        description="Unique identifier of the label assigned to the annotation, or null if unlabeled."
    )
    x1: int = Field(description="X coordinate of image 1 in pixels.")
    y1: int = Field(description="Y coordinate of image 1 in pixels.")
    x2: int = Field(description="X coordinate of image 2 in pixels.")
    y2: int = Field(description="Y coordinate of image 2 in pixels.")
    expert_level: int = Field(
        description="expert_level of the user who created the annotation, captured at creation time."
    )
    confidence: Optional[float] = Field(description="Currently always null.")
    status: str = Field(
        description="Lifecycle status of the annotation: review_pending, review_failed, or approved."
    )
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the annotation was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the annotation."
    )
    reviewed_at: Optional[int] = Field(
        description="Unix epoch time in milliseconds when the annotation was reviewed, or null if not yet reviewed."
    )
    reviewed_by: Optional[UUID] = Field(
        description="Unique identifier of the user who reviewed the annotation, or null if not yet reviewed."
    )


class PointAnnotationListResponse(BaseModel):
    annotations: list[PointAnnotationResponse] = Field(
        description="Point annotations whose image pair belongs to the given dive."
    )


class NextPairImageResponse(BaseModel):
    """An image within a pair offered for annotation."""

    uuid: UUID = Field(description="Unique identifier of the image.")
    filename: str = Field(description="Display filename of the image.")
    filepath: str = Field(
        description="Relative path under the assets directory the image is stored at."
    )
    dive_id: UUID = Field(description="Unique identifier of the dive the image belongs to.")
    status: str | None = Field(
        description="Lifecycle status of the image, or null if unmapped."
    )
    size_x: int = Field(description="Width of the image in pixels.")
    size_y: int = Field(description="Height of the image in pixels.")
    metadata: Any | None = Field(
        description="Arbitrary caller-supplied JSON object, or null."
    )


class NextPairResponse(BaseModel):
    """An open image pair offered to the caller for point annotation."""

    image1: NextPairImageResponse = Field(description="One image of the pair.")
    image2: NextPairImageResponse = Field(description="The other image of the pair.")
    difficulty: int | None = Field(
        description="Minimum expert_level a user must have to be offered this pair. Null means no gating."
    )
    priority: int | None = Field(
        description="Pairs with a higher priority are offered first; null sorts last."
    )
    status: str | None = Field(
        description="Lifecycle status of the image pair, or null if unmapped."
    )


class NextCandidateResponse(BaseModel):
    """An open candidate pair offered to the caller for overlap review."""

    image1: NextPairImageResponse = Field(description="One image of the pair.")
    image2: NextPairImageResponse = Field(description="The other image of the pair.")
    status: str | None = Field(
        description="Lifecycle status of the candidate pair, or null if unmapped."
    )


class AccuracyStat(BaseModel):
    """An accuracy figure derived from reviewed annotations.

    Accuracy is the fraction of a user's *reviewed* annotations that were
    approved (approved / (approved + review_failed)). Pending and otherwise
    unreviewed annotations are excluded, so `reviewed` is the denominator.
    """

    correct: int = Field(description="Number of the user's annotations that were reviewed and approved.")
    reviewed: int = Field(
        description="Number of the user's annotations that have been reviewed (approved or review_failed)."
    )
    accuracy: float | None = Field(
        description="correct / reviewed, or null when no annotations have been reviewed yet."
    )


class OverlapStats(BaseModel):
    """Stage 1 (Finding Overlap) statistics for a single player."""

    pairs_marked: int = Field(description="Total overlap votes the player has cast.")
    overlaps_found: int = Field(
        description="Overlap votes where the player judged the pair to overlap (no_overlap = false)."
    )
    overall_pairs_with_overlap: int = Field(
        description="Global count of candidate pairs resolved to has_overlap (context, not player-specific)."
    )
    accuracy_all_time: AccuracyStat = Field(description="Overlap accuracy over all of the player's reviewed votes.")
    accuracy_window: AccuracyStat = Field(
        description="Overlap accuracy over the player's most recent `window` votes."
    )


class AnnotateStats(BaseModel):
    """Stage 2 (Annotating) statistics for a single player."""

    annotations: int = Field(description="Total point annotations the player has created.")
    annotations_verified: int = Field(description="Player's point annotations that were reviewed and approved.")
    pairs_marked: int = Field(description="Distinct image pairs the player has annotated.")
    pairs_verified: int = Field(
        description="Distinct image pairs where at least one of the player's annotations was approved."
    )
    accuracy_all_time: AccuracyStat = Field(
        description="Annotation accuracy over all of the player's reviewed annotations."
    )
    accuracy_window: AccuracyStat = Field(
        description="Annotation accuracy over the player's most recent `window` annotations."
    )


class VerifyStats(BaseModel):
    """Stage 3 (Verification) statistics for a single player, i.e. reviews they performed.

    Verification *accuracy* is intentionally omitted: under the review-status
    basis there is no independent ground truth for a single reviewer's call.
    Only counters are reported until a consensus/meta-review mechanism exists.
    """

    verified: int = Field(description="Total annotations the player has reviewed (across overlap and point annotations).")
    accepted: int = Field(description="Reviews where the player approved the annotation.")
    faulty_found: int = Field(description="Reviews where the player marked the annotation as failed.")


class MyStatsResponse(BaseModel):
    """The signed-in player's own statistics across all three game stages."""

    window: int = Field(description="Size of the recent-annotation window used for the windowed accuracies.")
    unconfirmed_exp: int = Field(
        description="Experience the player will gain once their currently pending (unreviewed) submissions are approved by other players."
    )
    overlap: OverlapStats = Field(description="Stage 1 (Finding Overlap) statistics.")
    annotate: AnnotateStats = Field(description="Stage 2 (Annotating) statistics.")
    verify: VerifyStats = Field(description="Stage 3 (Verification) statistics.")

class PointAnnotationReviewResponse(BaseModel):
    """A point annotation pending review, with full image details so the two images can be rendered."""

    uuid: UUID = Field(description="Unique identifier of the annotation.")
    image_a: NextPairImageResponse = Field(description="One image of the annotated pair.")
    image_b: NextPairImageResponse = Field(description="The other image of the annotated pair.")
    label_id: Optional[UUID] = Field(
        description="Unique identifier of the label assigned to the annotation, or null if unlabeled."
    )
    x1: int = Field(description="X coordinate in image_a, in pixels.")
    y1: int = Field(description="Y coordinate in image_a, in pixels.")
    x2: int = Field(description="X coordinate in image_b, in pixels.")
    y2: int = Field(description="Y coordinate in image_b, in pixels.")
    expert_level: int = Field(
        description="expert_level of the user who created the annotation, captured at creation time."
    )
    status: str = Field(description="Always review_pending for items returned by the review queue.")
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the annotation was created."
    )
