# src/core/anchors/models.py

"""
Pydantic-модель CheckAnchor — единый контракт привязки находки к месту.

Группы полей:
- semantic   — clause_uid/clause_ref/quoted_text/span_*/source_content_hash
- geometric  — page/layout_element_ids/bbox_union/segment_id
- provenance — anchor_method/anchor_confidence/anchor_validation_passed/anchor_diagnostics

Совместимые форматы (см. план, 1.5):
- layout_element_ids: "{lang}:{node_type}:{page}:{seq}"
- bbox_union:        [x0, top, x1, bottom]
- clause_uid:        effective_uid ("main_contract:7.3.2")
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class CheckAnchorMethod(StrEnum):
    """
    Метод получения anchor.

    Порядок в enum НЕ является порядком силы — используйте method_strength().
    """

    EXACT_SPAN = "exact_span"
    FUZZY_SPAN = "fuzzy_span"
    CLAUSE_AND_LAYOUT = "clause_and_layout"
    CLAUSE_ONLY = "clause_only"
    LAYOUT_ONLY = "layout_only"
    PAGE_ONLY = "page_only"
    RETRIEVAL_LEGACY = "retrieval_legacy"
    NONE = "none"


class CheckAnchor(BaseModel):
    """
    Один anchor находки. Может быть N на один CheckResult.

    Инварианты:
    - span_start/span_end задаются парой, оба >= 0, span_end >= span_start;
    - bbox_union: ровно 4 finite числа, x0 <= x1, top <= bottom;
    - anchor_confidence в [0.0, 1.0];
    - anchor_method=NONE → anchor_confidence == 0.0;
    - source_content_hash (если задан) — 64-символьный hex.
    """

    # Контракт: strict — новые поля добавляются явно, а не "прилетают" по ошибке.
    model_config = {"extra": "forbid"}

    # ── Semantic ──────────────────────────────────────────────────────────
    clause_uid: str | None = Field(
        default=None,
        description="Effective clause UID, e.g. 'main_contract:7.3.2'.",
    )
    clause_ref: str | None = Field(
        default=None,
        description="Human-readable clause ref, e.g. 'п. 7.3.2'.",
    )
    quoted_text: str | None = Field(
        default=None,
        description="Verbatim quote from source used as evidence.",
    )
    span_start: int | None = Field(
        default=None,
        description="Start char offset of quote within canonical source text.",
    )
    span_end: int | None = Field(
        default=None,
        description="End char offset (exclusive) of quote.",
    )
    source_content_hash: str | None = Field(
        default=None,
        description="SHA-256 hex of the canonical source text at extraction time.",
    )

    # ── Geometric ─────────────────────────────────────────────────────────
    page: int | None = Field(default=None, description="1-based page number.")
    layout_element_ids: list[str] = Field(
        default_factory=list,
        description="Layout element IDs covered by this anchor.",
    )
    bbox_union: list[float] | None = Field(
        default=None,
        description="Union bounding box [x0, top, x1, bottom] in PDF coords.",
    )
    segment_id: str | None = Field(
        default=None,
        description="Logical segment identifier within multi-doc file.",
    )

    # ── Provenance ────────────────────────────────────────────────────────
    anchor_method: CheckAnchorMethod = Field(
        description="How this anchor was obtained.",
    )
    anchor_confidence: float = Field(
        description="Confidence in [0.0, 1.0]; 0.0 iff anchor_method=NONE.",
    )
    anchor_validation_passed: bool = Field(
        default=False,
        description="True if round-trip validation of the anchor passed.",
    )
    anchor_diagnostics: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form diagnostics (matcher ratios, fallback reasons, ...).",
    )

    @field_validator("anchor_confidence")
    @classmethod
    def _v_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("anchor_confidence must be within [0.0, 1.0]")
        return v

    @field_validator("bbox_union")
    @classmethod
    def _v_bbox(cls, v: list[float] | None) -> list[float] | None:
        if v is None:
            return None
        if len(v) != 4:
            raise ValueError(
                "bbox_union must contain exactly 4 numbers [x0, top, x1, bottom]"
            )
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in v):
            raise ValueError("bbox_union must contain finite numbers only")
        x0, top, x1, bottom = v
        if x0 > x1:
            raise ValueError("bbox_union requires x0 <= x1")
        if top > bottom:
            raise ValueError("bbox_union requires top <= bottom")
        return [float(x) for x in v]

    @field_validator("source_content_hash")
    @classmethod
    def _v_hash(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) != 64:
            raise ValueError("source_content_hash must be 64 hex characters")
        try:
            int(v, 16)
        except ValueError as exc:
            raise ValueError("source_content_hash must be hexadecimal") from exc
        return v.lower()

    @field_validator("span_start", "span_end")
    @classmethod
    def _v_span_non_negative(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v < 0:
            raise ValueError("span offsets must be >= 0")
        return v

    @field_validator("page")
    @classmethod
    def _v_page_positive(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v < 1:
            raise ValueError("page must be >= 1")
        return v

    @model_validator(mode="after")
    def _v_cross_field(self) -> "CheckAnchor":
        if (self.span_start is None) != (self.span_end is None):
            raise ValueError("span_start and span_end must be set together")
        if self.span_start is not None and self.span_end is not None:
            if self.span_end < self.span_start:
                raise ValueError("span_end must be >= span_start")

        if self.anchor_method == CheckAnchorMethod.NONE and self.anchor_confidence != 0.0:
            raise ValueError("anchor_method=NONE requires anchor_confidence=0.0")

        return self

