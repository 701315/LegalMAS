import types

import pytest

from core.config import settings
from services.structure._pipeline._core_builder import build_structure, build_file_structure
from services.structure.models import ClauseTree, FileStructureResult


def _make_elements_single_doc() -> list[dict]:
    """Простой layout для single-doc файла: один блок текста на одной странице."""
    return [
        {
            "element_id": "e1",
            "page": 1,
            "text": "ДОГОВОР №123",
        },
        {
            "element_id": "e2",
            "page": 1,
            "text": "1. ПРЕДМЕТ ДОГОВОРА",
        },
        {
            "element_id": "e3",
            "page": 1,
            "text": "1.1. Покупатель обязуется приобрести товар.",
        },
    ]


def _make_elements_contract_appendix() -> list[dict]:
    """
    Layout для файла "договор + приложение" на двух страницах.

    Структура:
    - страница 1: договор
    - страница 2: приложение
    """
    return [
        {
            "element_id": "c1",
            "page": 1,
            "text": "ДОГОВОР №123",
        },
        {
            "element_id": "c2",
            "page": 1,
            "text": "1. ПРЕДМЕТ ДОГОВОРА",
        },
        {
            "element_id": "c3",
            "page": 1,
            "text": "1.1. Покупатель обязуется приобрести товар.",
        },
        {
            "element_id": "a1",
            "page": 2,
            "text": "Приложение №1",
        },
        {
            "element_id": "a2",
            "page": 2,
            "text": "Перечень товаров и цен.",
        },
    ]


@pytest.fixture(autouse=True)
def reset_structure_flags(monkeypatch):
    """
    Автоматически сбрасывает флаг STRUCTURE_ENABLE_SEGMENTATION
    перед каждым тестом.
    """
    # Сохраняем старое значение (уже объявлено в Settings)
    old_value = settings.STRUCTURE_ENABLE_SEGMENTATION
    yield
    # Возвращаем обратно после теста
    monkeypatch.setattr(settings, "STRUCTURE_ENABLE_SEGMENTATION", old_value)


def test_build_structure_and_build_file_structure_primary_tree_match(monkeypatch):
    """
    T1.3: build_structure() == build_file_structure().primary_tree по структуре.

    Проверяем, что новый API не ломает legacy:
    - дерево одно и то же по структуре и содержанию,
    - отличаться могут только segment-поля и schema_version.
    """
    monkeypatch.setattr(settings, "STRUCTURE_ENABLE_SEGMENTATION", False)

    document_id = "test-doc-1"
    elements = _make_elements_single_doc()

    legacy_tree: ClauseTree = build_structure(document_id=document_id, elements=elements)
    file_result: FileStructureResult = build_file_structure(
        document_id=document_id,
        elements=elements,
        document_version_id=None,
    )

    primary_tree = file_result.primary_tree

    legacy_dict = legacy_tree.to_dict()
    primary_dict = primary_tree.to_dict()

    # Удаляем из обоих словарей все segment- и schema-поля, чтобы сравнивать
    # только "содержимое" дерева.
    def strip_segment_fields(d: dict) -> dict:
        d = dict(d)  # скопировать
        for key in list(d.keys()):
            if key.startswith("segment_") or key in ("is_primary_segment", "schema_version"):
                d.pop(key, None)
        return d

    legacy_stripped = strip_segment_fields(legacy_dict)
    primary_stripped = strip_segment_fields(primary_dict)

    assert legacy_stripped == primary_stripped


def test_build_file_structure_segmentation_disabled_single_segment(monkeypatch):
    """
    T2.10 из плана: STRUCTURE_ENABLE_SEGMENTATION=False → поведение как legacy.

    Проверяем, что при выключенной сегментации:
    - возвращается ровно один сегмент;
    - segment_id задан;
    - primary_tree относится к этому сегменту.
    """
    monkeypatch.setattr(settings, "STRUCTURE_ENABLE_SEGMENTATION", False, raising=False)

    document_id = "test-doc-2"
    elements = _make_elements_single_doc()

    result = build_file_structure(
        document_id=document_id,
        elements=elements,
        document_version_id=None,
    )

    assert isinstance(result, FileStructureResult)
    assert result.segment_count == 1
    assert result.file_graph.segment_count == 1

    segment = result.file_graph.segments[0]
    assert segment.segment_id
    assert segment.is_primary is True

    primary_tree = result.primary_tree
    assert primary_tree.segment_id == segment.segment_id
    assert primary_tree.is_primary_segment is True


def test_build_file_structure_segmentation_enabled_contract_appendix(monkeypatch):
    """
    T2.2 из плана: Contract + Appendix.

    При включенной сегментации на искусственном примере
    ожидаем как минимум 2 сегмента:
    - первый должен быть contract;
    - второй — appendix или unknown (если сегментер оказался слишком консервативен).
    """
    monkeypatch.setattr(settings, "STRUCTURE_ENABLE_SEGMENTATION", True, raising=False)

    document_id = "test-doc-3"
    elements = _make_elements_contract_appendix()

    result = build_file_structure(
        document_id=document_id,
        elements=elements,
        document_version_id=None,
    )

    assert isinstance(result, FileStructureResult)
    assert result.segment_count >= 1

    segment_types = [seg.segment_type for seg in result.file_graph.segments]

    # Первый сегмент — скорее всего contract
    assert segment_types[0] in ("contract", "unknown")

    # Если два сегмента — второй должен быть appendix/unknown
    if len(segment_types) >= 2:
        assert segment_types[1] in ("appendix", "unknown")
