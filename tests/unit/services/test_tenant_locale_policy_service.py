# tests/unit/services/test_tenant_locale_policy_service.py

"""
Unit tests for tenant locale policy validation service (Sprint 2.6).
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.tenant_locale_policy_service import (
    LocalePolicyViolationError,
    is_translation_allowed,
    validate_locale_for_tenant,
)


TENANT_ID = uuid.uuid4()


def _make_db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    return db


def _run(coro):
    return asyncio.run(coro)


class TestValidateLocaleForTenant:
    def test_valid_locale_no_policy(self):
        """No tenant policy → all registry locales allowed."""
        db = _make_db()

        with patch(
            "services.tenant_locale_policy_service.TenantLocalePolicyRepository"
        ) as repo_cls:
            repo = MagicMock()
            repo.get_by_tenant_id = AsyncMock(return_value=None)
            repo_cls.return_value = repo

            result = _run(validate_locale_for_tenant(db, TENANT_ID, "en"))

        assert result == "en"

    def test_valid_locale_with_permissive_policy(self):
        """Policy exists, locale in allowed_locales → allowed."""
        db = _make_db()
        policy = SimpleNamespace(
            tenant_id=TENANT_ID,
            allowed_locales=["en", "ru"],
            is_translation_enabled=True,
            restrict_to_allowed=True,
        )

        with patch(
            "services.tenant_locale_policy_service.TenantLocalePolicyRepository"
        ) as repo_cls:
            repo = MagicMock()
            repo.get_by_tenant_id = AsyncMock(return_value=policy)
            repo_cls.return_value = repo

            result = _run(validate_locale_for_tenant(db, TENANT_ID, "ru"))

        assert result == "ru"

    def test_locale_blocked_by_tenant_policy(self):
        """Policy restricts to ['en'], requesting 'ru' → raises."""
        db = _make_db()
        policy = SimpleNamespace(
            tenant_id=TENANT_ID,
            allowed_locales=["en"],
            is_translation_enabled=True,
            restrict_to_allowed=True,
        )

        with patch(
            "services.tenant_locale_policy_service.TenantLocalePolicyRepository"
        ) as repo_cls:
            repo = MagicMock()
            repo.get_by_tenant_id = AsyncMock(return_value=policy)
            repo_cls.return_value = repo

            with pytest.raises(LocalePolicyViolationError) as exc_info:
                _run(validate_locale_for_tenant(db, TENANT_ID, "ru"))

        assert exc_info.value.reason == "tenant_policy_restriction"
        assert exc_info.value.locale == "ru"

    def test_unsupported_locale_rejected(self):
        """Locale not in result_locales.json → raises regardless of policy."""
        db = _make_db()

        with patch(
            "services.tenant_locale_policy_service.TenantLocalePolicyRepository"
        ) as repo_cls:
            repo = MagicMock()
            repo.get_by_tenant_id = AsyncMock(return_value=None)
            repo_cls.return_value = repo

            with pytest.raises(LocalePolicyViolationError) as exc_info:
                _run(validate_locale_for_tenant(db, TENANT_ID, "xx"))

        assert exc_info.value.reason == "unsupported_locale"

    def test_empty_allowed_locales_means_all_allowed(self):
        """Policy with empty allowed_locales → no restriction."""
        db = _make_db()
        policy = SimpleNamespace(
            tenant_id=TENANT_ID,
            allowed_locales=[],
            is_translation_enabled=True,
            restrict_to_allowed=True,
        )

        with patch(
            "services.tenant_locale_policy_service.TenantLocalePolicyRepository"
        ) as repo_cls:
            repo = MagicMock()
            repo.get_by_tenant_id = AsyncMock(return_value=policy)
            repo_cls.return_value = repo

            result = _run(validate_locale_for_tenant(db, TENANT_ID, "ru"))

        assert result == "ru"


class TestIsTranslationAllowed:
    def test_no_policy_allows_translation(self):
        db = _make_db()

        with patch(
            "services.tenant_locale_policy_service.TenantLocalePolicyRepository"
        ) as repo_cls:
            repo = MagicMock()
            repo.get_by_tenant_id = AsyncMock(return_value=None)
            repo_cls.return_value = repo

            assert _run(is_translation_allowed(db, TENANT_ID)) is True

    def test_policy_enabled(self):
        db = _make_db()
        policy = SimpleNamespace(is_translation_enabled=True)

        with patch(
            "services.tenant_locale_policy_service.TenantLocalePolicyRepository"
        ) as repo_cls:
            repo = MagicMock()
            repo.get_by_tenant_id = AsyncMock(return_value=policy)
            repo_cls.return_value = repo

            assert _run(is_translation_allowed(db, TENANT_ID)) is True

    def test_policy_disabled(self):
        db = _make_db()
        policy = SimpleNamespace(is_translation_enabled=False)

        with patch(
            "services.tenant_locale_policy_service.TenantLocalePolicyRepository"
        ) as repo_cls:
            repo = MagicMock()
            repo.get_by_tenant_id = AsyncMock(return_value=policy)
            repo_cls.return_value = repo

            assert _run(is_translation_allowed(db, TENANT_ID)) is False


            