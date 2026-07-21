import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from engine.checks import instruction_snapshot
from engine.instructions.override_service import (
    BaseVersionNotFoundError,
    EffectiveInstructionPayload,
    StaleBaseError,
)

pytestmark = pytest.mark.asyncio


def _build_run_repo():
    run_repo = Mock()
    run_repo.update_instruction_snapshot = AsyncMock(return_value=object())
    return run_repo


def _snapshot_update_call(run_repo):
    call = run_repo.update_instruction_snapshot.await_args
    return {
        "run_id": call.args[0],
        "versions": call.args[1],
        "manifest": call.args[2],
        "payload": call.args[3],
        "snapshot_schema_version": call.kwargs["snapshot_schema_version"],
    }


async def test_freeze_instruction_snapshot_uses_effective_override_chain(monkeypatch):
    run_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    base_version_id = uuid.uuid4()
    tenant_override_id = uuid.uuid4()
    deal_override_id = uuid.uuid4()

    registry = Mock()
    monkeypatch.setattr(
        instruction_snapshot.YAMLRegistry,
        "get_instance",
        Mock(return_value=registry),
    )

    version_repo = Mock()
    version_repo.get_latest_published = AsyncMock()
    version_repo.resolve_or_create_from_config = AsyncMock()
    monkeypatch.setattr(
        instruction_snapshot,
        "DocumentTypeInstructionVersionRepository",
        lambda session: version_repo,
    )

    override_service = Mock()
    override_service.resolve_effective_payload = AsyncMock(
        return_value=EffectiveInstructionPayload(
            doc_type_code="nda",
            base_version_id=base_version_id,
            base_content_hash="base-content-hash",
            tenant_override_id=tenant_override_id,
            deal_override_id=deal_override_id,
            effective_payload={"checks": [{"id": "custom-check"}]},
            effective_hash="effective-hash",
            is_overridden=True,
            provenance={"source": "test"},
        )
    )
    monkeypatch.setattr(
        instruction_snapshot,
        "InstructionOverrideService",
        lambda session: override_service,
    )

    run_repo = _build_run_repo()

    result = await instruction_snapshot.freeze_instruction_snapshot(
        run_uuid=run_id,
        doc_types={"nda"},
        run_repo=run_repo,
        session=object(),
        tenant_id=tenant_id,
        deal_id=deal_id,
    )

    assert result == {"nda": str(base_version_id)}

    saved = _snapshot_update_call(run_repo)
    assert saved["run_id"] == run_id
    assert saved["versions"] == {"nda": str(base_version_id)}
    assert saved["payload"] == {"nda": {"checks": [{"id": "custom-check"}]}}
    assert saved["snapshot_schema_version"] == 1

    manifest = saved["manifest"]["nda"]
    assert manifest["version_id"] == str(base_version_id)
    assert manifest["override_id"] == str(deal_override_id)
    assert manifest["tenant_override_id"] == str(tenant_override_id)
    assert manifest["deal_override_id"] == str(deal_override_id)
    assert manifest["is_overridden"] is True
    assert manifest["effective_hash"] == "effective-hash"
    assert manifest["resolution_strategy"] == "effective_override_chain"

    registry.get_config.assert_not_called()
    version_repo.resolve_or_create_from_config.assert_not_awaited()


async def test_freeze_instruction_snapshot_falls_back_to_registry_seed_when_no_published_base(
    monkeypatch,
):
    run_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    seeded_version_id = uuid.uuid4()

    cfg = SimpleNamespace(
        type_code="nda",
        name="NDA",
        source_yaml="checks:\n  - id: base-check\n",
        source_sha256="cfg-sha",
        raw={"checks": [{"id": "base-check"}]},
    )

    registry = Mock()
    registry.get_config = Mock(return_value=cfg)
    monkeypatch.setattr(
        instruction_snapshot.YAMLRegistry,
        "get_instance",
        Mock(return_value=registry),
    )

    seeded_version = SimpleNamespace(
        id=seeded_version_id,
        compiled_payload={"checks": [{"id": "base-check"}]},
        immutable_content_hash="seeded-immutable-hash",
        source_sha256="cfg-sha",
        source_yaml=cfg.source_yaml,
        owner_scope="platform",
    )
    resolve_result = SimpleNamespace(
        version=seeded_version,
        created=True,
        lookup_key="nda:cfg-sha",
    )

    version_repo = Mock()
    version_repo.get_latest_published = AsyncMock(return_value=None)
    version_repo.resolve_or_create_from_config = AsyncMock(return_value=resolve_result)
    monkeypatch.setattr(
        instruction_snapshot,
        "DocumentTypeInstructionVersionRepository",
        lambda session: version_repo,
    )

    override_service = Mock()
    override_service.resolve_effective_payload = AsyncMock(
        side_effect=BaseVersionNotFoundError("no published base")
    )
    monkeypatch.setattr(
        instruction_snapshot,
        "InstructionOverrideService",
        lambda session: override_service,
    )

    run_repo = _build_run_repo()

    result = await instruction_snapshot.freeze_instruction_snapshot(
        run_uuid=run_id,
        doc_types={"nda"},
        run_repo=run_repo,
        session=object(),
        tenant_id=tenant_id,
        deal_id=deal_id,
    )

    assert result == {"nda": str(seeded_version_id)}

    saved = _snapshot_update_call(run_repo)
    assert saved["versions"] == {"nda": str(seeded_version_id)}
    assert saved["payload"] == {"nda": {"checks": [{"id": "base-check"}]}}

    manifest = saved["manifest"]["nda"]
    assert manifest["version_id"] == str(seeded_version_id)
    assert manifest["override_id"] is None
    assert manifest["tenant_override_id"] is None
    assert manifest["deal_override_id"] is None
    assert manifest["is_overridden"] is False
    assert manifest["resolution_strategy"] == "registry_seeded_base"

    version_repo.resolve_or_create_from_config.assert_awaited_once_with(cfg)


