# src/services/structure/legal_unit_retrieval.py

from __future__ import annotations

import uuid
from typing import Any

from engine.retrieval.tokenization import count_tokens
from services.structure.legal_unit_models import LegalUnit, LegalUnitsSnapshot


def _enumish_str(value: Any) -> str | None:
    """
    Аккуратно привести enum-like / dataclass-like значение к строке.

    Поддерживает:
    - Enum.value
    - обычные строки
    - None
    """
    if value is None:
        return None

    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str) and enum_value.strip():
        return enum_value.strip()

    text = str(value).strip()
    return text or None


def _listify(value: Any) -> list[Any]:
    """
    Безопасно привести значение к list.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _resolve_retrieval_text(unit: LegalUnit) -> str:
    """
    Собрать финальный retrieval text для LLM.

    Приоритет:
    1. retrieval_text — уже готовая retrieval projection
       (обычно context_prefix + exact_text)
    2. exact_text — точный текст unit, materialized из source elements

    P8.8d:
    - own_text больше НЕ используется как fallback.
    - own_text является legacy field и может содержать sibling spill.
    - Если у unit нет retrieval_text и exact_text, такой unit не должен
      попадать в primary legal_unit retrieval corpus.
    """
    retrieval_text = getattr(unit, "retrieval_text", None)
    if isinstance(retrieval_text, str) and retrieval_text.strip():
        return retrieval_text.strip()

    exact_text = getattr(unit, "exact_text", None)
    if isinstance(exact_text, str) and exact_text.strip():
        return exact_text.strip()

    return ""


def _resolve_citability_band(unit: LegalUnit) -> str:
    """
    Достать citability_band из unit.citability если оно присутствует.
    """
    citability = getattr(unit, "citability", None)
    if citability is None:
        return "low"

    band = getattr(citability, "citability_band", None)
    if isinstance(band, str) and band.strip():
        return band.strip()

    return "low"


def _resolve_title(unit: LegalUnit) -> str | None:
    """
    Выбрать лучший заголовок unit.
    """
    title = getattr(unit, "title", None)
    if isinstance(title, str) and title.strip():
        return title.strip()

    heading_text = getattr(unit, "heading_text", None)
    if isinstance(heading_text, str) and heading_text.strip():
        return heading_text.strip()

    return None


def _resolve_element_ids(unit: LegalUnit) -> list[str]:
    """
    Выбрать element ids из наиболее вероятных полей модели.
    """
    candidates = [
        getattr(unit, "source_element_ids", None),
        getattr(unit, "own_element_ids", None),
        getattr(unit, "element_ids", None),
    ]

    for candidate in candidates:
        if isinstance(candidate, (list, tuple)):
            return [str(x) for x in candidate if str(x).strip()]

    return []


def _resolve_path_titles(unit: LegalUnit) -> list[str]:
    """
    Достать path titles если они есть в модели.
    """
    value = getattr(unit, "path_titles", None)
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _resolve_raw_uid(unit: LegalUnit) -> str | None:
    """
    LegalUnit в реальной модели хранит raw_uid, а не clause_uid.
    """
    raw_uid = getattr(unit, "raw_uid", None)
    if isinstance(raw_uid, str) and raw_uid.strip():
        return raw_uid.strip()
    return None


def _should_include_unit(unit: LegalUnit, text: str) -> bool:
    """
    Решить, должен ли unit попасть в retrieval corpus.

    Правила:
    - Unit включается только если у него есть непустой retrieval/exact text.
    - Пустой structural anchor без детей не включается.
    - Legacy own_text не считается допустимым retrieval substrate.

    P8.8d:
    - primary corpus должен строиться только из exact legal unit foundation,
      а не из старого own_text.
    """
    if not text.strip():
        return False

    unit_type = _enumish_str(getattr(unit, "unit_type", None))
    children_unit_ids = _listify(getattr(unit, "children_unit_ids", None))

    if unit_type == "structural_anchor" and not children_unit_ids:
        return False

    return True


def build_retrieval_units_from_legal_units(
    snapshot: LegalUnitsSnapshot,
    doc_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """
    Преобразовать LegalUnitsSnapshot в retrieval-visible chunk corpus.

    Выходной контракт:
    [
        {
            "id": str,
            "text": str,
            "metadata": {...}
        }
    ]

    P8.8d:
    - Это bridge между exact legal units и CHUNKS v2 retrieval corpus.
    - Эти chunks затем записываются в segment snapshot как chunks["legal_unit"].
    - Retrieval runtime читает их через ChunkCorpusReaderV2 без специальных
      reader-side преобразований.

    Важно:
    - В primary retrieval corpus включаются только units, у которых есть
      retrieval_text или exact_text.
    - legacy own_text НЕ используется как retrieval fallback, потому что
      может содержать sibling spill.
    - Функция intentionally tolerant к shape модели LegalUnit:
      использует getattr() и fallback'и только для структурных полей,
      но не для retrieval text substrate.
    """
    out: list[dict[str, Any]] = []
    str_doc_id = str(doc_id)

    snapshot_segment_id = getattr(snapshot, "segment_id", None)
    snapshot_segment_type = getattr(snapshot, "segment_type", None)
    snapshot_segment_order = getattr(snapshot, "segment_order", None)
    snapshot_is_primary = bool(getattr(snapshot, "is_primary_segment", False))

    units = _listify(getattr(snapshot, "units", None))

    for unit in units:
        if not isinstance(unit, LegalUnit):
            continue

        text = _resolve_retrieval_text(unit)
        if not _should_include_unit(unit, text):
            continue

        unit_id = getattr(unit, "unit_id", None)
        if not isinstance(unit_id, str) or not unit_id.strip():
            continue

        unit_id = unit_id.strip()
        raw_uid = _resolve_raw_uid(unit)

        unit_class = _enumish_str(getattr(unit, "unit_class", None))
        unit_type = _enumish_str(getattr(unit, "unit_type", None))

        title = _resolve_title(unit)
        path_titles = _resolve_path_titles(unit)
        element_ids = _resolve_element_ids(unit)

        page_start = getattr(unit, "page_start", None)
        page_end = getattr(unit, "page_end", None)

        parent_unit_id = getattr(unit, "parent_unit_id", None)
        children_unit_ids = _listify(getattr(unit, "children_unit_ids", None))

        context_prefix = getattr(unit, "context_prefix", None)
        if not isinstance(context_prefix, str):
            context_prefix = None

        metadata: dict[str, Any] = {
            "doc_id": str_doc_id,
            "chunk_kind": "legal_unit",
            "effective_uid": unit_id,
            "raw_uid": raw_uid,
            "scope": snapshot_segment_id,
            "unit_class": unit_class,
            "unit_type": unit_type,
            "citability": _resolve_citability_band(unit),
            "context_prefix": context_prefix,
            "level": getattr(unit, "level", None),
            "title": title,
            "path_titles": path_titles,
            "start_page": page_start,
            "end_page": page_end,
            "element_ids": element_ids,
            "token_count": count_tokens(text),
            "segment_id": snapshot_segment_id,
            "segment_type": snapshot_segment_type,
            "segment_order": snapshot_segment_order,
            "is_primary_segment": snapshot_is_primary,
            "parent_unit_id": parent_unit_id,
            "children_unit_ids": children_unit_ids,
            "retrieval_safe": True,
        }

        # Убираем пустые значения для компактности и cleanliness snapshot.
        metadata = {
            k: v
            for k, v in metadata.items()
            if v not in (None, [], {}, "")
        }

        out.append(
            {
                "id": f"{str_doc_id}:{unit_id}",
                "text": text,
                "metadata": metadata,
            }
        )

    return out


