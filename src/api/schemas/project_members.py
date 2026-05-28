# src/api/schemas/project_members.py

"""
Pydantic схемы для управления участниками проекта (project members).

Используются в API-слое для:
- приёма данных при создании/обновлении участника проекта;
- возврата участника в ответах (ORM → Pydantic через from_attributes);
- типизации роли участника через ProjectRole из слоя БД.

Модели:
- ProjectMemberBase — общие поля участника (name, login, role);
- ProjectMemberResponse — модель ответа API с member_id и created_at;
- CreateProjectMember — payload для создания участника, включает password;
- UpdateProjectMember — частичное обновление участника (все поля опциональны).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from db.repositories.project_role_repo import ProjectRole


class ProjectMemberBase(BaseModel):
    name: str
    login: str
    role: ProjectRole


class ProjectMemberResponse(ProjectMemberBase):
    member_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True  # для model_validate(ORM)


class CreateProjectMember(ProjectMemberBase):
    password: str  # пока просто принимаем, позже свяжем с реальным user


class UpdateProjectMember(BaseModel):
    name: str | None = None
    login: str | None = None
    password: str | None = None
    role: ProjectRole | None = None
