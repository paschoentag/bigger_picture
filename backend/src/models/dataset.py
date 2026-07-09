from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DatasetSummaryResponse(BaseModel):
    """Aggregate counts across the dataset."""

    dive_count: int = Field(description="Total number of dives.")
    image_count: int = Field(description="Total number of images.")
    image_pair_count: int = Field(description="Total number of image pairs.")


class StatusEnumResponse(BaseModel):
    """A single status value, as recognized by the `status` field of one of the dataset's entity types."""

    name: str = Field(description="The status value itself, e.g. hidden or open.")
    description: str | None = Field(
        description="Free-text explanation of what this status means and when it applies."
    )


class StatusEnumListResponse(BaseModel):
    """All recognized status values, grouped by the entity type they apply to."""

    image_statuses: list[StatusEnumResponse] = Field(
        description="Status values for images."
    )
    pair_statuses: list[StatusEnumResponse] = Field(
        description="Status values for image pairs."
    )
    candidate_statuses: list[StatusEnumResponse] = Field(
        description="Status values for candidate pairs."
    )
    annotation_statuses: list[StatusEnumResponse] = Field(
        description="Status values for point annotations."
    )


class LabelResponse(BaseModel):
    """A label that can be assigned to a point annotation."""

    uuid: UUID = Field(description="Unique identifier of the label.")
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the label was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the label."
    )
    scope: str = Field(
        description="Caller-defined namespace for the label. Combined with title, must be unique."
    )
    title: str = Field(description="Display name of the label.")
    description: str | None = Field(
        description="Optional free-text description of the label."
    )


class RegionResponse(BaseModel):
    """A named region that a dive can be associated with."""

    uuid: UUID = Field(description="Unique identifier of the region.")
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the region was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the region."
    )
    title: str = Field(description="Display name of the region. Must be unique.")
    metadata: Any | None = Field(
        description="Arbitrary caller-supplied JSON object, or null."
    )
    description: str | None = Field(
        description="Optional free-text description of the region."
    )


class RegionListResponse(BaseModel):
    regions: list[RegionResponse] = Field(description="All regions in the system.")


class HelperImageResponse(BaseModel):
    """A helper image: a decorative image asset, not part of the dataset."""

    uuid: UUID = Field(description="Unique identifier of the helper image.")
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the helper image was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who uploaded the helper image."
    )
    filename: str = Field(
        description="Display filename of the helper image. Not used to derive storage path."
    )
    filepath: str = Field(
        description="Relative path under the assets directory the image is stored at. "
        "Content-addressed; served at /assets/{filepath}."
    )


class HelperImageListResponse(BaseModel):
    helper_images: list[HelperImageResponse] = Field(
        description="Helper images, for the requested page."
    )
    total: int = Field(description="Total number of helper images, across all pages.")


class FunFactResponse(BaseModel):
    """A fun fact that can be shown to users."""

    uuid: UUID = Field(description="Unique identifier of the fun fact.")
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the fun fact was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the fun fact."
    )
    title: str = Field(description="Display name of the fun fact. Must be unique.")
    fact: Any = Field(description="Arbitrary caller-supplied JSON object describing the fact.")
    min_level: int = Field(
        description="Minimum expert_level a user must have to be shown this fact."
    )
    region: UUID | None = Field(
        description="Unique identifier of the region this fact is scoped to, or null if it applies to all regions."
    )
    image: HelperImageResponse | None = Field(
        description="The helper image attached to this fun fact, or null if none is attached."
    )


class FunFactListResponse(BaseModel):
    fun_facts: list[FunFactResponse] = Field(description="Fun facts, for the requested page.")
    total: int = Field(description="Total number of fun facts, across all pages.")


