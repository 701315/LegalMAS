"""Stage 8 Integration Tests: Stage 7 → Runner."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.runner import Runner
from src.db.repositories.runner_repo import RunnerRepository
from src.classifiers.hybrid_classifier import HybridClassifier


@pytest.mark.asyncio
async def test_runner_calls_repository_with_deal_id(monkeypatch):
    """Runner вызывает RunnerRepository.get_non_duplicate_docs с указанным deal_id."""

    session = AsyncMock()

    # Подменяем RunnerRepository на мок
    fake_repo = MagicMock(spec=RunnerRepository)
    fake_repo.get_non_duplicate_docs = AsyncMock(return_value=[])
    monkeypatch.setattr("src.engine.runner.RunnerRepository", lambda s: fake_repo)

    # Подменяем HybridClassifier, чтобы не тянуть реальные зависимости
    fake_classifier = MagicMock(spec=HybridClassifier)
    fake_classifier.classify = AsyncMock()
    monkeypatch.setattr("src.engine.runner.HybridClassifier", lambda *a, **k: fake_classifier)

    runner = Runner(session)
    await runner.run_deal("deal123")

    fake_repo.get_non_duplicate_docs.assert_awaited_once_with("deal123")
    fake_classifier.classify.assert_not_awaited()  # нет документов → нет вызовов


@pytest.mark.asyncio
async def test_runner_updates_document_fields(monkeypatch):
    """Runner обновляет поля документа из результата HybridClassifier."""

    # 1. Фейковый документ
    fake_doc = MagicMock()
    fake_doc.id = "doc123"
    fake_doc.text = "some contract text"
    fake_doc.text_sanitized = "some sanitized text"
    fake_doc.filename = "contract.pdf"
    fake_doc.folder_path = "02.Contracts/"

    # 2. Мокаем RunnerRepository.get_non_duplicate_docs
    fake_repo = MagicMock(spec=RunnerRepository)
    fake_repo.get_non_duplicate_docs = AsyncMock(return_value=[fake_doc])
    monkeypatch.setattr("src.engine.runner.RunnerRepository", lambda s: fake_repo)

    # 3. Мокаем HybridClassifier.classify
    fake_classification = MagicMock()
    fake_classification.doctype = "SPA"
    fake_classification.confidence = 0.95
    fake_classification.level.value = "L3"
    fake_classification.details = {"levels_tried": ["L1", "L2", "L3"]}
    fake_classification.applicable_triggers = ["change_of_control"]

    fake_classifier = MagicMock(spec=HybridClassifier)
    fake_classifier.classify = AsyncMock(return_value=fake_classification)
    monkeypatch.setattr("src.engine.runner.HybridClassifier", lambda *a, **k: fake_classifier)

    # 4. Мокаем AsyncSession
    session = AsyncMock()

    runner = Runner(session)
    result = await runner.run_deal("deal123")

    # Проверяем, что поля документа проставлены
    assert fake_doc.doc_type == "SPA"
    assert fake_doc.classification_confidence == 0.95
    assert fake_doc.classification_level == "L3"
    assert fake_doc.classification_details == fake_classification.details
    assert fake_doc.applicable_triggers == ["change_of_control"]

    # Документ должен быть добавлен в сессию
    session.add.assert_called_with(fake_doc)

    # Агрегированные результаты
    assert result["processed_docs"] == 1
    assert result["classified_docs"] == 1
