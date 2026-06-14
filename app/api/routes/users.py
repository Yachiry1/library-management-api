from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead, summary="Get authenticated user")
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
