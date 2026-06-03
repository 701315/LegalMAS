from __future__ import annotations

import uuid

import pytest

import services.document_language_pipeline as dlp
from services.layout_language_filter import filter_layout_to_language


def _make_decision(
    *,
    target_language: str = "ru",
    is_bilingual: bool = False,
    route: str = "proceed",
    quarantine_reason: str | None = None,
) -> dlp.DocumentLanguageDecision:
    return dlp.DocumentLanguageDecision(
        detected_languages=["ru", "en"] if is_bilingual else ["ru"],
        target_language=target_language,
        is_bilingual=is_bilingual,
        target_language_ratio=0.92 if not is_bilingual else 0.55,
        route=route,
        quarantine_reason=quarantine_reason,
        deal_primary_language_before=target_language,
        deal_languages_before=["ru", "en"] if is_bilingual else ["ru"],
        deal_primary_language_after=target_language,
        deal_languages_after=["ru", "en"] if is_bilingual else ["ru"],
        requires_user_selection=False,
        pipeline_mode="PRIMARY_ONLY_DOWNSTREAM",
    )


@pytest.mark.asyncio
async def test_build_primary_language_layout_applies_filter_for_non_bilingual_document(monkeypatch):
    decision = _make_decision(is_bilingual=False)

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
    assert seen["context"]["is_bilingual"] is False

    assert len(result.primary_layout["elements"]) == 1
    assert result.primary_layout["elements"][0]["text"] == "1 ДОГОВОР ПОСТАВКИ"

    meta = result.primary_layout["metadata"]
    assert meta["language_pipeline"]["fallback_used"] is False
    assert meta["language_pipeline"]["is_bilingual"] is False
    assert meta["language_filter"]["fallback_used"] is False
    assert meta["language_filter"]["structural_filter_used"] is False


@pytest.mark.asyncio
async def test_build_primary_language_layout_non_bilingual_empty_filter_falls_back_to_raw(monkeypatch):
    decision = _make_decision(is_bilingual=False)

    async def fake_analyze_document_languages(*args, **kwargs):
        return decision

    def fake_filter_layout_to_language(layout, target_language, context=None):
        return {
            "document_id": layout.get("document_id"),
            "document_version_id": layout.get("document_version_id"),
            "elements": [],
            "tables": [],
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
async def test_build_primary_language_layout_bilingual_branch_still_uses_filter(monkeypatch):
    decision = _make_decision(is_bilingual=True)

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
    assert seen["context"]["is_bilingual"] is True
    assert result.primary_layout["metadata"]["language_filter"]["structural_filter_used"] is True


def test_filter_layout_to_language_simple_filter_preserves_structured_data():
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
                "text": "SALE AGREEMENT",
                "type": "heading",
            },
        ],
        "tables": [],
        "metadata": {},
    }

    result = filter_layout_to_language(
        layout,
        "ru",
        context={"is_bilingual": False, "document_id": "doc-1"},
    )

    texts = [str(el.get("text") or "") for el in result["elements"]]

    assert "buyer@example.com" in texts
    assert "SWIFT ABC123" in texts
    assert any("ДОГОВОР ПОСТАВКИ" in text for text in texts)
    assert not any(text == "SALE AGREEMENT" for text in texts)


    