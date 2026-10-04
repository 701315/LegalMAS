"""Тест: per-field location.page обновляется anchor'ом (B3.5)."""
from core.anchors.models import CheckAnchorMethod
from engine.checks.extraction import ExtractionExecutor


class _MockAnchor:
    def __init__(self, page=None, method=CheckAnchorMethod.EXACT_SPAN):
        self.page = page
        self.anchor_method = method


def test_updates_page_when_anchor_page_valid():
    payload = {"location": {"page": 1, "quote": "...", "clause_ref": "..."}}
    ExtractionExecutor._apply_anchor_page_to_field_location(
        payload, _MockAnchor(page=2),
    )
    assert payload["location"]["page"] == 2
    assert payload["location"]["quote"] == "..."
    assert payload["location"]["clause_ref"] == "..."


def test_no_update_when_anchor_page_none():
    payload = {"location": {"page": 1}}
    ExtractionExecutor._apply_anchor_page_to_field_location(
        payload, _MockAnchor(page=None),
    )
    assert payload["location"]["page"] == 1


def test_no_update_when_page_already_correct():
    payload = {"location": {"page": 2}}
    ExtractionExecutor._apply_anchor_page_to_field_location(
        payload, _MockAnchor(page=2),
    )
    assert payload["location"]["page"] == 2


def test_no_update_when_page_invalid():
    for bad_page in (0, -1, "2", True):
        payload = {"location": {"page": 1}}
        ExtractionExecutor._apply_anchor_page_to_field_location(
            payload, _MockAnchor(page=bad_page),
        )
        assert payload["location"]["page"] == 1, f"failed for {bad_page}"


def test_no_crash_when_payload_not_dict():
    ExtractionExecutor._apply_anchor_page_to_field_location(
        None, _MockAnchor(page=2),
    )
    ExtractionExecutor._apply_anchor_page_to_field_location(
        {}, _MockAnchor(page=2),
    )
    ExtractionExecutor._apply_anchor_page_to_field_location(
        {"location": None}, _MockAnchor(page=2),
    )
    ExtractionExecutor._apply_anchor_page_to_field_location(
        {"location": "not-a-dict"}, _MockAnchor(page=2),
    )


def test_no_update_when_anchor_lacks_page_attribute():
    class _NoPageAnchor:
        anchor_method = CheckAnchorMethod.EXACT_SPAN

    payload = {"location": {"page": 1}}
    ExtractionExecutor._apply_anchor_page_to_field_location(
        payload, _NoPageAnchor(),
    )
    assert payload["location"]["page"] == 1
