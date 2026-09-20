# tests/unit/models/test_user_output_locale.py

"""
Unit tests for User model default_output_locale field (Sprint 2.4 / Invariant #5).
"""

import uuid
from db.models.user import User


def test_user_model_has_output_locale_fields() -> None:
    """Verify that User model has both ui_locale and default_output_locale as separate axes."""
    tenant_id = uuid.uuid4()
    user = User(
        tenant_id=tenant_id,
        email="lawyer@example.com",
        password_hash="hashed_pw",
        full_name="Senior Associate",
        ui_locale="ru",                # UI axis (Russian UI)
        default_output_locale="en",    # Results axis (English results)
    )

    assert user.ui_locale == "ru"
    assert user.default_output_locale == "en"
    assert user.ui_locale != user.default_output_locale


def test_user_model_default_output_locale_nullable() -> None:
    """Verify default_output_locale defaults to None."""
    tenant_id = uuid.uuid4()
    user = User(
        tenant_id=tenant_id,
        email="lawyer2@example.com",
        password_hash="hashed_pw",
    )

    assert user.default_output_locale is None
    assert user.ui_locale is None


    