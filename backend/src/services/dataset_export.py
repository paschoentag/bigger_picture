"""CSV/zip export writers for the dataset section (scientist role).

Every writer drops internal integer ids and resolves foreign keys to the
referenced row's uuid before emitting a row. `image_pairs`/`candidate_pairs`
are the one deliberate exception: they have no uuid of their own and are
identified purely by their two images' uuids (a natural key) everywhere they
appear, in their own CSV and in any other table's reference to them (e.g.
`point_annotations.pair_id` becomes `pair_image1_uuid`/`pair_image2_uuid`, not
a single `pair_uuid`). This is required for conflict-free merging: since a
pair has no identity beyond its two images, two databases that already agree
on image uuids automatically agree on pair identity too, with no independently
minted uuid to reconcile.

CSV cells are comma-delimited (not the `;` used by the existing zip-upload
importer's CSV contract) to match the already-shipped
`point_annotations.py::export_point_annotations_csv` endpoint that some of
these writers extend. Don't "fix" this to match the importer - a separate,
more capable admin import/merge tool is planned for later and will be built to
consume whatever shape this export produces.
"""

import csv
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import TextIO
from uuid import UUID

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session, aliased

from src.constants import (
    INT_ANNOTATION_STATUS,
    INT_CANDIDATE_STATUS,
    INT_IMAGE_STATUS,
    INT_PAIR_STATUS,
)
from src.schema.cameras import Camera
from src.schema.candidate_annotations import CandidateAnnotation
from src.schema.candidate_pairs import CandidatePair
from src.schema.dives import Dive
from src.schema.fun_facts import FunFact
from src.schema.helper_images import HelperImage
from src.schema.image_pairs import ImagePair
from src.schema.images import Image
from src.schema.labels import Label
from src.schema.point_annotations import PointAnnotation
from src.schema.quest_claims import QuestClaim
from src.schema.regions import Region
from src.schema.seen_facts import SeenFact
from src.schema.users import User
from src.services.assets import resolve_asset_path

# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def _uuid_str(raw: bytes | None) -> str:
    return str(UUID(bytes=raw)) if raw is not None else ""


def _opt(value) -> str:
    return "" if value is None else value


def _status_title(int_map: dict[int, object], status_id: int | None) -> str:
    if status_id is None:
        return ""
    status = int_map.get(status_id)
    return str(status) if status is not None else str(status_id)


# --------------------------------------------------------------------------
# Per-table CSV writers (full structural export)
# --------------------------------------------------------------------------


def write_users_csv(db: Session, buffer: TextIO) -> None:
    writer = csv.writer(buffer)
    writer.writerow(["uuid", "created_at", "created_by_uuid", "username", "role", "expert_level", "exp", "story"])
    creator = aliased(User)
    rows = db.execute(
        select(User, creator).join(creator, User.created_by == creator.id).order_by(User.id)
    ).all()
    for user, creator_row in rows:
        writer.writerow(
            [
                _uuid_str(user.uuid),
                user.created_at,
                _uuid_str(creator_row.uuid),
                user.username,
                user.role,
                user.expert_level,
                user.exp,
                _opt(user.story),
            ]
        )


def write_labels_csv(db: Session, buffer: TextIO) -> None:
    writer = csv.writer(buffer)
    writer.writerow(["uuid", "created_at", "created_by_uuid", "scope", "title", "description"])
    creator = aliased(User)
    rows = db.execute(
        select(Label, creator).join(creator, Label.created_by == creator.id).order_by(Label.id)
    ).all()
    for label, creator_row in rows:
        writer.writerow(
            [
                _uuid_str(label.uuid),
                label.created_at,
                _uuid_str(creator_row.uuid),
                label.scope,
                label.title,
                _opt(label.description),
            ]
        )


