"""Интеграционные тесты для build_primary_language_source (Фаза 8)."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import uuid
from core.constants import DocumentStatus
from workers.build_primary_language_source import _build_primary_language_source_async


@pytest.mark.asyncio
async def test_build_primary_language_source_v2_path_success():
    # 1. Создаем UUIDs
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    run_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    # 2. Мокаем репозитории
    mock_db = AsyncMock()
    
    # Имитируем поведение SQLAlchemy 2.0 AsyncSession.execute()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "BLOCK_DOCUMENT_CONTINUE_RUN"
    mock_db.execute.return_value = mock_result

    mock_ver = MagicMock()
    mock_ver.origin_filetype = "pdf"
    mock_ver.original_ref = "s3://bucket/test.pdf"
    mock_ver.converted_pdf_ref = None
    mock_ver.detected_languages = ["ru", "en"]

    # Мокаем репозиторий версий
    mock_ver_repo = AsyncMock()
    mock_ver_repo.get_by_id.return_value = mock_ver

    # Мокаем репозиторий документов
    mock_doc_repo = AsyncMock()

    # Мокаем репозиторий сделок
    mock_deal_repo = AsyncMock()
    mock_deal = MagicMock()
    mock_deal.primary_language = "ru"
    mock_deal_repo.internal_unsafe_get_by_id.return_value = mock_deal

    # Мокаем репозиторий резолва
    mock_res_repo = AsyncMock()

    # Слайдим моки репозиториев в классы инициализации
    with patch("workers.build_primary_language_source.DocumentVersionRepository", return_value=mock_ver_repo), \
         patch("workers.build_primary_language_source.DocumentRepository", return_value=mock_doc_repo), \
         patch("workers.build_primary_language_source.DealRepository", return_value=mock_deal_repo), \
         patch("workers.build_primary_language_source.DocumentRunLanguageResolutionRepository", return_value=mock_res_repo), \
         patch("workers.build_primary_language_source.AuditRepository", return_value=AsyncMock()), \
         patch("workers.build_primary_language_source.ArtifactStore") as mock_store_cls, \
         patch("workers.build_primary_language_source.DocumentLayoutService") as mock_service_cls, \
         patch("workers.build_primary_language_source.recompute_deal_language_discovery_state", return_value=AsyncMock()), \
         patch("workers.build_primary_language_source.update_deal_languages", return_value=AsyncMock()), \
         patch("workers.build_primary_language_source.layout_config") as mock_config:

        # Мокаем настройки
        mock_config.document_layout_v2_enabled = True

        # Мокаем S3 хранилище и бакет
        mock_store = MagicMock()
        mock_store.bucket = "bucket"  # Явно задаем бакет, совпадающий с S3-ссылкой
        mock_store.get_file.return_value = b"%PDF-mock-bytes"
        mock_store_cls.return_value = mock_store

        # Мокаем оркестрирующий сервис
        mock_service = MagicMock()
        mock_prepared_res = MagicMock()
        mock_prepared_res.canonical_layout_ref = "s3://bucket/canonical.json"
        mock_prepared_res.layout_primary_ref = "s3://bucket/primary.json"
        mock_prepared_res.detected_languages = ["ru", "en"]
        mock_prepared_res.total_atoms = 100
        mock_prepared_res.projected_atoms = 80
        mock_service.prepare_document_layout.return_value = mock_prepared_res
        mock_service_cls.return_value = mock_service

        # Запускаем асинхронное ядро воркера по V2 пути
        result = await _build_primary_language_source_async(
            document_version_id=str(ver_id),
            document_id=str(doc_id),
            deal_id=str(deal_id),
            tenant_id=str(tenant_id),
            db=mock_db,
            run_id=str(run_id),
            target_language="ru",
        )

        # 3. Проверки успешного выполнения
        assert result["committed"] is True
        assert result["canonical_layout_ref"] == "s3://bucket/canonical.json"
        assert result["layout_primary_ref"] == "s3://bucket/primary.json"
        assert result["target_language"] == "ru"
        assert result["detected_languages"] == ["ru", "en"]

        # Проверим, что репозитории вызвали ожидаемые методы обновления
        mock_ver_repo.update_refs.assert_called_once_with(
            version_id=ver_id,
            canonical_layout_ref="s3://bucket/canonical.json",
            detected_languages=["ru", "en"],
            layout_primary_ref="s3://bucket/primary.json",
            primary_source_ref="s3://bucket/test.pdf",
        )

        mock_res_repo.upsert_resolution.assert_called_once_with(
            run_id=run_id,
            document_version_id=ver_id,
            tenant_id=tenant_id,
            requested_language="ru",
            available_languages=["ru", "en"],
            effective_language="ru",
            resolution_status="LANGUAGE_READY",
            canonical_layout_ref="s3://bucket/canonical.json",
            layout_primary_ref="s3://bucket/primary.json",
        )

        mock_doc_repo.update_status.assert_called_once_with(
            doc_id,
            DocumentStatus.PRIMARY_READY.value,
        )