class FunFactCreateRequest(BaseModel):
    """Request used to create a new fun fact."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "title": "Octopuses have three hearts",
                "fact": {"text": "Octopuses have three hearts and blue blood."},
                "min_level": 0,
                "region": None,
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier to assign to the new fun fact.")

    title: str = Field(
        min_length=1,
        max_length=127,
        description="Display name of the fun fact. Must be unique.",
    )

    fact: Any = Field(description="Arbitrary JSON object describing the fact.")

    min_level: int = Field(
        default=0,
        description="Minimum expert_level a user must have to be shown this fact.",
    )

    region: UUID | None = Field(
        default=None,
        description="Unique identifier of the region to scope this fact to. Omit or send null to apply to all regions.",
    )

    image: str | None = Field(
        default=None,
        description="Base64-encoded raw image bytes to upload as this fact's image. Deduplicated "
        "by content: if identical bytes were uploaded before, the existing helper image is reused. "
        "Mutually exclusive with image_uuid. Requires image_filename.",
    )

    image_filename: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Display filename to record for the uploaded image. Required when image is "
        "supplied; rejected with 422 if supplied without image.",
    )

    image_uuid: UUID | None = Field(
        default=None,
        description="Unique identifier of an existing helper image to attach instead of uploading "
        "a new one. Mutually exclusive with image.",
    )


class FunFactUpdateRequest(BaseModel):
    """Request used to partially update an existing fun fact.

    Only the fields explicitly supplied are changed; omitted fields are left
    untouched. Sending an explicit null for title, fact, or min_level is also
    a no-op, since none of these columns are nullable. Sending an explicit
    null for region clears it (the fact then applies to all regions).

    Image handling has four states, since it needs one more than the usual
    present/null/value truth table can express: leave unchanged (omit image,
    image_uuid, and clear_image), upload new bytes (image + image_filename),
    attach an existing helper image (image_uuid), or detach the current image
    (clear_image: true). At most one of these may be active at a time.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "min_level": 2,
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier of the fun fact to update.")

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=127,
        description="New display name. Must be unique. Omit to leave unchanged.",
    )

    fact: Any | None = Field(
        default=None,
        description="New fact payload. Omit to leave unchanged.",
    )

    min_level: int | None = Field(
        default=None,
        description="New minimum expert_level. Omit to leave unchanged.",
    )

    region: UUID | None = Field(
        default=None,
        description="New region to scope this fact to. Send null to clear it, or omit to leave unchanged.",
    )

    image: str | None = Field(
        default=None,
        description="Base64-encoded raw image bytes to upload and attach, replacing any current "
        "image. Deduplicated by content. Mutually exclusive with image_uuid and clear_image. "
        "Requires image_filename.",
    )

    image_filename: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Display filename for the uploaded image. Required when image is supplied; "
        "rejected with 422 if supplied without image.",
    )

    image_uuid: UUID | None = Field(
        default=None,
        description="Unique identifier of an existing helper image to attach instead of uploading "
        "a new one. Mutually exclusive with image and clear_image.",
    )

    clear_image: bool = Field(
        default=False,
        description="If true, detach the current image (sets it to null). Mutually exclusive with "
        "image and image_uuid. Omit or false to leave the image unchanged.",
    )


class CameraResponse(BaseModel):
    """A camera that a dive can be recorded with."""

    uuid: UUID = Field(description="Unique identifier of the camera.")
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the camera was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the camera."
    )
    title: str = Field(description="Display name of the camera. Must be unique.")
    metadata: Any | None = Field(
        description="Arbitrary caller-supplied JSON object, or null."
    )
    description: str | None = Field(
        description="Optional free-text description of the camera."
    )


class DiveCreateRequest(BaseModel):
    """Request used to create a new dive."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "title": "Dive 1",
                "metadata": None,
                "description": None,
                "region": "1a6ccf07-c766-4934-a6a5-0ca6dbdb5a0b",
                "camera": None,
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier to assign to the new dive.")

    title: str = Field(
        min_length=1,
        max_length=127,
        description="Display name of the dive. Must be unique.",
    )

    metadata: dict[str, Any] | None = Field(
        default=None, description="Arbitrary JSON object to attach to the dive."
    )

    description: str | None = Field(
        default=None,
        max_length=1023,
        description="Optional free-text description of the dive.",
    )

    region: UUID = Field(
        description="Unique identifier of an existing region to associate with the dive."
    )

    camera: UUID | None = Field(
        default=None,
        description='Unique identifier of an existing camera to associate with the dive. If omitted, falls back to the well-known "Unknown Camera".',
    )


class DiveUpdateRequest(BaseModel):
    """Request used to partially update an existing dive.

    Only the fields explicitly supplied are changed; omitted fields are left
    untouched. Sending an explicit null for title, region, or camera is also a
    no-op, since none of these can be cleared.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "title": "Dive 1 (renamed)",
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier of the dive to update.")

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=127,
        description="New display name. Must be unique. Omit to leave unchanged.",
    )

    metadata: dict[str, Any] | None = Field(
        default=None,
        description="New metadata object. Send null to clear it, or omit to leave unchanged.",
    )

    description: str | None = Field(
        default=None,
        max_length=1023,
        description="New description. Send null to clear it, or omit to leave unchanged.",
    )

    region: UUID | None = Field(
        default=None,
        description="Unique identifier of a new region to associate with the dive. Omit to leave unchanged.",
    )

    camera: UUID | None = Field(
        default=None,
        description="Unique identifier of a new camera to associate with the dive. Omit to leave unchanged.",
    )


class DiveResponse(BaseModel):
    """A dive: an association between a region, a camera, and the images captured during it."""

    uuid: UUID = Field(description="Unique identifier of the dive.")
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the dive was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the dive."
    )
    title: str = Field(description="Display name of the dive.")
    metadata: Any | None = Field(
        description="Arbitrary caller-supplied JSON object, or null."
    )
    description: str | None = Field(
        description="Optional free-text description of the dive."
    )
    region: UUID = Field(
        description="Unique identifier of the region associated with the dive."
    )
    camera: UUID = Field(
        description="Unique identifier of the camera associated with the dive."
    )


