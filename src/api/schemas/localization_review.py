"""
Pydantic schemas for translation review endpoints (Sprint 6.2).

Follows the same patterns as api/schemas/qc.py:
- strict field validation and normalization
- explicit allowed values
- immutable response DTOs
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ReviewApproveRequest(BaseModel):
    """Request body for approving a localized presentation."""

    comment: str | None = Field(default=None, max_length=4000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ReviewRejectRequest(BaseModel):
    """Request body for rejecting a localized presentation. Comment is mandatory."""

    comment: str = Field(min_length=1, max_length=4000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("comment must not be empty")
        return normalized


class ReviewEditRequest(BaseModel):
    """Request body for applying a human override to a localized presentation."""

    localized_check_name: str | None = Field(default=None, max_length=500)
    display_text: str | None = Field(default=None, max_length=50000)
    review_message: str | None = Field(default=None, max_length=50000)
    dd_request_text: str | None = Field(default=None, max_length=50000)
    comment: str | None = Field(default=None, max_length=4000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ReviewResponse(BaseModel):
    """Response for any review action (approve / reject / edit / reset)."""

    presentation_id: str
    translation_status: str
    locale: str
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    review_comment: str | None = None
    has_human_override: bool = False
    has_original_snapshot: bool = False
