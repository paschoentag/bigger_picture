from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src import config
from src.api.deps import require_current_user
from src.constants import Role
from src.db import get_db
from src.models.admin import UserCreateRequest, UserUpdateRequest
from src.models.auth import UserResponse
from src.password_auth.hashing import hash_password
from src.password_auth.store import has_password, set_password_hash
from src.schema.users import User
from src.util import apply_partial_update, now_ms

router = APIRouter()


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        uuid=UUID(bytes=user.uuid),
        username=user.username,
        role=Role(user.role),
        expert_level=user.expert_level,
        exp=user.exp,
        created_at=user.created_at,
    )


@router.post(
    "/create",
    response_model=UserResponse,
    status_code=201,
    summary="Create User",
    description="""
Create a new user with the given uuid, username, and role. Requires the admin role.

expert_level is read-only, derived from exp; any value supplied for it is ignored and the new user always starts at expert_level 0.

`password` is required for every new user, regardless of role.

Fails with 409 if the uuid or username (case-insensitively) is already taken.
""",
)
def create_user(payload: UserCreateRequest, request: Request, db: Session = Depends(get_db)):
    admin = require_current_user(request)

    user = User(
        uuid=payload.uuid.bytes,
        created_at=now_ms(),
        created_by=admin.id,
        username=payload.username,
        role=str(payload.role),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or uuid already taken")
    db.refresh(user)

    set_password_hash(config.AUTH_DATABASE_PATH, user.uuid, hash_password(payload.password))

    return _to_response(user)


@router.post(
    "/update",
    response_model=UserResponse,
    summary="Update User",
    description="""
Partially update an existing user, identified by uuid. Requires the admin role.

Only the fields supplied in the request are changed; omitted fields are left as-is. Sending an explicit null for username or role is also a no-op. expert_level is read-only, derived from exp; any value supplied for it (null or not) is ignored.

`password` sets/replaces the stored credential, for any role. It is required (422) if the resulting role is scientist/admin and the account has no credential yet (first-time promotion). Changing role never touches an existing stored credential on its own - this is the mechanism for an admin to unlock a legacy annotator account by setting its first password.

Fails with 404 if the uuid is not found, or 409 if the new username is already taken (case-insensitively).
""",
)
def update_user(payload: UserUpdateRequest, request: Request, db: Session = Depends(get_db)):
    require_current_user(request)

    user = db.execute(select(User).where(User.uuid == payload.uuid.bytes)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    updates = apply_partial_update(
        payload,
        nullable_columns=set(),
        field_map={"username": "username", "role": "role"},
    )
    if "role" in updates:
        updates["role"] = str(updates["role"])

    final_role = updates.get("role", user.role)
    password_requested = "password" in payload.model_fields_set and payload.password is not None

    if (
        final_role != Role.ANNOTATOR
        and not password_requested
        and not has_password(config.AUTH_DATABASE_PATH, user.uuid)
    ):
        raise HTTPException(
            status_code=422,
            detail="password is required when promoting to scientist/admin for the first time",
        )

    for column, value in updates.items():
        setattr(user, column, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already taken")
    db.refresh(user)

    if password_requested:
        set_password_hash(config.AUTH_DATABASE_PATH, user.uuid, hash_password(payload.password))

    return _to_response(user)
