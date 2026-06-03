import pytest

from storage.artifact_store import ArtifactPath
from workers.build_primary_language_source import (
    _build_primary_language_metadata_sidecar,
    _store_primary_language_metadata_sidecar_safe,
)


class RecordingStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def put_json(self, path: str, payload: dict) -> str:
        self.calls.append((path, payload))
        return f"s3://{path}"


class FailingStore:
    def put_json(self, path: str, payload: dict) -> str:
        raise RuntimeError("sidecar store failed")


def test_build_primary_language_metadata_sidecar_keeps_only_supported_keys() -> None:
    primary_layout = {
        "metadata": {
            "language_pipeline": {"target_language": "en", "is_bilingual": False},
            "language_filter": {"contract_version": 1, "mode": "simple"},
            "extraction": {"strategy": "text"},
            "other_key": {"ignored": True},
        }
    }

    payload = _build_primary_language_metadata_sidecar(primary_layout)

    assert payload == {
        "contract_version": 1,
        "language_pipeline": {"target_language": "en", "is_bilingual": False},
        "language_filter": {"contract_version": 1, "mode": "simple"},
    }


def test_store_primary_language_metadata_sidecar_safe_stores_expected_path() -> None:
    store = RecordingStore()
    tenant_id = "tenant-1"
    deal_id = "deal-1"
    document_id = "doc-1"

    primary_layout = {
        "metadata": {
            "language_pipeline": {"target_language": "ru"},
            "language_filter": {"contract_version": 1, "mode": "simple"},
        }
    }

    ref = _store_primary_language_metadata_sidecar_safe(
        store=store,
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=document_id,
        primary_layout=primary_layout,
        log_extra_base={},
    )

    expected_path = ArtifactPath.primary_source_language_metadata(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=document_id,
    )

    assert ref == f"s3://{expected_path}"
    assert store.calls == [
        (
            expected_path,
            {
                "contract_version": 1,
                "language_pipeline": {"target_language": "ru"},
                "language_filter": {"contract_version": 1, "mode": "simple"},
            },
        )
    ]


def test_store_primary_language_metadata_sidecar_safe_is_failure_isolated() -> None:
    store = FailingStore()
    primary_layout = {
        "metadata": {
            "language_pipeline": {"target_language": "en"},
            "language_filter": {"contract_version": 1},
        }
    }

    ref = _store_primary_language_metadata_sidecar_safe(
        store=store,
        tenant_id="tenant-1",
        deal_id="deal-1",
        document_id="doc-1",
        primary_layout=primary_layout,
        log_extra_base={},
    )

    assert ref is None


def test_build_primary_language_metadata_sidecar_returns_none_when_layout_has_no_language_metadata() -> None:
    primary_layout = {
        "metadata": {
            "extraction": {"strategy": "text"},
        }
    }

    payload = _build_primary_language_metadata_sidecar(primary_layout)

    assert payload is None


    