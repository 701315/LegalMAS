"""Unit tests для оркестратора и extract воркера (Фаза 9)."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import uuid
from core.constants import DocumentStatus
from workers.run_orchestrator import _start_run_pipeline_async
from workers.extract_worker import _extract_document_async


@pytest.mark.asyncio
async def test_orchestrator_v2_skip_ineligible_document_by_policy():
    """Тест: оркестратор V2 пропускает ineligible документ при BLOCK_DOCUMENT_CONTINUE_RUN policy."""
    run_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    mock_db = AsyncMock()

    # Имитируем загрузку Run
    mock_run = MagicMock()
    mock_run.status = "RUNNING"
    mock_run.deal_id = deal_id
    mock_run.tenant_id = tenant_id
    mock_run.pipeline_strategy = "REUSE_STRUCTURE"
    mock_run.missing_target_language_policy = "BLOCK_DOCUMENT_CONTINUE_RUN"

    mock_run_repo = AsyncMock()
    mock_run_repo.get_by_id.return_value = mock_run

    # Имитируем сделку
    mock_deal_repo = AsyncMock()
    mock_deal = MagicMock()
    mock_deal.primary_language = "ru"
    mock_deal_repo.internal_unsafe_get_by_id.return_value = mock_deal

    # Имитируем документы
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.status = "PRIMARY_READY"
    mock_doc.doc_type = "nda"
    mock_doc.classification_level = "L3"

    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_deal.return_value = [mock_doc]

    # Имитируем версию
    mock_ver = MagicMock()
    mock_ver.id = ver_id
    mock_ver_repo = AsyncMock()
    mock_ver_repo.get_latest.return_value = mock_ver

    # Имитируем недоступный язык резолва (LANGUAGE_UNAVAILABLE)
    mock_res_record = MagicMock()
    mock_res_record.resolution_status = "LANGUAGE_UNAVAILABLE"

    mock_res_repo = AsyncMock()
    mock_res_repo.get_by_run_and_version.return_value = mock_res_record

    mock_dse_repo = AsyncMock()

    # Слайдим моки
    with patch("workers.run_orchestrator.RunRepository", return_value=mock_run_repo), \
         patch("workers.run_orchestrator.DealRepository", return_value=mock_deal_repo), \
         patch("workers.run_orchestrator.DocumentRepository", return_value=mock_doc_repo), \
         patch("workers.run_orchestrator.DocumentVersionRepository", return_value=mock_ver_repo), \
         patch("workers.run_orchestrator.DocumentRunLanguageResolutionRepository", return_value=mock_res_repo), \
         patch("workers.run_orchestrator.DocumentStageExecutionRepository", return_value=mock_dse_repo), \
         patch("workers.run_orchestrator.AuditRepository", return_value=AsyncMock()), \
         patch("workers.run_orchestrator.settings") as mock_settings, \
         patch("workers.run_orchestrator.layout_config") as mock_config:

        mock_config.document_layout_v2_enabled = True
        mock_settings.DOCUMENT_LAYOUT_V2_ENABLED = True

        res = await _start_run_pipeline_async(
            run_id=str(run_id),
            deal_id=str(deal_id),
            tenant_id=str(tenant_id),
            force_reclassify=False,
            db=mock_db,
        )

        # Оркестратор пропустил документ и не запланировал никаких новых задач
        assert res["tasks_scheduled"] == 0
        assert res["documents_with_plan"] == 0
        mock_dse_repo.create_planned_or_none_on_conflict.assert_not_called()


@pytest.mark.asyncio
async def test_extract_worker_v2_canonical_bypass_success():
    """Тест: extract_worker V2 мгновенно завершается по bypass, если есть резолв."""
    run_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    deal_id = uuid.uuid4()

    mock_db = AsyncMock()

    # Мокаем резолв запись
    mock_res_record = MagicMock()
    mock_res_record.canonical_layout_ref = "s3://bucket/canonical.json"
    mock_res_record.layout_primary_ref = "s3://bucket/primary.json"

    mock_res_repo = AsyncMock()
    mock_res_repo.get_by_run_and_version.return_value = mock_res_record

    # Мокаем S3 хранилище
    mock_store = MagicMock()
    mock_store.bucket = "bucket"
    mock_store.get_json.return_value = {"page_count": 3}

    with patch("workers.extract_worker.DocumentRunLanguageResolutionRepository", return_value=mock_res_repo), \
         patch("workers.extract_worker.ArtifactStore") as mock_store_cls, \
         patch("workers.extract_worker.update_extraction_result", return_value=AsyncMock()) as mock_update_res, \
         patch("workers.extract_worker.layout_config") as mock_config, \
         patch("workers.extract_worker.settings") as mock_settings:

        mock_config.document_layout_v2_enabled = True
        mock_settings.DOCUMENT_LAYOUT_V2_ENABLED = True
        mock_store_cls.return_value = mock_store

        result = await _extract_document_async(
            document_version_id=str(ver_id),
            document_id=str(doc_id),
            deal_id=str(deal_id),
            tenant_id=str(tenant_id),
            db=mock_db,
            run_id=str(run_id),
        )

        assert result["status"] == DocumentStatus.EXTRACTED.value
        assert result["pages"] == 3
        assert result["strategy"] == "canonical_filtered_layout_v2"
        assert result["committed"] is True

        mock_update_res.assert_called_once_with(
            document_version_id=str(ver_id),
            document_id=str(doc_id),
            raw_ref="s3://bucket/canonical.json",
            primary_ref="s3://bucket/primary.json",
            page_count=3,
            strategy="canonical_filtered_layout_v2",
            ocr_confidence=1.0,
            db=mock_db,
        )
