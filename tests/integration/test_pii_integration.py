"""
Интеграционные тесты PII Sanitizer.

Паттерн: один тест — один процесс (согласовано с Stage 4).
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.pii_encryption import reset_encryptor
from src.workers.pii_sanitizer import PIISanitizer, sanitize_document

# ═══════════════════════════════════════════════════════════════════════════════
# Test data
# ═══════════════════════════════════════════════════════════════════════════════

FAKE_LAYOUT_RAW = {
    "elements": [
        {
            "element_id": "e001",
            "type": "text",
            "text": "Продавец Иванов Иван Иванович, паспорт 4512 123456, тел. +7 999 123-45-67.",
            "page": 1,
        },
        {
            "element_id": "e002",
            "type": "text",
            "text": "ИНН Продавца: 7707083893, ОГРН: 1027700132195.",
            "page": 1,
        },
        {
            "element_id": "e003",
            "type": "text",
            "text": "Кадастровый номер объекта: 77:01:0001001:1234.",
            "page": 2,
        },
    ],
    "metadata": {"pages": 2},
}


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_uow():
    """Мок UnitOfWork."""
    uow = MagicMock()
    uow.session = MagicMock()
    return uow


@pytest.fixture
def mock_artifact_store():
    """Мок ArtifactStore."""
    store = AsyncMock()
    store.get_json = AsyncMock(return_value=FAKE_LAYOUT_RAW)
    store.put_json = AsyncMock()
    store.put_file = AsyncMock()
    return store


@pytest.fixture
def sample_document():
    """Тестовый документ."""
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.deal_id = uuid.uuid4()
    doc.status = "extracted"
    doc.applicable_triggers = ["sale_purchase"]
    doc.classification_level = "L2"
    doc.doc_type = None
    doc.deal = MagicMock()
    doc.deal.tenant_id = uuid.uuid4()
    return doc


@pytest.fixture
def sample_version(sample_document):
    """Тестовая версия документа."""
    version = MagicMock()
    version.id = uuid.uuid4()
    version.document_id = sample_document.id
    version.text_layout_raw_ref = (
        f"tenants/{sample_document.deal.tenant_id}/raw/{sample_document.id}.json"
    )
    return version


@pytest.fixture
def mock_settings():
    """Мок настроек (UPPER_CASE)."""
    settings = MagicMock()
    settings.PII_NER_ENABLED = False
    settings.PII_PRESERVE_INN = True
    settings.PII_PRESERVE_OGRN = True
    settings.PII_PRESERVE_CADASTRAL = True
    settings.PII_PRESERVE_PARTY_ROLES = True
    settings.PII_AUDIT_ENABLED = False
    settings.PII_SKIP_IF_ALREADY_SANITIZED = True
    settings.PII_ENCRYPTION_KEY = ""  # Пустая строка = plaintext mode
    return settings


@pytest.fixture
def mock_doc_repo(sample_document):
    """Мок DocumentRepository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=sample_document)
    repo.update_status = AsyncMock()
    return repo


