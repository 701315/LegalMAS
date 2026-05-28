# src/api/mappers/project_members.py

"""
Мапперы для преобразования ORM-модели участника проекта в API-схемы.

Задачи этого модуля:
- разорвать связь между DealMember (SQLAlchemy) и REST API;
- отразить внутреннее поле id во внешнее member_id;
- обеспечить единый формат ответа для списка, создания и обновления участника.

Где используется:
- в эндпоинтах project_members.py для всех операций с участниками проекта.
"""

from collections.abc import Iterable

from api.schemas.project_members import ProjectMemberResponse
from db.models.deal_member import DealMember


def map_member_to_response(member: DealMember) -> ProjectMemberResponse:
    return ProjectMemberResponse(
        member_id=member.id,
        name=member.name,
        login=member.login,
        role=member.role,
        created_at=member.created_at,
    )


def map_members_to_response(
    members: Iterable[DealMember],
) -> list[ProjectMemberResponse]:
    return [map_member_to_response(m) for m in members]
