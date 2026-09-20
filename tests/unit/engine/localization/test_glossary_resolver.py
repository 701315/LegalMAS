"""
Unit tests for GlossaryResolver and LegalGlossaryRepository (Sprint 3.2).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.sql.selectable import Select

from db.models.legal_glossary import LegalGlossary
from db.repositories.legal_glossary_repo import LegalGlossaryRepository
from engine.localization.glossary_resolver import GlossaryResolver


# ── Helper for creating dummy model instances ───────────────────

def create_term(
    source_term: str,
    target_term: str,
    tenant_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> LegalGlossary:
    term = MagicMock(spec=LegalGlossary)
    term.id = uuid.uuid4()
    term.tenant_id = tenant_id
    term.source_locale = "ru"
    term.target_locale = "en"
    term.source_term = source_term
    term.target_term = target_term
    term.is_active = is_active
    return term


# ── Repository tests (Mocked DB session) ──────────────────────────


@pytest.mark.asyncio
async def test_repository_get_active_terms_sql_building() -> None:
    """Verify that the repository executes the correct SELECT statement."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    repo = LegalGlossaryRepository(mock_session)
    tenant_id = uuid.uuid4()

    # Trigger select
    await repo.get_active_terms(tenant_id, "ru", "en")

    # Assert that session.execute was called with a Select object
    assert mock_session.execute.call_count == 1
    stmt = mock_session.execute.call_args[0][0]
    assert isinstance(stmt, Select)


# ── Resolver tests (Merging & Overriding logic) ───────────────────


@pytest.mark.asyncio
async def test_resolver_without_tenant_returns_only_platform_terms() -> None:
    """If tenant_id is None, only platform-wide terms are loaded and returned."""
    platform_term = create_term("неустойка", "contractual penalty", tenant_id=None)

    mock_repo = MagicMock(spec=LegalGlossaryRepository)
    mock_repo.get_active_terms = AsyncMock(return_value=[platform_term])

    resolver = GlossaryResolver(mock_repo)
    result = await resolver.resolve_terms(None, "ru", "en")

    mock_repo.get_active_terms.assert_called_once_with(
        tenant_id=None,
        source_locale="ru",
        target_locale="en",
    )
    assert result == {"неустойка": "contractual penalty"}


@pytest.mark.asyncio
async def test_resolver_with_tenant_merges_without_conflicts() -> None:
    """Platform-wide and tenant terms are merged if their source_terms do not overlap."""
    tenant_id = uuid.uuid4()
    platform_term = create_term("неустойка", "contractual penalty", tenant_id=None)
    tenant_term = create_term("задаток", "earnest money", tenant_id=tenant_id)

    mock_repo = MagicMock(spec=LegalGlossaryRepository)
    mock_repo.get_active_terms = AsyncMock(return_value=[platform_term, tenant_term])

    resolver = GlossaryResolver(mock_repo)
    result = await resolver.resolve_terms(tenant_id, "ru", "en")

    assert result == {
        "неустойка": "contractual penalty",
        "задаток": "earnest money",
    }


@pytest.mark.asyncio
async def test_resolver_tenant_overrides_platform_term() -> None:
    """If same term is defined in platform and tenant, tenant-specific version takes precedence."""
    tenant_id = uuid.uuid4()
    platform_term = create_term("устав", "articles of association", tenant_id=None)
    tenant_term = create_term("устав", "charter", tenant_id=tenant_id)

    mock_repo = MagicMock(spec=LegalGlossaryRepository)
    mock_repo.get_active_terms = AsyncMock(return_value=[platform_term, tenant_term])

    resolver = GlossaryResolver(mock_repo)
    result = await resolver.resolve_terms(tenant_id, "ru", "en")

    # The result must contain 'charter', overriding 'articles of association'
    assert result == {"устав": "charter"}


@pytest.mark.asyncio
async def test_resolver_ignores_inactive_terms() -> None:
    """Terms with is_active=False must be excluded from final resolved dictionary."""
    tenant_id = uuid.uuid4()
    active_term = create_term("неустойка", "contractual penalty", tenant_id=None)
    inactive_term = create_term("задаток", "earnest money", tenant_id=tenant_id, is_active=False)

    mock_repo = MagicMock(spec=LegalGlossaryRepository)
    # Even if DB returned it (or cache), resolver must double-guard
    mock_repo.get_active_terms = AsyncMock(return_value=[active_term, inactive_term])

    resolver = GlossaryResolver(mock_repo)
    result = await resolver.resolve_terms(tenant_id, "ru", "en")

    assert result == {"неустойка": "contractual penalty"}
    assert "задаток" not in result