class DiveListResponse(BaseModel):
    dives: list[DiveResponse] = Field(description="All dives in the system.")


class ImageCreateRequest(BaseModel):
    """Request model used to upload a new image."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "filename": "frame_0001.jpg",
                "filepath": "dive1/frame_0001.jpg",
                "dive_uuid": "1a6ccf07-c766-4934-a6a5-0ca6dbdb5a0b",
                "metadata": None,
                "difficulty": None,
                "priority": None,
                "image": "<base64-encoded image bytes>",
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier to assign to the new image.")

    filename: str = Field(
        min_length=1, max_length=255, description="Display filename of the image."
    )

    filepath: str = Field(
        min_length=1,
        max_length=1023,
        description="Relative path under the assets directory to store the image at. Must be unique.",
    )

    dive_uuid: UUID = Field(
        description="Unique identifier of an existing dive to associate the image with."
    )

    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional arbitrary JSON object to attach to the image.",
    )

    difficulty: int | None = Field(
        default=None,
        description="Stored verbatim; not currently used by any query logic.",
    )

    priority: int | None = Field(
        default=None,
        description="Stored verbatim; not currently used by any query logic.",
    )

    image: str = Field(
        description="Base64-encoded raw image bytes. Decoded and written to filepath; the image's width and height are computed from the decoded bytes, not read from this request."
    )


class ImageUpdateRequest(BaseModel):
    """Request used to partially update an existing image, optionally replacing its file.

    Only the fields explicitly supplied are changed; omitted fields are left
    untouched. Sending an explicit null for filename, filepath, or dive_uuid
    is also a no-op, since none of these can be cleared.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
                "difficulty": 2,
            }
        }
    )

    uuid: UUID = Field(description="Unique identifier of the image to update.")

    filename: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New display filename. Omit to leave unchanged.",
    )

    filepath: str | None = Field(
        default=None,
        min_length=1,
        max_length=1023,
        description="New relative path under the assets directory. Must be unique. Omit to leave unchanged. The file will be moved to this new path in the assets directory.",
    )

    dive_uuid: UUID | None = Field(
        default=None,
        description="Unique identifier of a new dive to associate the image with. Omit to leave unchanged.",
    )

    metadata: dict[str, Any] | None = Field(
        default=None,
        description="New metadata object. Send null to clear it, or omit to leave unchanged.",
    )

    difficulty: int | None = Field(
        default=None,
        description="Send null to clear it, or omit to leave unchanged. Stored verbatim; not currently used by any query logic.",
    )

    priority: int | None = Field(
        default=None,
        description="Send null to clear it, or omit to leave unchanged. Stored verbatim; not currently used by any query logic.",
    )

    image: str | None = Field(
        default=None,
        description="Base64-encoded raw image bytes to replace the current file with. Omit to leave the file unchanged. Rejected with 409 if it would change the image's dimensions while point annotations referencing it exist to prevent inconsistencies.",
    )


class ImageResponse(BaseModel):
    """An image belonging to a dive."""

    uuid: UUID = Field(description="Unique identifier of the image.")
    created_at: int = Field(
        description="Unix epoch time in milliseconds when the image was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the image."
    )
    filename: str = Field(description="Display filename of the image.")
    filepath: str = Field(
        description="Relative path under the assets directory the image is stored at."
    )
    dive: UUID = Field(
        description="Unique identifier of the dive the image belongs to."
    )
    status: str | None = Field(
        description='Lifecycle status of the image (hidden, open, review_pending, finalized, or deleted). Always "hidden" on creation.'
    )
    size_x: int = Field(
        description="Width of the image in pixels, computed from the uploaded file."
    )
    size_y: int = Field(
        description="Height of the image in pixels, computed from the uploaded file."
    )
    metadata: Any | None = Field(
        description="Arbitrary caller-supplied JSON object, or null."
    )
    difficulty: int | None = Field(
        description="Stored verbatim; not currently used by any query logic."
    )
    priority: int | None = Field(
        description="Stored verbatim; not currently used by any query logic."
    )


class ImageListResponse(BaseModel):
    images: list[ImageResponse] = Field(description="Images belonging to the given dive, for the requested page.")
    total: int = Field(description="Total number of images belonging to the dive, across all pages.")


class ImagePairRef(BaseModel):
    """A pair of images, referenced by their uuids."""

    image_a: UUID = Field(
        description="Unique identifier of one image in the pair. Order of image_a and image_b does not matter."
    )
    image_b: UUID = Field(
        description="Unique identifier of the other image in the pair. Must differ from image_a."
    )


