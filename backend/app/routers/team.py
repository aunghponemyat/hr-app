from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.auth import AppSettings
from app.deps.authz import AuthorizationContext, require_permission
from app.schemas.admin import PageQuery, PageResponse, TeamMemberResponse
from app.schemas.attendance import TeamAttendanceQuery, TeamAttendanceResponse
from app.services.attendance_read_service import team_summary
from app.services.roster_service import list_team_members

router = APIRouter(prefix="/api/v1/team", tags=["team"])
Reader = Annotated[
    AuthorizationContext,
    Depends(require_permission("employee", "read", allowed_scopes=frozenset({"team", "any"}))),
]


@router.get("/members", response_model=PageResponse[TeamMemberResponse])
def members(
    caller: Reader, query: Annotated[PageQuery, Query()], settings: AppSettings
) -> PageResponse[TeamMemberResponse]:
    return list_team_members(caller, query, settings)


@router.get("/attendance", response_model=TeamAttendanceResponse)
def attendance(
    caller: Annotated[
        AuthorizationContext,
        Depends(
            require_permission("attendance", "read", allowed_scopes=frozenset({"team", "any"}))
        ),
    ],
    query: Annotated[TeamAttendanceQuery, Query()],
    settings: AppSettings,
) -> TeamAttendanceResponse:
    return team_summary(caller, query, settings)
