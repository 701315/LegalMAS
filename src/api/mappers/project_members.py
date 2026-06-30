# src/api/mappers/project_members.py

"""
Мапперы для project members API.

Преобразуют dataclass-представления из ProjectRoleRepository
в Pydantic response schemas.
"""

from collections.abc import Iterable

from api.schemas.project_members import (
    AvailableProjectUserResponse,
    ProjectMemberResponse,
)
from db.repositories.project_role_repo import (
    AvailableProjectUserView,
    ProjectMemberView,
)


def map_member_to_response(member: ProjectMemberView) -> ProjectMemberResponse:
    return ProjectMemberResponse(
        member_id=member.member_id,
        user_id=member.user_id,
        email=member.email,
        full_name=member.full_name,
        system_role=member.system_role,
        role=member.role,
        created_at=member.created_at,
    )


def map_members_to_response(
    members: Iterable[ProjectMemberView],
) -> list[ProjectMemberResponse]:
    return [map_member_to_response(m) for m in members]


def map_available_user_to_response(
    user: AvailableProjectUserView,
) -> AvailableProjectUserResponse:
    return AvailableProjectUserResponse(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        system_role=user.system_role,
    )


def map_available_users_to_response(
    users: Iterable[AvailableProjectUserView],
) -> list[AvailableProjectUserResponse]:
    return [map_available_user_to_response(u) for u in users]


