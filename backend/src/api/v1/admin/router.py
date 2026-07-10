from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.v1.admin.backups import router as backups_router
from src.api.v1.admin.fun_facts import router as fun_facts_router
from src.api.v1.admin.users import router as users_router
from src.db import get_db
from src.models.admin import UserListResponse, UserSummary
from src.schema.users import User

router = APIRouter()

router.include_router(users_router, prefix="/users")
router.include_router(backups_router, prefix="/backups")
router.include_router(fun_facts_router, prefix="/fun-facts")


@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List Users",
    description="""
Return a summary of every user in the system. Requires the admin role.
""",
)
def list_users(db: Session = Depends(get_db)):
    users = db.execute(select(User)).scalars().all()
    return UserListResponse(
        users=[
            UserSummary(
                uuid=UUID(bytes=user.uuid),
                username=user.username,
                role=user.role,
                expert_level=user.expert_level,
                exp=user.exp,
            )
            for user in users
        ]
    )
