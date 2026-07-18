# tests/unit/test_deal_language_service.py

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from services import deal_language_service


@dataclass
class _FakeDeal:
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    languages: list[str] | None = None
    primary_language: str | None = None


class _FakeDealRepository:
    def __init__(self, deal: _FakeDeal | None):
        self._deal = deal
        self.update_languages_calls: list[dict] = []
        self.update_primary_language_calls: list[dict] = []

    async def internal_unsafe_get_by_id(self, deal_id: uuid.UUID):
        if self._deal is None:
            return None
        if self._deal.id != deal_id:
            return None
        return self._deal

    async def update_languages(
        self,
        *,
        deal_id: uuid.UUID,
        tenant_id: uuid.UUID,
        languages: list[str],
    ) -> None:
        self.update_languages_calls.append(
            {
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "languages": languages,
            }
        )

    async def update_primary_language(
        self,
        *,
        deal_id: uuid.UUID,
        tenant_id: uuid.UUID,
        primary_language: str | None,
    ) -> None:
        self.update_primary_language_calls.append(
            {
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "primary_language": primary_language,
            }
        )


@pytest.mark.asyncio
async def test_update_deal_languages_passes_tenant_id_to_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    deal_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    fake_deal = _FakeDeal(
        id=deal_id,
        tenant_id=tenant_id,
        languages=None,
        primary_language=None,
    )
    fake_repo = _FakeDealRepository(fake_deal)

    monkeypatch.setattr(
        deal_language_service,
        "DealRepository",
        lambda db: fake_repo,
    )

    await deal_language_service.update_deal_languages(
        db=object(),
        deal_id=deal_id,
        new_languages=[" RU "],
    )

    assert fake_repo.update_languages_calls == [
        {
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "languages": ["ru"],
        }
    ]
    assert fake_repo.update_primary_language_calls == [
        {
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "primary_language": "ru",
        }
    ]


@pytest.mark.asyncio
async def test_update_deal_languages_does_not_write_when_nothing_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deal_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    fake_deal = _FakeDeal(
        id=deal_id,
        tenant_id=tenant_id,
        languages=["ru"],
        primary_language="ru",
    )
    fake_repo = _FakeDealRepository(fake_deal)

    monkeypatch.setattr(
        deal_language_service,
        "DealRepository",
        lambda db: fake_repo,
    )

    await deal_language_service.update_deal_languages(
        db=object(),
        deal_id=deal_id,
        new_languages=["RU"],
    )

    assert fake_repo.update_languages_calls == []
    assert fake_repo.update_primary_language_calls == []


@pytest.mark.asyncio
async def test_update_deal_languages_returns_silently_when_deal_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_repo = _FakeDealRepository(None)

    monkeypatch.setattr(
        deal_language_service,
        "DealRepository",
        lambda db: fake_repo,
    )

    await deal_language_service.update_deal_languages(
        db=object(),
        deal_id=uuid.uuid4(),
        new_languages=["ru"],
    )

    assert fake_repo.update_languages_calls == []
    assert fake_repo.update_primary_language_calls == []


@pytest.mark.asyncio
async def test_update_deal_languages_keeps_existing_primary_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deal_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    fake_deal = _FakeDeal(
        id=deal_id,
        tenant_id=tenant_id,
        languages=["ru"],
        primary_language="ru",
    )
    fake_repo = _FakeDealRepository(fake_deal)

    monkeypatch.setattr(
        deal_language_service,
        "DealRepository",
        lambda db: fake_repo,
    )

    await deal_language_service.update_deal_languages(
        db=object(),
        deal_id=deal_id,
        new_languages=["en"],
    )

    assert fake_repo.update_languages_calls == [
        {
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "languages": ["en", "ru"],
        }
    ]
    assert fake_repo.update_primary_language_calls == []


    