def _write_titled_metadata_csv(db: Session, buffer: TextIO, model) -> None:
    """Shared row writer for cameras.csv/regions.csv: uuid, title, metadata, description."""
    writer = csv.writer(buffer)
    writer.writerow(["uuid", "created_at", "created_by_uuid", "title", "metadata", "description"])
    creator = aliased(User)
    rows = db.execute(
        select(model, creator).join(creator, model.created_by == creator.id).order_by(model.id)
    ).all()
    for row, creator_row in rows:
        writer.writerow(
            [
                _uuid_str(row.uuid),
                row.created_at,
                _uuid_str(creator_row.uuid),
                row.title,
                _opt(row.metadata_json),
                _opt(row.description),
            ]
        )


def write_cameras_csv(db: Session, buffer: TextIO) -> None:
    _write_titled_metadata_csv(db, buffer, Camera)


def write_regions_csv(db: Session, buffer: TextIO) -> None:
    _write_titled_metadata_csv(db, buffer, Region)


def write_dives_csv(db: Session, buffer: TextIO) -> None:
    writer = csv.writer(buffer)
    writer.writerow(
        ["uuid", "created_at", "created_by_uuid", "title", "metadata", "description", "region_uuid", "camera_uuid"]
    )
    creator = aliased(User)
    rows = db.execute(
        select(Dive, creator, Region, Camera)
        .join(creator, Dive.created_by == creator.id)
        .join(Region, Dive.region_id == Region.id)
        .join(Camera, Dive.camera_id == Camera.id)
        .order_by(Dive.id)
    ).all()
    for dive, creator_row, region, camera in rows:
        writer.writerow(
            [
                _uuid_str(dive.uuid),
                dive.created_at,
                _uuid_str(creator_row.uuid),
                dive.title,
                _opt(dive.metadata_json),
                _opt(dive.description),
                _uuid_str(region.uuid),
                _uuid_str(camera.uuid),
            ]
        )


def write_images_csv(db: Session, buffer: TextIO) -> None:
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "uuid", "created_at", "created_by_uuid", "filename", "filepath", "dive_uuid",
            "status", "size_x", "size_y", "metadata", "difficulty", "priority",
        ]
    )
    creator = aliased(User)
    rows = db.execute(
        select(Image, creator, Dive)
        .join(creator, Image.created_by == creator.id)
        .join(Dive, Image.dive_id == Dive.id)
        .order_by(Image.id)
    ).all()
    for image, creator_row, dive in rows:
        writer.writerow(
            [
                _uuid_str(image.uuid),
                image.created_at,
                _uuid_str(creator_row.uuid),
                image.filename,
                image.filepath,
                _uuid_str(dive.uuid),
                _status_title(INT_IMAGE_STATUS, image.status_id),
                image.size_x,
                image.size_y,
                _opt(image.metadata_json),
                _opt(image.difficulty),
                _opt(image.priority),
            ]
        )


def write_image_pairs_csv(db: Session, buffer: TextIO) -> None:
    """No id/uuid column: image1_uuid+image2_uuid together are this row's identity."""
    writer = csv.writer(buffer)
    writer.writerow(["image1_uuid", "image2_uuid", "created_at", "created_by_uuid", "difficulty", "priority", "status"])
    creator = aliased(User)
    image1 = aliased(Image)
    image2 = aliased(Image)
    rows = db.execute(
        select(ImagePair, creator, image1, image2)
        .join(creator, ImagePair.created_by == creator.id)
        .join(image1, ImagePair.image1_id == image1.id)
        .join(image2, ImagePair.image2_id == image2.id)
        .order_by(ImagePair.id)
    ).all()
    for pair, creator_row, img1, img2 in rows:
        writer.writerow(
            [
                _uuid_str(img1.uuid),
                _uuid_str(img2.uuid),
                pair.created_at,
                _uuid_str(creator_row.uuid),
                _opt(pair.difficulty),
                _opt(pair.priority),
                _status_title(INT_PAIR_STATUS, pair.status_id),
            ]
        )


