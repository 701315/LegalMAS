from storage.artifact_store import ArtifactPath
from workers.extract_worker import (
    _attach_primary_language_metadata,
    _load_primary_language_metadata_sidecar_safe,
)


class JsonStore:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.last_path: str | None = None

    def get_json(self, path: str):
        self.last_path = path
        if self.error is not None:
            raise self.error
        return self.payload


def test_load_primary_language_metadata_sidecar_safe_returns_supported_keys_only() -> None:
    store = JsonStore(
        payload={
            "contract_version": 1,
            "language_pipeline": {"target_language": "en", "is_bilingual": False},
            "language_filter": {"contract_version": 1, "mode": "simple"},
            "unrelated": {"ignored": True},
        }
    )

    metadata = _load_primary_language_metadata_sidecar_safe(
        store=store,
        tenant_id="tenant-1",
        deal_id="deal-1",
        document_id="doc-1",
        document_version_id="ver-1",
    )

    assert store.last_path == ArtifactPath.primary_source_language_metadata(
        tenant_id="tenant-1",
        deal_id="deal-1",
        document_id="doc-1",
    )
    assert metadata == {
        "language_pipeline": {"target_language": "en", "is_bilingual": False},
        "language_filter": {"contract_version": 1, "mode": "simple"},
    }


def test_load_primary_language_metadata_sidecar_safe_returns_none_on_read_error() -> None:
    store = JsonStore(error=RuntimeError("missing sidecar"))

    metadata = _load_primary_language_metadata_sidecar_safe(
        store=store,
        tenant_id="tenant-1",
        deal_id="deal-1",
        document_id="doc-1",
        document_version_id="ver-1",
    )

    assert metadata is None


def test_load_primary_language_metadata_sidecar_safe_returns_none_for_invalid_payload() -> None:
    store = JsonStore(payload=["not", "a", "dict"])

    metadata = _load_primary_language_metadata_sidecar_safe(
        store=store,
        tenant_id="tenant-1",
        deal_id="deal-1",
        document_id="doc-1",
        document_version_id="ver-1",
    )

    assert metadata is None


def test_attach_primary_language_metadata_preserves_existing_metadata_and_does_not_mutate_input() -> None:
    raw_layout = {
        "elements": [{"text": "Clause 1"}],
        "metadata": {
            "extraction": {"strategy": "text"},
        },
    }

    language_metadata = {
        "language_pipeline": {"target_language": "en", "is_bilingual": False},
        "language_filter": {"contract_version": 1, "mode": "simple"},
    }

    layout_primary = _attach_primary_language_metadata(
        layout=raw_layout,
        language_metadata=language_metadata,
    )

    assert layout_primary is not raw_layout
    assert raw_layout == {
        "elements": [{"text": "Clause 1"}],
        "metadata": {
            "extraction": {"strategy": "text"},
        },
    }
    assert layout_primary["metadata"] == {
        "extraction": {"strategy": "text"},
        "language_pipeline": {"target_language": "en", "is_bilingual": False},
        "language_filter": {"contract_version": 1, "mode": "simple"},
    }


def test_attach_primary_language_metadata_returns_copy_when_sidecar_missing() -> None:
    raw_layout = {
        "elements": [{"text": "Clause 1"}],
    }

    layout_primary = _attach_primary_language_metadata(
        layout=raw_layout,
        language_metadata=None,
    )

    assert layout_primary == raw_layout
    assert layout_primary is not raw_layout


    