@pytest.fixture
def mock_version_repo(sample_version):
    """Мок DocumentVersionRepository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=sample_version)
    repo.update_refs = AsyncMock()
    return repo


@pytest.fixture
def mock_audit_repo():
    """Мок AuditRepository."""
    repo = AsyncMock()
    repo.log = AsyncMock()
    return repo


@pytest.fixture(autouse=True)
def reset_encryption():
    """Сброс синглтона шифрования перед каждым тестом."""
    reset_encryptor()
    yield
    reset_encryptor()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPIISanitizerService:
    """Тесты сервиса PIISanitizer (без Celery)."""

    @pytest.mark.asyncio
    async def test_sanitize_preserves_identifiers(
        self,
        mock_uow,
        mock_artifact_store,
        sample_document,
        sample_version,
        mock_settings,
        mock_doc_repo,
        mock_version_repo,
        mock_audit_repo,
    ):
        """ИНН, ОГРН, кадастр не токенизируются."""
        # ВАЖНО: Патчим settings в src.core.config, а не в pii_detector
        with (
            patch("src.core.config.settings", mock_settings),
            patch("src.workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo),
            patch(
                "src.workers.pii_sanitizer.DocumentVersionRepository",
                return_value=mock_version_repo,
            ),
            patch("src.workers.pii_sanitizer.AuditRepository", return_value=mock_audit_repo),
        ):
            sanitizer = PIISanitizer(
                uow=mock_uow,
                artifact_store=mock_artifact_store,
            )
            result = await sanitizer.sanitize(sample_version.id)

        assert not result.get("skipped")
        assert result["entities_preserved"] > 0

        call_args = mock_artifact_store.put_json.call_args
        sanitized_layout = call_args[0][1]
        full_text = " ".join(e["text"] for e in sanitized_layout["elements"])

        assert "7707083893" in full_text
        assert "1027700132195" in full_text
        assert "77:01:0001001:1234" in full_text

    @pytest.mark.asyncio
    async def test_sanitize_tokenizes_personal_data(
        self,
        mock_uow,
        mock_artifact_store,
        sample_document,
        sample_version,
        mock_settings,
        mock_doc_repo,
        mock_version_repo,
        mock_audit_repo,
    ):
        """Личные данные (паспорт, телефон) токенизируются."""
        with (
            patch("src.core.config.settings", mock_settings),
            patch("src.workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo),
            patch(
                "src.workers.pii_sanitizer.DocumentVersionRepository",
                return_value=mock_version_repo,
            ),
            patch("src.workers.pii_sanitizer.AuditRepository", return_value=mock_audit_repo),
        ):
            sanitizer = PIISanitizer(
                uow=mock_uow,
                artifact_store=mock_artifact_store,
            )
            result = await sanitizer.sanitize(sample_version.id)

        assert result["entities_tokenized"] > 0

        call_args = mock_artifact_store.put_json.call_args
        sanitized_layout = call_args[0][1]
        full_text = " ".join(e["text"] for e in sanitized_layout["elements"])

        assert "4512 123456" not in full_text
        assert "+7 999 123-45-67" not in full_text

    @pytest.mark.asyncio
    async def test_sanitize_idempotent(
        self,
        mock_uow,
        mock_artifact_store,
        sample_document,
        sample_version,
        mock_settings,
        mock_doc_repo,
        mock_version_repo,
        mock_audit_repo,
    ):
        """Повторный вызов для sanitized документа → skipped."""
        sample_document.status = "sanitized"

        with (
            patch("src.core.config.settings", mock_settings),
            patch("src.workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo),
            patch(
                "src.workers.pii_sanitizer.DocumentVersionRepository",
                return_value=mock_version_repo,
            ),
            patch("src.workers.pii_sanitizer.AuditRepository", return_value=mock_audit_repo),
        ):
            sanitizer = PIISanitizer(
                uow=mock_uow,
                artifact_store=mock_artifact_store,
            )
            result = await sanitizer.sanitize(sample_version.id)

        assert result.get("skipped") is True
        mock_artifact_store.get_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_sanitize_document_not_found(
        self,
        mock_uow,
        mock_artifact_store,
        sample_version,
        mock_settings,
        mock_version_repo,
        mock_audit_repo,
    ):
        """Документ не найден → PermanentError."""
        mock_doc_repo_not_found = AsyncMock()
        mock_doc_repo_not_found.get_by_id = AsyncMock(return_value=None)

        from src.core.exceptions import PermanentError

        with (
            patch("src.core.config.settings", mock_settings),
            patch(
                "src.workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo_not_found
            ),
            patch(
                "src.workers.pii_sanitizer.DocumentVersionRepository",
                return_value=mock_version_repo,
            ),
            patch("src.workers.pii_sanitizer.AuditRepository", return_value=mock_audit_repo),
        ):
            sanitizer = PIISanitizer(
                uow=mock_uow,
                artifact_store=mock_artifact_store,
            )

            with pytest.raises(PermanentError, match="not found"):
                await sanitizer.sanitize(sample_version.id)

    @pytest.mark.asyncio
    async def test_sanitize_version_not_found(
        self,
        mock_uow,
        mock_artifact_store,
        mock_settings,
        mock_doc_repo,
        mock_audit_repo,
    ):
        """Версия документа не найдена → PermanentError."""
        mock_version_repo_not_found = AsyncMock()
        mock_version_repo_not_found.get_by_id = AsyncMock(return_value=None)

        from src.core.exceptions import PermanentError

        with (
            patch("src.core.config.settings", mock_settings),
            patch("src.workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo),
            patch(
                "src.workers.pii_sanitizer.DocumentVersionRepository",
                return_value=mock_version_repo_not_found,
            ),
            patch("src.workers.pii_sanitizer.AuditRepository", return_value=mock_audit_repo),
        ):
            sanitizer = PIISanitizer(
                uow=mock_uow,
                artifact_store=mock_artifact_store,
            )

            with pytest.raises(PermanentError, match="not found"):
                await sanitizer.sanitize(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_sanitize_no_raw_text(
        self,
        mock_uow,
        mock_artifact_store,
        sample_document,
        sample_version,
        mock_settings,
        mock_doc_repo,
        mock_audit_repo,
    ):
        """Нет raw текста → PermanentError."""
        sample_version.text_layout_raw_ref = None
        mock_version_repo = AsyncMock()
        mock_version_repo.get_by_id = AsyncMock(return_value=sample_version)

        from src.core.exceptions import PermanentError

        with (
            patch("src.core.config.settings", mock_settings),
            patch("src.workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo),
            patch(
                "src.workers.pii_sanitizer.DocumentVersionRepository",
                return_value=mock_version_repo,
            ),
            patch("src.workers.pii_sanitizer.AuditRepository", return_value=mock_audit_repo),
        ):
            sanitizer = PIISanitizer(
                uow=mock_uow,
                artifact_store=mock_artifact_store,
            )

            with pytest.raises(PermanentError, match="text_layout_raw_ref"):
                await sanitizer.sanitize(sample_version.id)

    @pytest.mark.asyncio
    async def test_pii_mapping_saved(
        self,
        mock_uow,
        mock_artifact_store,
        sample_document,
        sample_version,
        mock_settings,
        mock_doc_repo,
        mock_version_repo,
        mock_audit_repo,
    ):
        """PII mapping сохраняется."""
        with (
            patch("src.core.config.settings", mock_settings),
            patch("src.workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo),
            patch(
                "src.workers.pii_sanitizer.DocumentVersionRepository",
                return_value=mock_version_repo,
            ),
            patch("src.workers.pii_sanitizer.AuditRepository", return_value=mock_audit_repo),
        ):
            sanitizer = PIISanitizer(
                uow=mock_uow,
                artifact_store=mock_artifact_store,
            )
            await sanitizer.sanitize(sample_version.id)

        assert mock_artifact_store.put_file.called
        call_args = mock_artifact_store.put_file.call_args
        mapping_data = call_args[0][1]

        mapping = json.loads(mapping_data.decode("utf-8"))
        assert isinstance(mapping, dict)

    @pytest.mark.asyncio
    async def test_document_status_updated(
        self,
        mock_uow,
        mock_artifact_store,
        sample_document,
        sample_version,
        mock_settings,
        mock_doc_repo,
        mock_version_repo,
        mock_audit_repo,
    ):
        """После санитизации статус обновляется."""
        with (
            patch("src.core.config.settings", mock_settings),
            patch("src.workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo),
            patch(
                "src.workers.pii_sanitizer.DocumentVersionRepository",
                return_value=mock_version_repo,
            ),
            patch("src.workers.pii_sanitizer.AuditRepository", return_value=mock_audit_repo),
        ):
            sanitizer = PIISanitizer(
                uow=mock_uow,
                artifact_store=mock_artifact_store,
            )
            await sanitizer.sanitize(sample_version.id)

        mock_doc_repo.update_status.assert_called_once()
        call_args = mock_doc_repo.update_status.call_args
        assert call_args.kwargs.get("doc_id") == sample_document.id
        assert call_args.kwargs.get("status") == "sanitized"

    @pytest.mark.asyncio
    async def test_version_refs_updated(
        self,
        mock_uow,
        mock_artifact_store,
        sample_document,
        sample_version,
        mock_settings,
        mock_doc_repo,
        mock_version_repo,
        mock_audit_repo,
    ):
        """После санитизации version refs обновляются."""
        with (
            patch("src.core.config.settings", mock_settings),
            patch("src.workers.pii_sanitizer.DocumentRepository", return_value=mock_doc_repo),
            patch(
                "src.workers.pii_sanitizer.DocumentVersionRepository",
                return_value=mock_version_repo,
            ),
            patch("src.workers.pii_sanitizer.AuditRepository", return_value=mock_audit_repo),
        ):
            sanitizer = PIISanitizer(
                uow=mock_uow,
                artifact_store=mock_artifact_store,
            )
            await sanitizer.sanitize(sample_version.id)

        mock_version_repo.update_refs.assert_called_once()
        assert "sanitized_ref" in mock_version_repo.update_refs.call_args.kwargs


class TestSanitizeDocumentTask:
    """Тесты Celery-таски."""

    def test_task_registered(self):
        """Таска зарегистрирована."""
        assert sanitize_document.name == "pii.sanitize_document"

    def test_task_has_retry_config(self):
        """Таска имеет конфигурацию retry."""
        assert sanitize_document.max_retries == 3
        assert sanitize_document.default_retry_delay == 60