def write_candidate_pairs_csv(db: Session, buffer: TextIO) -> None:
    """No id/uuid column: image1_uuid+image2_uuid together are this row's identity."""
    writer = csv.writer(buffer)
    writer.writerow(["image1_uuid", "image2_uuid", "created_at", "created_by_uuid", "status", "reviewed_at", "reviewed_by_uuid"])
    creator = aliased(User)
    reviewer = aliased(User)
    image1 = aliased(Image)
    image2 = aliased(Image)
    rows = db.execute(
        select(CandidatePair, creator, image1, image2, reviewer)
        .join(creator, CandidatePair.created_by == creator.id)
        .join(image1, CandidatePair.image1_id == image1.id)
        .join(image2, CandidatePair.image2_id == image2.id)
        .outerjoin(reviewer, CandidatePair.reviewed_by == reviewer.id)
        .order_by(CandidatePair.id)
    ).all()
    for pair, creator_row, img1, img2, reviewer_row in rows:
        writer.writerow(
            [
                _uuid_str(img1.uuid),
                _uuid_str(img2.uuid),
                pair.created_at,
                _uuid_str(creator_row.uuid),
                _status_title(INT_CANDIDATE_STATUS, pair.status_id),
                _opt(pair.reviewed_at),
                _uuid_str(reviewer_row.uuid) if reviewer_row is not None else "",
            ]
        )


def write_point_annotations_csv(db: Session, buffer: TextIO) -> None:
    """The annotation's pair is referenced by its two image uuids, not a pair uuid."""
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "uuid", "created_at", "created_by_uuid", "pair_image1_uuid", "pair_image2_uuid",
            "label_uuid", "x1", "y1", "x2", "y2", "expert_level", "confidence",
            "status", "reviewed_at", "reviewed_by_uuid",
        ]
    )
    creator = aliased(User)
    reviewer = aliased(User)
    image1 = aliased(Image)
    image2 = aliased(Image)
    rows = db.execute(
        select(PointAnnotation, creator, image1, image2, Label, reviewer)
        .join(creator, PointAnnotation.created_by == creator.id)
        .join(ImagePair, PointAnnotation.pair_id == ImagePair.id)
        .join(image1, ImagePair.image1_id == image1.id)
        .join(image2, ImagePair.image2_id == image2.id)
        .outerjoin(Label, PointAnnotation.label_id == Label.id)
        .outerjoin(reviewer, PointAnnotation.reviewed_by == reviewer.id)
        .order_by(PointAnnotation.id)
    ).all()
    for ann, creator_row, img1, img2, label, reviewer_row in rows:
        writer.writerow(
            [
                _uuid_str(ann.uuid),
                ann.created_at,
                _uuid_str(creator_row.uuid),
                _uuid_str(img1.uuid),
                _uuid_str(img2.uuid),
                _uuid_str(label.uuid) if label is not None else "",
                ann.x1,
                ann.y1,
                ann.x2,
                ann.y2,
                ann.expert_level,
                _opt(ann.confidence),
                _status_title(INT_ANNOTATION_STATUS, ann.status_id),
                _opt(ann.reviewed_at),
                _uuid_str(reviewer_row.uuid) if reviewer_row is not None else "",
            ]
        )


def write_candidate_annotations_csv(db: Session, buffer: TextIO) -> None:
    """The vote's candidate pair is referenced by its two image uuids, not a candidate uuid."""
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "uuid", "created_at", "created_by_uuid", "candidate_image1_uuid", "candidate_image2_uuid",
            "no_overlap", "expert_level", "status", "reviewed_at", "reviewed_by_uuid",
        ]
    )
    creator = aliased(User)
    reviewer = aliased(User)
    image1 = aliased(Image)
    image2 = aliased(Image)
    rows = db.execute(
        select(CandidateAnnotation, creator, image1, image2, reviewer)
        .join(creator, CandidateAnnotation.created_by == creator.id)
        .join(CandidatePair, CandidateAnnotation.candidate_id == CandidatePair.id)
        .join(image1, CandidatePair.image1_id == image1.id)
        .join(image2, CandidatePair.image2_id == image2.id)
        .outerjoin(reviewer, CandidateAnnotation.reviewed_by == reviewer.id)
        .order_by(CandidateAnnotation.id)
    ).all()
    for ann, creator_row, img1, img2, reviewer_row in rows:
        writer.writerow(
            [
                _uuid_str(ann.uuid),
                ann.created_at,
                _uuid_str(creator_row.uuid),
                _uuid_str(img1.uuid),
                _uuid_str(img2.uuid),
                int(ann.no_overlap),
                ann.expert_level,
                _status_title(INT_ANNOTATION_STATUS, ann.status_id),
                _opt(ann.reviewed_at),
                _uuid_str(reviewer_row.uuid) if reviewer_row is not None else "",
            ]
        )


