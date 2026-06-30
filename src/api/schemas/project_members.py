# src/api/schemas/project_members.py

"""
Pydantic-схемы для управления участниками проекта.

Чистая модель:
- пользователь создаётся отдельно через admin panel;
- project members API только назначает существующего пользователя
  в проект и задаёт ему project role.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from core.roles import ProjectRole


class ProjectMemberResponse(BaseModel):
    """
    Участник проекта с данными пользователя и project role.
    """

    member_id: UUID
    user_id: UUID
    email: str
    full_name: str | None
    system_role: str
    role: ProjectRole
    created_at: datetime


class AvailableProjectUserResponse(BaseModel):
    """
    Пользователь tenant'а, которого можно добавить в проект.
    """

    user_id: UUID
    email: str
    full_name: str | None
    system_role: str


class CreateProjectMember(BaseModel):
    """
    Назначить существующего пользователя в проект.
    """

    user_id: UUID
    role: ProjectRole


class UpdateProjectMember(BaseModel):
    """
    Изменить только роль участника в проекте.
    """

    role: ProjectRole