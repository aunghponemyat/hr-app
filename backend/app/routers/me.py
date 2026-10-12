from fastapi import APIRouter

from app.deps.auth import CurrentEmployee
from app.schemas.auth import ProfileResponse
from app.services.profile_service import get_profile

router = APIRouter(prefix="/api/v1", tags=["profile"])


@router.get("/me", response_model=ProfileResponse)
def me(employee: CurrentEmployee) -> ProfileResponse:
    return get_profile(employee)