def write_fun_facts_csv(db: Session, buffer: TextIO) -> None:
    writer = csv.writer(buffer)
    writer.writerow(["uuid", "created_at", "created_by_uuid", "title", "fact", "min_level", "region_uuid", "image_uuid"])
    creator = aliased(User)
    rows = db.execute(
        select(FunFact, creator).join(creator, FunFact.created_by == creator.id).order_by(FunFact.id)
    ).all()
    for fact, creator_row in rows:
        region_uuid = ""
        if fact.region_id is not None:
            region = db.get(Region, fact.region_id)
            region_uuid = _uuid_str(region.uuid)
        image_uuid = ""
        if fact.image_id is not None:
            helper_image = db.get(HelperImage, fact.image_id)
            image_uuid = _uuid_str(helper_image.uuid)
        writer.writerow(
            [
                _uuid_str(fact.uuid),
                fact.created_at,
                _uuid_str(creator_row.uuid),
                fact.title,
                fact.fact_json,
                fact.min_level,
                region_uuid,
                image_uuid,
            ]
        )


def write_helper_images_csv(db: Session, buffer: TextIO, helper_image_ids: list[int] | None = None) -> None:
    writer = csv.writer(buffer)
    writer.writerow(["uuid", "created_at", "created_by_uuid", "filepath", "filename", "blake3_hash"])
    creator = aliased(User)
    stmt = (
        select(HelperImage, creator)
        .join(creator, HelperImage.created_by == creator.id)
        .order_by(HelperImage.id)
    )
    if helper_image_ids is not None:
        stmt = stmt.where(HelperImage.id.in_(helper_image_ids))
    rows = db.execute(stmt).all()
    for helper_image, creator_row in rows:
        writer.writerow(
            [
                _uuid_str(helper_image.uuid),
                helper_image.created_at,
                _uuid_str(creator_row.uuid),
                helper_image.filepath,
                helper_image.filename,
                helper_image.blake3_hash.hex(),
            ]
        )


def write_seen_facts_csv(db: Session, buffer: TextIO) -> None:
    seen_user = aliased(User)
    seen_fact = aliased(FunFact)
    rows = db.execute(
        select(SeenFact, seen_user, seen_fact)
        .join(seen_user, SeenFact.user_id == seen_user.id)
        .join(seen_fact, SeenFact.fact_id == seen_fact.id)
        .order_by(SeenFact.user_id, SeenFact.fact_id)
    ).all()
    writer = csv.writer(buffer)
    writer.writerow(["user_uuid", "fact_uuid", "seen_count"])
    for seen, user_row, fact_row in rows:
        writer.writerow([_uuid_str(user_row.uuid), _uuid_str(fact_row.uuid), seen.seen_count])


def write_quest_claims_csv(db: Session, buffer: TextIO) -> None:
    writer = csv.writer(buffer)
    writer.writerow(["user_uuid", "quest_key", "day_start_ms", "reward_exp", "created_at"])
    rows = db.execute(
        select(QuestClaim, User)
        .join(User, QuestClaim.user_id == User.id)
        .order_by(QuestClaim.id)
    ).all()
    for claim, user_row in rows:
        writer.writerow(
            [_uuid_str(user_row.uuid), claim.quest_key, claim.day_start_ms, claim.reward_exp, claim.created_at]
        )


# --------------------------------------------------------------------------
# Flat-view CSV writers (existing SQL views, minus their leaked internal ids)
# --------------------------------------------------------------------------

