from __future__ import annotations

import uuid

import pytest

import services.document_language_pipeline as dlp
from services.layout_language_filter import filter_layout_to_language


def _make_decision(
    *,
    target_language: str = "ru",
    is_multilingual: bool = False,
    route: str = "proceed",
    quarantine_reason: str | None = None,
) -> dlp.DocumentLanguageDecision:
    """
    Создать DocumentLanguageDecision для тестов по новому контракту.

    В новой модели основной флаг — is_multilingual.
    is_bilingual остаётся только как backward-compatible property alias.
    """
    detected = [target_language, "en"] if is_multilingual else [target_language]
    ratios = (
        {target_language: 0.55, "en": 0.45}
        if is_multilingual
        else {target_language: 0.92}
    )

    return dlp.DocumentLanguageDecision(
        detected_languages=detected,
        target_language=target_language,
        is_multilingual=is_multilingual,
        language_ratios=ratios,
        target_language_ratio=ratios[target_language],
        route=route,
        quarantine_reason=quarantine_reason,
        deal_primary_language_before=target_language,
        deal_languages_before=detected,
        deal_primary_language_after=target_language,
        deal_languages_after=detected,
        requires_user_selection=False,
        pipeline_mode="PRIMARY_ONLY_DOWNSTREAM",
    )


@pytest.mark.asyncio
async def test_build_primary_language_layout_applies_filter_for_non_multilingual_document(monkeypatch):
    """
    Монолингвальный документ должен идти в simple filter path.
    """
    decision = _make_decision(is_multilingual=False)

    async def fake_analyze_document_languages(*args, **kwargs):
        return decision

    seen: dict[str, object] = {}

    def fake_filter_layout_to_language(layout, target_language, context=None):
        seen["called"] = True
        seen["target_language"] = target_language
        seen["context"] = context
        return {
            "document_id": layout.get("document_id"),
            "document_version_id": layout.get("document_version_id"),
            "elements": [
                {
                    "element_id": "el-1",
                    "page": 1,
                    "bbox": [0, 0, 100, 10],
                    "text": "1 ДОГОВОР ПОСТАВКИ",
                    "type": "heading",
                }
            ],
            "tables": [],
            "excluded_element_ids": [],
            "filter_decisions": [],
            "metadata": {
                "language_filter": {
                    "structural_filter_used": False,
                    "degraded": False,
                    "elements_after": 1,
                }
            },
        }

    monkeypatch.setattr(dlp, "analyze_document_languages", fake_analyze_document_languages)
    monkeypatch.setattr(dlp, "filter_layout_to_language", fake_filter_layout_to_language)

    raw_layout = {
        "document_id": "doc-1",
        "document_version_id": "ver-1",
        "elements": [
            {
                "element_id": "el-1",
                "page": 1,
                "bbox": [0, 0, 100, 10],
                "text": "1 ДОГОВОР ПОСТАВКИ / SALE AGREEMENT",
                "type": "heading",
            }
        ],
        "tables": [],
        "metadata": {},
    }

    result = await dlp.build_primary_language_layout(
        db=None,
        deal_id=uuid.uuid4(),
        tenant_id="tenant-1",
        document_id="doc-1",
        layout=raw_layout,
        target_language="ru",
    )

    assert result.should_quarantine is False
    assert seen.get("called") is True
    assert seen["target_language"] == "ru"
    assert seen["context"]["is_multilingual"] is False

    assert len(result.primary_layout["elements"]) == 1
    assert result.primary_layout["elements"][0]["text"] == "1 ДОГОВОР ПОСТАВКИ"

    meta = result.primary_layout["metadata"]
    assert meta["language_pipeline"]["fallback_used"] is False
    assert meta["language_pipeline"]["is_multilingual"] is False
    # backward compat alias сохраняется в metadata
    assert meta["language_pipeline"]["is_bilingual"] is False
    assert meta["language_filter"]["fallback_used"] is False
    assert meta["language_filter"]["structural_filter_used"] is False


