# src/db/models/tenant_result_locale_policy.py

"""
TenantResultLocalePolicy model.

Defines enterprise-level localization rules for translated check results.
Controls which output locales are allowed and whether LLM-based translations
are enabled for a given tenant.
"""

from __future__ import annotations

import uuid
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class TenantResultLocalePolicy(Base):
    """
    Tenant result locale policy.

    Controls target result localization constraints for an entire tenant.

    Properties:
    - tenant_id: Target tenant (FK tenants.id, Cascade, Unique)
    - allowed_locales: Array of BCP 47 codes (e.g. ['en', 'ru']). Empty list
      means no specific restrictions (all registry-supported locales allowed).
    - is_translation_enabled: If False, LLM-based translation requests will be blocked.
      Users can only read results in the canonical Run.analysis_language.
    - restrict_to_allowed: If True, explicitly enforce allowed_locales validation.
    """

    __tablename__ = "tenant_result_locale_policies"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
        comment="Tenant owning this policy. One policy per tenant constraint.",
    )

    allowed_locales: Mapped[list[str]] = mapped_column(
        ARRAY(String(10)),
        nullable=False,
        default=list,
        server_default="{}",
        comment="List of allowed BCP 47 output locales. Empty means all registry locales are allowed.",
    )

    is_translation_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Enables or disables LLM translation pipeline for the entire tenant.",
    )

    restrict_to_allowed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="If True, strictly enforce 422/403 for locales not in allowed_locales.",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_result_locale_policies_tenant"),
    )


    