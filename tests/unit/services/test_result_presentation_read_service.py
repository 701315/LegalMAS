# tests/unit/services/test_result_presentation_read_service.py

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.result_presentation_read_service import (
    resolve_presentation_locale,
)

TENANT_ID = uuid.uuid4()


def _make_db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    return db


def _run(coro):
    return asyncio.run(coro)


class TestResolvePresentationLocale6Levels:
    def test_level_1_explicit_highest_priority(self):
        """Level 1: Explicit parameter overrides everything."""
        db = _make_db()
        with patch("services.result_presentation_read_service.validate_locale_for_tenant", new=AsyncMock(return_value="ru")):
            result = _run(resolve_presentation_locale(
                db,
                tenant_id=TENANT_ID,
                explicit_locale="ru",
                user_default_output_locale="en",
                user_ui_locale="en",
                deal_primary_language="en",
                run_analysis_language="en",
            ))
        assert result == "ru"

    def test_level_1_explicit_fails_raises_value_error(self):
        """Level 1 failure raises ValueError (propagates as 422 in API)."""
        db = _make_db()
        from services.tenant_locale_policy_service import LocalePolicyViolationError
        mock_err = LocalePolicyViolationError("Blocked", reason="unsupported_locale")
        
        with patch("services.result_presentation_read_service.validate_locale_for_tenant", new=AsyncMock(side_effect=mock_err)):
            with pytest.raises(ValueError, match="Blocked"):
                _run(resolve_presentation_locale(
                    db,
                    tenant_id=TENANT_ID,
                    explicit_locale="invalid",
                ))

    def test_level_2_user_default_output_locale(self):
        """Level 2: User-specific result locale preference overrides UI locale and below."""
        db = _make_db()
        
        # Мокаем нормализацию: возвращаем кандидата, если он поддерживается
        async def mock_norm(d, t_id, val):
            return val if val in ("ru", "en") else None

        with patch("services.result_presentation_read_service._normalize_and_validate_fallback", new=AsyncMock(side_effect=mock_norm)):
            result = _run(resolve_presentation_locale(
                db,
                tenant_id=TENANT_ID,
                explicit_locale=None,
                user_default_output_locale="ru",
                user_ui_locale="en",
                deal_primary_language="en",
                run_analysis_language="en",
            ))
        assert result == "ru"

    def test_level_3_user_ui_locale(self):
        """Level 3: User's UI locale is used if Level 2 is missing/invalid."""
        db = _make_db()

        async def mock_norm(d, t_id, val):
            # Симулируем, что "invalid" не поддерживается, а "ru" поддерживается
            return val if val == "ru" else None

        with patch("services.result_presentation_read_service._normalize_and_validate_fallback", new=AsyncMock(side_effect=mock_norm)):
            result = _run(resolve_presentation_locale(
                db,
                tenant_id=TENANT_ID,
                explicit_locale=None,
                user_default_output_locale="invalid",
                user_ui_locale="ru",
                deal_primary_language="en",
                run_analysis_language="en",
            ))
        assert result == "ru"

    def test_level_4_deal_primary_language(self):
        """Level 4: Deal primary language is used when user prefs are missing/invalid."""
        db = _make_db()

        async def mock_norm(d, t_id, val):
            return val if val == "ru" else None

        with patch("services.result_presentation_read_service._normalize_and_validate_fallback", new=AsyncMock(side_effect=mock_norm)):
            result = _run(resolve_presentation_locale(
                db,
                tenant_id=TENANT_ID,
                explicit_locale=None,
                user_default_output_locale=None,
                user_ui_locale="invalid",
                deal_primary_language="ru",
                run_analysis_language="en",
            ))
        assert result == "ru"

    def test_level_5_run_analysis_language(self):
        """Level 5: Run analysis language is used when deal primary language is missing/invalid."""
        db = _make_db()

        async def mock_norm(d, t_id, val):
            return val if val == "ru" else None

        with patch("services.result_presentation_read_service._normalize_and_validate_fallback", new=AsyncMock(side_effect=mock_norm)):
            result = _run(resolve_presentation_locale(
                db,
                tenant_id=TENANT_ID,
                explicit_locale=None,
                user_default_output_locale=None,
                user_ui_locale=None,
                deal_primary_language="invalid",
                run_analysis_language="ru",
            ))
        assert result == "ru"

    def test_level_6_system_default_fallback(self):
        """Level 6: System default is used when everything else is missing/invalid."""
        db = _make_db()

        async def mock_norm(d, t_id, val):
            # 'en' поддерживается системой
            return val if val == "en" else None

        with patch("services.result_presentation_read_service.get_default_output_locale", return_value="en"), \
             patch("services.result_presentation_read_service._normalize_and_validate_fallback", new=AsyncMock(side_effect=mock_norm)):
            result = _run(resolve_presentation_locale(
                db,
                tenant_id=TENANT_ID,
                explicit_locale=None,
                user_default_output_locale=None,
                user_ui_locale=None,
                deal_primary_language=None,
                run_analysis_language=None,
            ))
        assert result == "en"


        