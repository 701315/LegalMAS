"""
Unit tests for InstructionLocalizationResolver (Sprint 4.4).

Tests the resolver's caching, priority logic, and fallback behavior
using mocked database sessions.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.instruction_localization_resolver import (
    InstructionLocalizationResolver,
)


def _make_row(
    key: str,
    locale: str,
    label: str,
    tenant_id: uuid.UUID | None = None,
) -> MagicMock:
    row = MagicMock()
    row.instruction_key = key
    row.locale = locale
    row.label = label
    row.tenant_id = tenant_id
    return row


@pytest.mark.asyncio  # <-- Добавлен маркер для строгого режима pytest-asyncio
class TestInstructionLocalizationResolver:
    """Verify resolution priority, caching, and fallback."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def tenant_id(self) -> uuid.UUID:
        return uuid.uuid4()

    async def test_platform_wide_resolution(
        self, mock_db: AsyncMock
    ) -> None:
        """Platform-wide entries resolve when no tenant override exists."""
        rows = [
            _make_row("dd_grid.field.generic.enum.yes", "en", "Yes"),
            _make_row("dd_grid.field.generic.enum.no", "en", "No"),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db.execute.return_value = mock_result

        resolver = InstructionLocalizationResolver(
            db=mock_db, tenant_id=None, locale="en"
        )
        result = await resolver.resolve("dd_grid.field.generic.enum.yes")

        assert result == "Yes"

    async def test_tenant_override_takes_precedence(
        self, mock_db: AsyncMock, tenant_id: uuid.UUID
    ) -> None:
        """Tenant-specific entry overrides platform-wide for the same key."""
        rows = [
            _make_row("dd_grid.field.generic.enum.yes", "en", "Yes"),
            _make_row(
                "dd_grid.field.generic.enum.yes", "en", "Affirmative",
                tenant_id=tenant_id,
            ),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db.execute.return_value = mock_result

        resolver = InstructionLocalizationResolver(
            db=mock_db, tenant_id=tenant_id, locale="en"
        )
        result = await resolver.resolve("dd_grid.field.generic.enum.yes")

        assert result == "Affirmative"

    async def test_fallback_when_key_missing(
        self, mock_db: AsyncMock
    ) -> None:
        """Returns fallback string when key is not in DB."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resolver = InstructionLocalizationResolver(
            db=mock_db, tenant_id=None, locale="en"
        )
        result = await resolver.resolve(
            "dd_grid.field.generic.enum.yes", fallback="Да"
        )

        assert result == "Да"

    async def test_returns_key_itself_when_no_fallback(
        self, mock_db: AsyncMock
    ) -> None:
        """Returns the key string when no fallback provided and key missing."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resolver = InstructionLocalizationResolver(
            db=mock_db, tenant_id=None, locale="en"
        )
        result = await resolver.resolve("dd_grid.system.unknown")

        assert result == "dd_grid.system.unknown"

    async def test_cache_prevents_duplicate_queries(
        self, mock_db: AsyncMock
    ) -> None:
        """Second resolve() call must NOT trigger another DB query."""
        rows = [_make_row("dd_grid.system.ungrouped", "en", "Other Checks")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db.execute.return_value = mock_result

        resolver = InstructionLocalizationResolver(
            db=mock_db, tenant_id=None, locale="en"
        )

        await resolver.resolve("dd_grid.system.ungrouped")
        await resolver.resolve("dd_grid.system.ungrouped")

        assert mock_db.execute.call_count == 1

    async def test_resolve_many_batch(
        self, mock_db: AsyncMock
    ) -> None:
        """resolve_many returns dict for all requested keys."""
        rows = [
            _make_row("dd_grid.field.generic.enum.yes", "en", "Yes"),
            _make_row("dd_grid.field.generic.enum.no", "en", "No"),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        mock_db.execute.return_value = mock_result

        resolver = InstructionLocalizationResolver(
            db=mock_db, tenant_id=None, locale="en"
        )
        result = await resolver.resolve_many(
            ["dd_grid.field.generic.enum.yes", "dd_grid.field.generic.enum.no"],
            fallback_map={"dd_grid.field.generic.enum.missing": "Missing"},
        )

        assert result == {
            "dd_grid.field.generic.enum.yes": "Yes",
            "dd_grid.field.generic.enum.no": "No",
        }

    async def test_locale_case_normalization(
        self, mock_db: AsyncMock
    ) -> None:
        """Locale is normalized to lowercase."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resolver = InstructionLocalizationResolver(
            db=mock_db, tenant_id=None, locale="  EN  "
        )
        await resolver.load_all()

        assert resolver._locale == "en"

        