_POINT_FLAT_COLUMNS = [
    "uuid", "created_at", "created_by", "expert_level", "confidence", "annotation_status",
    "reviewed_at", "reviewed_by", "label_uuid", "label_scope", "label_title",
    "pair_created_at", "pair_created_by", "pair_difficulty", "pair_priority", "pair_status",
    "image1_uuid", "image1_filename", "image1_filepath", "image1_status",
    "image1_size_x", "image1_size_y", "image1_difficulty", "image1_priority",
    "image2_uuid", "image2_filename", "image2_filepath", "image2_status",
    "image2_size_x", "image2_size_y", "image2_difficulty", "image2_priority",
    "dive_uuid", "dive_title", "x1", "y1", "x2", "y2",
]
_POINT_FLAT_UUID_COLUMNS = {"uuid", "label_uuid", "image1_uuid", "image2_uuid", "dive_uuid"}

_CANDIDATE_FLAT_COLUMNS = [
    "uuid", "created_at", "created_by", "no_overlap", "expert_level", "annotation_status",
    "reviewed_at", "reviewed_by", "candidate_created_at", "candidate_created_by", "candidate_status",
    "image1_uuid", "image1_filename", "image1_filepath", "image1_status",
    "image1_size_x", "image1_size_y", "image1_difficulty", "image1_priority",
    "image2_uuid", "image2_filename", "image2_filepath", "image2_status",
    "image2_size_x", "image2_size_y", "image2_difficulty", "image2_priority",
    "dive_uuid", "dive_title",
]
_CANDIDATE_FLAT_UUID_COLUMNS = {"uuid", "image1_uuid", "image2_uuid", "dive_uuid"}


def _flat_row_values(row, columns: list[str], uuid_columns: set[str]) -> list:
    values = []
    for column in columns:
        value = getattr(row, column)
        if value is None:
            values.append("")
        elif column in uuid_columns:
            values.append(_uuid_str(value))
        else:
            values.append(value)
    return values


def _write_flat_view_csv(
    db: Session, buffer: TextIO, view_name: str, columns: list[str], uuid_columns: set[str], dive_ids: list[int] | None
) -> None:
    writer = csv.writer(buffer)
    writer.writerow(columns)
    selected = ", ".join(f"v.{column}" for column in columns)
    sql = f"SELECT {selected} FROM {view_name} v"
    params: dict = {}
    if dive_ids is not None:
        sql += " JOIN dives d ON d.uuid = v.dive_uuid WHERE d.id IN :dive_ids"
        params["dive_ids"] = dive_ids
    stmt = text(sql)
    if dive_ids is not None:
        stmt = stmt.bindparams(bindparam("dive_ids", expanding=True))
    for row in db.execute(stmt, params):
        writer.writerow(_flat_row_values(row, columns, uuid_columns))


def write_point_annotation_flat_csv(db: Session, buffer: TextIO, dive_ids: list[int] | None = None) -> None:
    _write_flat_view_csv(
        db, buffer, "view_point_annotation_flat", _POINT_FLAT_COLUMNS, _POINT_FLAT_UUID_COLUMNS, dive_ids
    )


def write_candidate_annotation_flat_csv(db: Session, buffer: TextIO, dive_ids: list[int] | None = None) -> None:
    _write_flat_view_csv(
        db, buffer, "view_candidate_annotation_flat", _CANDIDATE_FLAT_COLUMNS, _CANDIDATE_FLAT_UUID_COLUMNS, dive_ids
    )


# --------------------------------------------------------------------------
# Asset (file) staging helpers - copy, never move: these are live assets
# --------------------------------------------------------------------------


def _copy_asset(filepath: str, dest_dir: Path) -> None:
    source = resolve_asset_path(filepath)
    dest = dest_dir / filepath
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)


def stage_all_images(db: Session, dest_dir: Path) -> None:
    for image in db.execute(select(Image)).scalars():
        _copy_asset(image.filepath, dest_dir)


def stage_images_for_dive(db: Session, dive_id: int, dest_dir: Path) -> None:
    for image in db.execute(select(Image).where(Image.dive_id == dive_id)).scalars():
        _copy_asset(image.filepath, dest_dir)


