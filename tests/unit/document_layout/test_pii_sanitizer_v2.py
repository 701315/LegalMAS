"""Unit tests для PII санитизатора V2 (Фаза 10)."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import uuid
from core.constants import DocumentStatus
from workers.pii_sanitizer import PIISanitizer


@pytest.mark.asyncio
async def test_pii_sanitizer_v2_isolated_flow_success():
    # 1. Сборка UUIDs
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    run_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    # 2. Мокаем UnitOfWork и сессию
    mock_uow = MagicMock()
    mock_uow.session = AsyncMock()

    # Имитируем DocumentVersion и Document в БД
    mock_ver = MagicMock()
    mock_ver.id = ver_id
    mock_ver.document_id = doc_id
    mock_ver.layout_primary_ref = "s3://bucket/legacy_primary.json"

    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.status = "EXTRACTED"
    mock_doc.applicable_triggers = []

    # Мокаем репозитории
    mock_ver_repo = AsyncMock()
    mock_ver_repo.get_by_id.return_value = mock_ver

    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = mock_doc

    # Имитируем V2 резолв-запись
    mock_res_record = MagicMock()
    mock_res_record.layout_primary_ref = "s3://bucket/run_scoped_primary.json"
    mock_res_record.layout_primary_sanitized_ref = None

    mock_res_repo = AsyncMock()
    mock_res_repo.get_by_run_and_version.return_value = mock_res_record

    # Мокаем S3 хранилище (динамический возврат S3 URIs)
    mock_store = MagicMock()
    mock_store.get_json.return_value = {"elements": []}  
    mock_store.put_json.side_effect = lambda path, data, **kwargs: f"s3://bucket/{path}"
    mock_store.put_file.side_effect = lambda path, data, **kwargs: f"s3://bucket/{path}"

    # Мокаем шифратор PII
    mock_encryptor = MagicMock()
    mock_encryptor.encrypt_mapping.return_value = b"encrypted_bytes"

    # Мокаем детекторы
    mock_detector = MagicMock()
    mock_detector.detect.return_value = []

    # Слайдим моки
    with patch("workers.pii_sanitizer.DocumentVersionRepository", return_value=mock_ver_repo), \
         patch("workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo), \
         patch("workers.pii_sanitizer.DocumentRunLanguageResolutionRepository", return_value=mock_res_repo), \
         patch("workers.pii_sanitizer.AuditRepository", return_value=AsyncMock()), \
         patch("workers.pii_sanitizer.settings") as mock_settings, \
         patch("workers.pii_sanitizer.layout_config") as mock_config:

        mock_config.document_layout_v2_enabled = True
        mock_settings.DOCUMENT_LAYOUT_V2_ENABLED = True
        mock_settings.PII_AUDIT_ENABLED = False
        mock_settings.PII_SKIP_IF_ALREADY_SANITIZED = False

        sanitizer = PIISanitizer(
            uow=mock_uow,
            artifact_store=mock_store,
            artifact_tenant_id=tenant_id,
            detector=mock_detector,
            encryptor=mock_encryptor,
            run_id=str(run_id),
        )

        res = await sanitizer.sanitize(ver_id)

        # 3. Проверки
        assert res["status"] == DocumentStatus.SANITIZED.value
        assert res["committed"] is True

        # Воркер считал изолированный run-scoped макет!
        mock_store.get_json.assert_called_once_with("s3://bucket/run_scoped_primary.json")

        expected_sanitized_path = "tenants/" + str(tenant_id) + "/deals/" + str(mock_doc.deal_id) + "/runs/" + str(run_id) + "/" + str(doc_id) + "_layout_primary_sanitized.json"
        expected_mapping_path = "tenants/" + str(tenant_id) + "/deals/" + str(mock_doc.deal_id) + "/pii/" + str(doc_id) + "/mapping.enc"

        # Воркер записал sanitized-ссылку в резолв-запись (в виде канонической S3-ссылки)
        assert mock_res_record.layout_primary_sanitized_ref == f"s3://bucket/{expected_sanitized_path}"
        assert mock_res_record.resolution_status == "LANGUAGE_READY"

        # И продублировал в DocumentVersion для legacy-совместимости (в виде канонической S3-ссылки)
        mock_ver_repo.update_refs.assert_called_once_with(
            version_id=ver_id,
            layout_primary_sanitized_ref=f"s3://bucket/{expected_sanitized_path}",
            pii_mapping_ref=f"s3://bucket/{expected_mapping_path}",
        )
