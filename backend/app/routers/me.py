from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps.authz import AuthorizationContext, require_permission
from app.schemas.auth import ProfileResponse
from app.services.profile_service import get_profile

router = APIRouter(prefix="/api/v1", tags=["profile"])


@router.get("/me", response_model=ProfileResponse)
def me(
    caller: Annotated[
        AuthorizationContext,
        Depends(
            require_permission(
                "profile",
                "read",
                allowed_scopes=frozenset({"self", "any"}),
                allow_password_change_required=True,
            )
        ),
    ],
) -> ProfileResponse:
    return get_profile(caller)