def stage_helper_images(db: Session, dest_dir: Path, helper_image_ids: list[int] | None = None) -> None:
    """Copy helper image files into `dest_dir` (the zip staging root, not a `helper_images/`
    subfolder of it): `HelperImage.filepath` is always already prefixed with `helper_images/`
    (unlike `Image.filepath`, which is a free-form caller-chosen path), so nesting it under
    another `helper_images/` directory here would double it up.
    """
    stmt = select(HelperImage)
    if helper_image_ids is not None:
        stmt = stmt.where(HelperImage.id.in_(helper_image_ids))
    for helper_image in db.execute(stmt).scalars():
        _copy_asset(helper_image.filepath, dest_dir)


# --------------------------------------------------------------------------
# Zip orchestration
# --------------------------------------------------------------------------

_FULL_EXPORT_WRITERS = [
    ("users.csv", write_users_csv),
    ("labels.csv", write_labels_csv),
    ("cameras.csv", write_cameras_csv),
    ("regions.csv", write_regions_csv),
    ("dives.csv", write_dives_csv),
    ("images.csv", write_images_csv),
    ("image_pairs.csv", write_image_pairs_csv),
    ("candidate_pairs.csv", write_candidate_pairs_csv),
    ("point_annotations.csv", write_point_annotations_csv),
    ("candidate_annotations.csv", write_candidate_annotations_csv),
    ("fun_facts.csv", write_fun_facts_csv),
    ("helper_images.csv", write_helper_images_csv),
    ("seen_facts.csv", write_seen_facts_csv),
    ("quest_claims.csv", write_quest_claims_csv),
]


def _zip_directory(src_dir: Path, dest_zip_path: Path) -> None:
    with zipfile.ZipFile(dest_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(src_dir))


def build_full_dataset_zip(db: Session, dest_zip_path: Path, include_images: bool = True) -> None:
    """Every content table as CSV (ids dropped, FKs -> uuids).

    `include_images=True` (the default, used by the existing full-export
    endpoint - unchanged) also bundles images/ and helper_images/ with the
    actual asset files. `include_images=False` (used by the separate
    CSV-only endpoint) skips both folders entirely, for datasets where the
    asset files would make the zip impractically large (potentially hundreds
    of GB) and only the CSVs (a few MB at most) are needed.
    """
    with tempfile.TemporaryDirectory() as staging:
        staging_dir = Path(staging)
        for filename, writer_fn in _FULL_EXPORT_WRITERS:
            with (staging_dir / filename).open("w", newline="", encoding="utf-8") as fh:
                writer_fn(db, fh)
        if include_images:
            stage_all_images(db, staging_dir / "images")
            stage_helper_images(db, staging_dir)
        _zip_directory(staging_dir, dest_zip_path)


def build_fun_facts_zip(db: Session, dest_zip_path: Path) -> None:
    """fun_facts.csv + helper_images.csv + only the helper images an exported fact references."""
    with tempfile.TemporaryDirectory() as staging:
        staging_dir = Path(staging)
        referenced_ids = [
            row[0]
            for row in db.execute(select(FunFact.image_id).where(FunFact.image_id.is_not(None)).distinct()).all()
        ]
        with (staging_dir / "fun_facts.csv").open("w", newline="", encoding="utf-8") as fh:
            write_fun_facts_csv(db, fh)
        with (staging_dir / "helper_images.csv").open("w", newline="", encoding="utf-8") as fh:
            write_helper_images_csv(db, fh, helper_image_ids=referenced_ids)
        stage_helper_images(db, staging_dir, helper_image_ids=referenced_ids)
        _zip_directory(staging_dir, dest_zip_path)


def build_dive_zip(db: Session, dive_id: int, dest_zip_path: Path) -> None:
    """points.csv + candidates.csv (flat views, filtered to one dive) + all of that dive's images."""
    with tempfile.TemporaryDirectory() as staging:
        staging_dir = Path(staging)
        with (staging_dir / "points.csv").open("w", newline="", encoding="utf-8") as fh:
            write_point_annotation_flat_csv(db, fh, dive_ids=[dive_id])
        with (staging_dir / "candidates.csv").open("w", newline="", encoding="utf-8") as fh:
            write_candidate_annotation_flat_csv(db, fh, dive_ids=[dive_id])
        stage_images_for_dive(db, dive_id, staging_dir / "images")
        _zip_directory(staging_dir, dest_zip_path)