class CandidatePairResponse(BaseModel):
    """A candidate pair of images awaiting an overlap review, before it becomes an image pair."""

    created_at: int = Field(
        description="Unix epoch time in milliseconds when the candidate pair was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the candidate pair."
    )
    image_a: UUID = Field(
        description="Unique identifier of one image in the pair. Order of image_a and image_b does not matter."
    )
    image_b: UUID = Field(
        description="Unique identifier of the other image in the pair. Order of image_a and image_b does not matter."
    )
    image_a_filename: str = Field(description="Display filename of image_a.")
    image_b_filename: str = Field(description="Display filename of image_b.")
    status: str | None = Field(
        description='Lifecycle status of the candidate pair (hidden, open, no_overlap, has_overlap, or deleted). Always "hidden" on creation.'
    )


class CandidatePairListResponse(BaseModel):
    candidates: list[CandidatePairResponse] = Field(
        description="Candidate pairs whose images both belong to the given dive, for the requested page."
    )
    total: int = Field(description="Total number of matching candidate pairs, across all pages.")
    hidden_count: int = Field(
        description="Total number of matching candidate pairs with status hidden, across all pages."
    )


class DivePublishRequest(BaseModel):
    """Request to publish a batch of hidden candidate pairs in a dive."""

    dive_uuid: UUID = Field(description="Dive whose hidden candidate pairs to publish.")


class PublishCandidatesResponse(BaseModel):
    published: int = Field(description="Number of candidate pairs moved from hidden to open.")
    remaining_hidden: int = Field(
        description="Number of candidate pairs still hidden in this dive after publishing."
    )


class StrideCandidatePairRequest(BaseModel):
    """Request to bulk-create candidate pairs across a dive's images by sliding stride."""

    dive_uuid: UUID = Field(description="Dive whose images to pair up.")
    stride: int = Field(
        gt=0,
        description="Distance between paired images in sort order; 1 pairs each image with the next.",
    )
    sort_by: Literal["filename", "filepath"] = Field(
        default="filename", description="Image field to sort by (ascending) before pairing."
    )


class StrideCandidatePairResponse(BaseModel):
    total_images: int = Field(description="Number of images in the dive considered.")
    pairs_considered: int = Field(
        description="Number of (image[i], image[i+stride]) pairs generated."
    )
    pairs_created: int = Field(description="Number of new candidate pairs created.")
    pairs_skipped: int = Field(
        description="Number of pairs that already existed and were left unchanged."
    )


class ImagePairResponse(BaseModel):
    """A pair of images available for point annotation."""

    created_at: int = Field(
        description="Unix epoch time in milliseconds when the image pair was created."
    )
    created_by: UUID = Field(
        description="Unique identifier of the user who created the image pair."
    )
    image_a: UUID = Field(
        description="Unique identifier of one image in the pair. Order of image_a and image_b does not matter."
    )
    image_b: UUID = Field(
        description="Unique identifier of the other image in the pair. Order of image_a and image_b does not matter."
    )
    image_a_filename: str = Field(description="Display filename of image_a.")
    image_b_filename: str = Field(description="Display filename of image_b.")
    difficulty: int | None = Field(
        description="Minimum expert_level a user must have to be offered this pair for annotation. Null means no gating."
    )
    priority: int | None = Field(
        description="Pairs with a higher priority are offered for annotation first; null sorts last."
    )
    status: str | None = Field(
        description='Lifecycle status of the image pair (hidden, open, review_pending, finalized, or deleted). Always "hidden" on creation.'
    )


class ImagePairListResponse(BaseModel):
    pairs: list[ImagePairResponse] = Field(
        description="Image pairs whose images both belong to the given dive, for the requested page."
    )
    total: int = Field(description="Total number of matching image pairs, across all pages.")


class DatasetImportCounts(BaseModel):
    """Number of rows created per entity type by a zip import."""

    labels: int = Field(description="Number of labels created.")
    cameras: int = Field(description="Number of cameras created.")
    regions: int = Field(description="Number of regions created.")
    dives: int = Field(description="Number of dives created.")
    images: int = Field(description="Number of images created.")
    candidate_pairs: int = Field(description="Number of candidate pairs created.")
    image_pairs: int = Field(description="Number of image pairs created.")
    helper_images: int = Field(description="Number of helper images created.")
    fun_facts: int = Field(description="Number of fun facts created.")


class DatasetImportResponse(BaseModel):
    """Result of a successful zip import."""

    created: DatasetImportCounts = Field(
        description="Per-entity created counts. Newly minted uuids (from rows using uuid \"new\") are not echoed back - reference them by title in later rows of the same import instead."
    )


class ImageZipImportResponse(BaseModel):
    """Result of a successful images-only zip import into a single dive."""

    created: int = Field(description="Number of images created.")
    skipped: int = Field(description="Number of non-image files in the zip that were ignored.")