async def test_freeze_instruction_snapshot_is_all_or_nothing_when_any_doc_type_resolution_fails(
    monkeypatch,
):
    run_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    successful_base_version_id = uuid.uuid4()

    registry = Mock()
    monkeypatch.setattr(
        instruction_snapshot.YAMLRegistry,
        "get_instance",
        Mock(return_value=registry),
    )

    version_repo = Mock()
    version_repo.get_latest_published = AsyncMock(return_value=None)
    version_repo.resolve_or_create_from_config = AsyncMock()
    monkeypatch.setattr(
        instruction_snapshot,
        "DocumentTypeInstructionVersionRepository",
        lambda session: version_repo,
    )

    async def _resolve_effective_payload(*, doc_type_code, tenant_id, deal_id):
        if doc_type_code == "nda":
            return EffectiveInstructionPayload(
                doc_type_code="nda",
                base_version_id=successful_base_version_id,
                base_content_hash="base-hash",
                tenant_override_id=None,
                deal_override_id=None,
                effective_payload={"checks": [{"id": "ok"}]},
                effective_hash="ok-hash",
                is_overridden=False,
                provenance={"source": "test"},
            )
        raise StaleBaseError("override is stale")

    override_service = Mock()
    override_service.resolve_effective_payload = AsyncMock(
        side_effect=_resolve_effective_payload
    )
    monkeypatch.setattr(
        instruction_snapshot,
        "InstructionOverrideService",
        lambda session: override_service,
    )

    run_repo = _build_run_repo()

    with pytest.raises(instruction_snapshot.InstructionSnapshotFreezeError) as exc_info:
        await instruction_snapshot.freeze_instruction_snapshot(
            run_uuid=run_id,
            doc_types={"nda", "msa"},
            run_repo=run_repo,
            session=object(),
            tenant_id=tenant_id,
            deal_id=deal_id,
        )

    assert run_repo.update_instruction_snapshot.await_count == 0
    assert exc_info.value.run_id == str(run_id)
    assert any(item["doc_type"] == "msa" for item in exc_info.value.errors)
    assert any(item["error_type"] == "StaleBaseError" for item in exc_info.value.errors)


async def test_freeze_instruction_snapshot_uses_published_platform_base_without_tenant_context(
    monkeypatch,
):
    run_id = uuid.uuid4()
    published_version_id = uuid.uuid4()

    registry = Mock()
    registry.get_config = Mock(return_value=None)
    monkeypatch.setattr(
        instruction_snapshot.YAMLRegistry,
        "get_instance",
        Mock(return_value=registry),
    )

    published_version = SimpleNamespace(
        id=published_version_id,
        compiled_payload={"checks": [{"id": "published-check"}]},
        immutable_content_hash="published-immutable-hash",
        source_sha256="published-source-sha",
        source_yaml="checks:\n  - id: published-check\n",
        owner_scope="platform",
    )

    version_repo = Mock()
    version_repo.get_latest_published = AsyncMock(return_value=published_version)
    version_repo.resolve_or_create_from_config = AsyncMock()
    monkeypatch.setattr(
        instruction_snapshot,
        "DocumentTypeInstructionVersionRepository",
        lambda session: version_repo,
    )

    override_service = Mock()
    override_service.resolve_effective_payload = AsyncMock()
    monkeypatch.setattr(
        instruction_snapshot,
        "InstructionOverrideService",
        lambda session: override_service,
    )

    run_repo = _build_run_repo()

    result = await instruction_snapshot.freeze_instruction_snapshot(
        run_uuid=run_id,
        doc_types={"nda"},
        run_repo=run_repo,
        session=object(),
        tenant_id=None,
        deal_id=None,
    )

    assert result == {"nda": str(published_version_id)}

    saved = _snapshot_update_call(run_repo)
    assert saved["versions"] == {"nda": str(published_version_id)}
    assert saved["payload"] == {"nda": {"checks": [{"id": "published-check"}]}}

    manifest = saved["manifest"]["nda"]
    assert manifest["version_id"] == str(published_version_id)
    assert manifest["override_id"] is None
    assert manifest["is_overridden"] is False
    assert manifest["resolution_strategy"] == "published_platform_base"

    version_repo.resolve_or_create_from_config.assert_not_awaited()


    