@pytest.mark.asyncio
async def test_build_primary_language_layout_non_multilingual_empty_filter_falls_back_to_raw(monkeypatch):
    """
    Если simple filter неожиданно вернул пустой layout для монолингвального документа,
    pipeline должен сделать безопасный fallback на raw layout.
    """
    decision = _make_decision(is_multilingual=False)

    async def fake_analyze_document_languages(*args, **kwargs):
        return decision

    def fake_filter_layout_to_language(layout, target_language, context=None):
        return {
            "document_id": layout.get("document_id"),
            "document_version_id": layout.get("document_version_id"),
            "elements": [],
            "tables": [],
            "excluded_element_ids": [],
            "filter_decisions": [],
            "metadata": {
                "language_filter": {
                    "structural_filter_used": False,
                    "degraded": True,
                    "degraded_reason": "no_elements_after_filter",
                }
            },
        }

    monkeypatch.setattr(dlp, "analyze_document_languages", fake_analyze_document_languages)
    monkeypatch.setattr(dlp, "filter_layout_to_language", fake_filter_layout_to_language)

    raw_layout = {
        "document_id": "doc-1",
        "document_version_id": "ver-1",
        "elements": [
            {
                "element_id": "el-1",
                "page": 1,
                "bbox": [0, 0, 100, 10],
                "text": "1 ДОГОВОР ПОСТАВКИ",
                "type": "heading",
            }
        ],
        "tables": [],
        "metadata": {},
    }

    result = await dlp.build_primary_language_layout(
        db=None,
        deal_id=uuid.uuid4(),
        tenant_id="tenant-1",
        document_id="doc-1",
        layout=raw_layout,
        target_language="ru",
    )

    assert result.should_quarantine is False
    assert result.primary_layout["elements"] == raw_layout["elements"]

    meta = result.primary_layout["metadata"]
    assert meta["language_pipeline"]["fallback_used"] is True
    assert meta["language_filter"]["fallback_used"] is True
    assert meta["language_filter"]["degraded"] is True
    assert "empty_layout_after_simple_filter_fallback_to_raw_layout" in str(
        meta["language_filter"]["degraded_reason"]
    )


@pytest.mark.asyncio
async def test_build_primary_language_layout_multilingual_branch_still_uses_filter(monkeypatch):
    """
    Multilingual документ должен идти в structural/multilingual filter path.
    """
    decision = _make_decision(is_multilingual=True)

    async def fake_analyze_document_languages(*args, **kwargs):
        return decision

    seen: dict[str, object] = {}

    def fake_filter_layout_to_language(layout, target_language, context=None):
        seen["called"] = True
        seen["context"] = context
        return {
            "document_id": layout.get("document_id"),
            "document_version_id": layout.get("document_version_id"),
            "elements": [
                {
                    "element_id": "el-ru",
                    "page": 1,
                    "bbox": [0, 0, 100, 10],
                    "text": "1 ДОГОВОР ПОСТАВКИ",
                    "type": "heading",
                }
            ],
            "tables": [],
            "excluded_element_ids": ["el-2"],
            "filter_decisions": [],
            "metadata": {
                "language_filter": {
                    "structural_filter_used": True,
                    "degraded": False,
                }
            },
        }

    monkeypatch.setattr(dlp, "analyze_document_languages", fake_analyze_document_languages)
    monkeypatch.setattr(dlp, "filter_layout_to_language", fake_filter_layout_to_language)

    raw_layout = {
        "document_id": "doc-1",
        "document_version_id": "ver-1",
        "elements": [
            {
                "element_id": "el-1",
                "page": 1,
                "bbox": [0, 0, 100, 10],
                "text": "1 ДОГОВОР ПОСТАВКИ",
                "type": "heading",
            },
            {
                "element_id": "el-2",
                "page": 1,
                "bbox": [120, 0, 220, 10],
                "text": "1 SALE AGREEMENT",
                "type": "heading",
            },
        ],
        "tables": [],
        "metadata": {},
    }

    result = await dlp.build_primary_language_layout(
        db=None,
        deal_id=uuid.uuid4(),
        tenant_id="tenant-1",
        document_id="doc-1",
        layout=raw_layout,
        target_language="ru",
    )

    assert result.should_quarantine is False
    assert seen.get("called") is True
    assert seen["context"]["is_multilingual"] is True
    # backward compat ключ тоже может присутствовать
    assert seen["context"]["is_bilingual"] is True
    assert result.primary_layout["metadata"]["language_filter"]["structural_filter_used"] is True


def test_filter_layout_to_language_simple_filter_preserves_structured_data():
    """
    Structured data (email, SWIFT) сохраняется даже если target_language=ru
    и рядом есть английский heading.
    """
    layout = {
        "document_id": "doc-1",
        "document_version_id": "ver-1",
        "elements": [
            {
                "element_id": "el-1",
                "page": 1,
                "bbox": [0, 0, 100, 10],
                "text": "1 ДОГОВОР ПОСТАВКИ",
                "type": "heading",
            },
            {
                "element_id": "el-2",
                "page": 1,
                "bbox": [0, 20, 200, 30],
                "text": "buyer@example.com",
                "type": "text",
            },
            {
                "element_id": "el-3",
                "page": 1,
                "bbox": [0, 40, 200, 50],
                "text": "SWIFT ABC123",
                "type": "text",
            },
            {
                "element_id": "el-4",
                "page": 1,
                "bbox": [0, 60, 200, 70],
                "text": "This Sale and Purchase Agreement is entered into between the parties",
                "type": "heading",
            },
        ],
        "tables": [],
        "metadata": {},
    }

    result = filter_layout_to_language(
        layout,
        "ru",
        context={"is_multilingual": False, "document_id": "doc-1"},
    )

    texts = [str(el.get("text") or "") for el in result["elements"]]

    assert "buyer@example.com" in texts
    assert "SWIFT ABC123" in texts
    assert any("ДОГОВОР ПОСТАВКИ" in text for text in texts)
    assert not any("entered into between the parties" in text for text in texts)


    