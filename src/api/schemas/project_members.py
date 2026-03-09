# src/api/schemas/project_members.py
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
