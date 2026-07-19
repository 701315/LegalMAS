# src/api/schemas/instructions.py

"""
Pydantic-схемы для эндпоинта effective-instruction.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EffectiveCheckItem(BaseModel):
    check_id: str | None = None
    name: str | None = None
    severity: str | None = None
    description: str | None = None
    detector_type: str | None = None
    conditional: bool = False
    origin: Literal["global", "document_type"]


class EffectiveInstructionResponse(BaseModel):
    run_id: str
    document_id: str
    doc_type: str | None = None
    triggers: list[str] = []
    playbook_version_id: str
    global_checks: list[EffectiveCheckItem] = []
    doc_type_instruction_version_id: str | None = None
    doc_type_checks: list[EffectiveCheckItem] = []
    is_frozen_snapshot: bool = False

