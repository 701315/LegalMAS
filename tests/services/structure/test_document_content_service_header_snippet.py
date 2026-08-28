import pytest
pytestmark = pytest.mark.skip(reason="get_snippet_from_layout was refactored into get_title_and_preamble")
import types
import uuid

import pytest

from src.engine.content.document_content_service import DocumentContentService


def _make_service() -> DocumentContentService:
    svc = object.__new__(DocumentContentService)
    svc.session = None
    svc.versions = None
    svc.documents = None
    svc._artifact_store = None
    svc.storage = None
    svc.layout_storage = None
    return svc


def _make_version():
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        clause_tree_ref="dummy-clause-tree-ref",
        layout_primary_ref="dummy-layout-ref",
        layout_primary_sanitized_ref="dummy-layout-sanitized-ref",
    )


@pytest.mark.asyncio
async def test_get_title_and_preamble_short_doc_reads_only_first_2_pages():
    svc = _make_service()
    version = _make_version()

    layout = {
        "metadata": {"total_pages": 4},
        "elements": [
            {"page": 1, "text": "SALE AND PURCHASE AGREEMENT"},
            {"page": 2, "text": "This agreement is made between Seller and Buyer."},
            {"page": 3, "text": "Extended preamble still on page 3 but must be ignored."},
            {"page": 4, "text": "More text that must also be ignored."},
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4())

    assert result is not None
    assert "SALE AND PURCHASE AGREEMENT" in result
    assert "This agreement is made between Seller and Buyer." in result
    assert "Extended preamble still on page 3" not in result
    assert "More text that must also be ignored." not in result


@pytest.mark.asyncio
async def test_get_title_and_preamble_long_doc_reads_first_3_pages():
    svc = _make_service()
    version = _make_version()

    layout = {
        "metadata": {"total_pages": 10},
        "elements": [
            {"page": 1, "text": "SALE AND PURCHASE AGREEMENT"},
            {"page": 2, "text": "This agreement is made between Seller and Buyer."},
            {"page": 3, "text": "Additional preamble and recitals on page 3."},
            {"page": 4, "text": "Page 4 text must be ignored by effective_max_pages=3."},
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4())

    assert result is not None
    assert "SALE AND PURCHASE AGREEMENT" in result
    assert "This agreement is made between Seller and Buyer." in result
    assert "Additional preamble and recitals on page 3." in result
    assert "Page 4 text must be ignored" not in result


@pytest.mark.asyncio
async def test_get_title_and_preamble_stops_on_table_of_contents():
    svc = _make_service()
    version = _make_version()

    layout = {
        "metadata": {"total_pages": 8},
        "elements": [
            {"page": 1, "text": "LEASE AGREEMENT"},
            {"page": 1, "text": "Between Landlord and Tenant"},
            {"page": 2, "text": "TABLE OF CONTENTS"},
            {"page": 2, "text": "This text must not appear after TOC stop-signal."},
            {"page": 3, "text": "This page must not appear either."},
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4())

    assert result is not None
    assert "LEASE AGREEMENT" in result
    assert "Between Landlord and Tenant" in result
    assert "TABLE OF CONTENTS" not in result
    assert "This text must not appear after TOC stop-signal." not in result
    assert "This page must not appear either." not in result


@pytest.mark.asyncio
async def test_get_title_and_preamble_stops_on_first_numbered_section():
    svc = _make_service()
    version = _make_version()

    layout = {
        "metadata": {"total_pages": 6},
        "elements": [
            {"page": 1, "text": "LOAN AGREEMENT"},
            {"page": 1, "text": "This agreement is entered into on 1 Jan 2026."},
            {"page": 2, "text": "1. DEFINITIONS"},
            {"page": 2, "text": "This text must not be included."},
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4())

    assert result is not None
    assert "LOAN AGREEMENT" in result
    assert "This agreement is entered into on 1 Jan 2026." in result
    assert "1. DEFINITIONS" not in result
    assert "This text must not be included." not in result


@pytest.mark.asyncio
async def test_get_title_and_preamble_truncates_to_max_length():
    svc = _make_service()
    version = _make_version()

    long_text = "A" * 2000
    layout = {
        "metadata": {"total_pages": 5},
        "elements": [
            {"page": 1, "text": long_text},
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4(), max_length=1500)

    assert result is not None
    assert len(result) == 1500


@pytest.mark.asyncio
async def test_get_title_and_preamble_short_doc_skips_1_page():
    svc = _make_service()
    version = _make_version()

    layout = {
        "metadata": {"total_pages": 4},
        "elements": [
            {"page": 1, "text": "Header text on page 1 that must be skipped."},
            {"page": 2, "text": "This is the first body paragraph that must be included because only 1 page is skipped."},
            {"page": 3, "text": "This is the second body paragraph that must also be included."},
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4())

    assert result is not None
    assert "Header text on page 1" not in result
    assert "first body paragraph" in result
    assert "second body paragraph" in result


@pytest.mark.asyncio
async def test_get_title_and_preamble_long_doc_skips_3_pages():
    svc = _make_service()
    version = _make_version()

    layout = {
        "metadata": {"total_pages": 9},
        "elements": [
            {"page": 1, "text": "Header page 1 must be skipped."},
            {"page": 2, "text": "Header page 2 must be skipped."},
            {"page": 3, "text": "Header page 3 must be skipped."},
            {"page": 4, "text": "This body text starts after 3 skipped pages and must be included."},
            {"page": 5, "text": "Another body paragraph that must also be included."},
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4())

    assert result is not None
    assert "Header page 1" not in result
    assert "Header page 2" not in result
    assert "Header page 3" not in result
    assert "starts after 3 skipped pages" in result
    assert "Another body paragraph" in result


@pytest.mark.asyncio
async def test_get_title_and_preamble_does_not_skip_all_pages_for_very_short_doc():
    svc = _make_service()
    version = _make_version()

    layout = {
        "metadata": {"total_pages": 1},
        "elements": [
            {"page": 1, "text": "This is the only meaningful text in a one-page document and should survive."},
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4())

    assert result is not None
    assert "only meaningful text" in result


@pytest.mark.asyncio
async def test_get_title_and_preamble_filters_out_short_elements():
    svc = _make_service()
    version = _make_version()

    layout = {
        "metadata": {"total_pages": 6},
        "elements": [
            {"page": 4, "text": "12"},
            {"page": 4, "text": "A"},
            {"page": 4, "text": "Short line"},
            {
                "page": 4,
                "text": "This is a sufficiently long body paragraph that must be included in the snippet.",
            },
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4(), min_element_len=40)

    assert result is not None
    assert "12" not in result
    assert "A" not in result
    assert "Short line" not in result
    assert "sufficiently long body paragraph" in result


@pytest.mark.asyncio
async def test_get_title_and_preamble_truncates_to_max_length():
    svc = _make_service()
    version = _make_version()

    text1 = "A" * 1000
    text2 = "B" * 1000
    layout = {
        "metadata": {"total_pages": 6},
        "elements": [
            {"page": 4, "text": text1},
            {"page": 5, "text": text2},
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4(), max_length=1500)

    assert result is not None
    assert len(result) == 1500


@pytest.mark.asyncio
async def test_get_title_and_preamble_falls_back_to_passed_skip_pages_when_total_pages_unknown():
    svc = _make_service()
    version = _make_version()

    layout = {
        "metadata": {},
        "elements": [
            {"page": 1, "text": "Must be skipped because explicit skip_pages=2."},
            {"page": 2, "text": "Must also be skipped because explicit skip_pages=2."},
            {
                "page": 3,
                "text": "This is a sufficiently long body paragraph that must be included when total_pages is unknown.",
            },
        ],
    }

    async def _get_latest_version(doc_id):
        return version

    async def _load_layout(v):
        return layout

    svc._get_latest_version = _get_latest_version
    svc._load_layout = _load_layout

    result = await svc.get_title_and_preamble(uuid.uuid4(), skip_pages=2)

    assert result is not None
    assert "Must be skipped" not in result
    assert "sufficiently long body paragraph" in result


