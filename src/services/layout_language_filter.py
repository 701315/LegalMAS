# src/services/layout_language_filter.py

"""
Layout language filter.

Фильтрует layout (text_layout_raw) до одного целевого языка.

Два режима работы:
- Простой (monolingual или короткий документ): посимвольная детекция скрипта,
  оставляем элементы целевого языка + нейтральные короткие блоки.
- Структурный (bilingual, >= 10 элементов): StructuralAnalyzer группирует
  параллельные блоки по вертикальной позиции и номерам пунктов,
  затем из каждой пары выбирается нужный язык.

Форматы:

  ВХОД (text_layout_raw):
  {
    "document_id": str,
    "document_version_id": str,
    "elements": [
      {
        "element_id": str,         # обязательно
        "text": str,               # обязательно
        "type": str,               # "text" | "heading" | "table" | ...
        "page": int,
        "bbox": [x0, y0, x1, y1],
        "clause_uid": str | None,      # может отсутствовать на этой стадии
        ...                            # любые другие поля — сохраняются as-is
      }
    ],
    "tables": [...],
    "metadata": {...}
  }

  ВЫХОД (layout_primary):
  {
    "document_id": str,
    "document_version_id": str,
    "elements": [
      {
        # Все поля оригинального элемента сохранены.
        # Добавлены/обновлены:
        "clause_uid": str | None,          # если структурный анализ нашёл номер
        "parent_clause_uid": str | None,   # если блок является телом пункта
      }
    ],
    "tables": [...],
    "metadata": {
      "language_filter": {
        "target_language": str,
        "bilingual_mode": bool,
        "structural_filter_used": bool,
        "elements_before": int,
        "elements_after": int,
        "chars_before": int,
        "chars_after": int,
        "element_retention_ratio": float,
        "char_retention_ratio": float,
        "degraded": bool,
        "degraded_reason": str | None,
      },
      "element_count": int,
      ...  # остальные поля metadata сохранены
    }
  }

  Downstream (structure_builder) ожидает из elements:
  - element_id (str)
  - text (str)
  - page (int)
  - type (str) — для распознавания heading
  - clause_uid — подсказка для построения дерева (необязательно)
  - parent_clause_uid — подсказка для построения дерева (необязательно)
"""

from __future__ import annotations

import re
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Константы детекции языка
# ---------------------------------------------------------------------------

# Порог доли символов нужного скрипта для однозначной классификации
_SCRIPT_DOMINANCE = 0.70
# Минимальное число символов скрипта для классификации (защита от "A" -> "en")
_SCRIPT_MIN_CHARS = 3
# Нейтральный блок (цифры, пунктуация) включается только если короткий
_NEUTRAL_MAX_CHARS = 40
# Минимальная длина текста для структурного анализа (чтобы не анализировать мусор)
_STRUCT_MIN_TEXT_LEN = 5
# Y-допуск при группировке параллельных блоков (пиксели/pt PDF)
_Y_TOLERANCE = 8.0
# Минимальный размер документа для включения структурного анализа
_STRUCTURAL_MIN_ELEMENTS = 10

# Пороги degraded-оценки
_MIN_ELEMENT_RETENTION_RATIO = 0.40
_MIN_CHAR_RETENTION_RATIO = 0.50

# Дополнительные эвристики очистки
_MAX_REPEATED_SYMBOL_RUN = 6

# ---------------------------------------------------------------------------
# Детекция скрипта
# ---------------------------------------------------------------------------


def _clean_artifacts(text: str) -> str:
    """
    Очистка типичных PDF/OCR/layout-артефактов перед детекцией языка.

    Не пытаемся "исправить" текст агрессивно — только убираем очевидный шум:
    - replacement chars и tofu-подобные символы;
    - zero-width chars;
    - повторяющийся мусор из пунктуации;
    - схлопываем пробелы.

    ВАЖНО: функция нужна для детекции языка и качества.
    Оригинальный текст элемента downstream не переписываем глобально.
    """
    if not text:
        return ""

    cleaned = text

    # Zero-width / soft noise
    cleaned = (
        cleaned.replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
    )

    # Частые символы деградации после неудачной конвертации/извлечения
    cleaned = cleaned.replace("�", " ")
    cleaned = cleaned.replace("■", " ")
    cleaned = cleaned.replace("□", " ")
    cleaned = cleaned.replace("▪", " ")
    cleaned = cleaned.replace("▫", " ")

    # Схлопываем длинные серии из одинаковых "шумовых" символов
    cleaned = re.sub(r"([_\-–—.=~*•·])\1{%d,}" % (_MAX_REPEATED_SYMBOL_RUN - 1), r"\1", cleaned)

    # Нормализуем пробелы
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _detect_script(text: str) -> str:
    """
    Определить доминирующий скрипт строки.

    Возвращает:
      "ru"    — доминирует кириллица
      "en"    — доминирует латиница
      "other" — нейтральный (цифры, пунктуация, пустая строка)

    ВАЖНО:
    - метод намеренно НЕ возвращает "mixed";
    - если оба скрипта присутствуют, побеждает тот, которого больше;
    - для арабского, CJK и иных письменностей текущий контракт возвращает "other",
      чтобы не ломать существующий pipeline, рассчитанный на "ru"/"en".
    """
    prepared = _clean_artifacts(text)
    if not prepared:
        return "other"

    cyr = 0
    lat = 0

    for ch in prepared:
        code = ord(ch)
        # Кириллица: основной блок + расширенный
        if 0x0400 <= code <= 0x04FF or 0x0500 <= code <= 0x052F:
            cyr += 1
        # Латиница: ASCII + Latin-1 supplement
        elif (
            0x0041 <= code <= 0x005A
            or 0x0061 <= code <= 0x007A
            or 0x00C0 <= code <= 0x00FF
        ):
            lat += 1

    total = cyr + lat
    if total == 0:
        return "other"

    if cyr >= _SCRIPT_MIN_CHARS and cyr / total >= _SCRIPT_DOMINANCE:
        return "ru"
    if lat >= _SCRIPT_MIN_CHARS and lat / total >= _SCRIPT_DOMINANCE:
        return "en"

    if cyr >= _SCRIPT_MIN_CHARS or lat >= _SCRIPT_MIN_CHARS:
        return "ru" if cyr >= lat else "en"

    return "other"


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _count_chars(text: str) -> int:
    """Число символов без пробелов и переносов, после мягкой очистки артефактов."""
    prepared = _clean_artifacts(text)
    return len(prepared.replace(" ", "").replace("\n", "")) if prepared else 0


def _should_keep_neutral(text: str) -> bool:
    """
    Нейтральный блок (числа, знаки, короткие подписи) включаем только если он короткий.
    Длинный нейтральный текст — чаще всего ошибка детекции, деградированный extraction
    или таблица/мусор без уверенного языка.
    """
    return _count_chars(text) <= _NEUTRAL_MAX_CHARS


def _safe_int_page(value: Any, default: int = 1) -> int:
    try:
        page = int(float(str(value).strip()))
        return page if page > 0 else default
    except (ValueError, TypeError, AttributeError):
        return default


def _safe_bbox(raw_bbox: Any) -> List[float]:
    """
    Нормализовать bbox к [x0, top, x1, bottom] из float.
    При проблемах возвращает [0,0,0,0].
    """
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
        return [0.0, 0.0, 0.0, 0.0]

    result: List[float] = []
    for value in raw_bbox[:4]:
        try:
            result.append(float(str(value).strip()))
        except (ValueError, TypeError, AttributeError):
            result.append(0.0)

    x0, top, x1, bottom = result
    if x1 < x0:
        x0, x1 = x1, x0
    if bottom < top:
        top, bottom = bottom, top

    return [x0, top, x1, bottom]


def _is_zero_bbox(bbox: List[float]) -> bool:
    return len(bbox) >= 4 and all(abs(v) < 1e-9 for v in bbox[:4])


def _bbox_sort_key(element: Dict[str, Any]) -> Tuple[int, float, float]:
    bbox = _safe_bbox(element.get("bbox"))
    return (
        _safe_int_page(element.get("page", 1)),
        bbox[1],
        bbox[0],
    )


# ---------------------------------------------------------------------------
# Публичные функции обнаружения языков
# ---------------------------------------------------------------------------


def detect_languages_in_layout(layout: Dict[str, Any]) -> List[str]:
    """
    Определить, какие языки реально присутствуют в layout.

    Анализирует все elements layout["elements"].
    Возвращает отсортированный список кодов языков (["en", "ru"] и т.п.).
    Если ни одного языка не обнаружено — возвращает ["ru"] как дефолт.
    """
    elements: List[Dict[str, Any]] = layout.get("elements") or []
    langs: set[str] = set()

    for el in elements:
        text = (el.get("text") or "").strip()
        if not text:
            continue
        script = _detect_script(text)
        if script in ("ru", "en"):
            langs.add(script)

    return sorted(langs) if langs else ["ru"]


# ---------------------------------------------------------------------------
# Структурный анализатор (билингвальный режим)
# ---------------------------------------------------------------------------


@dataclass
class _StructElement:
    """Внутреннее представление одного элемента layout."""
    original: Dict[str, Any]
    element_id: str
    text: str
    page: int
    bbox: List[float]
    element_type: str
    detected_lang: str         # "ru" | "en" | "other"
    clause_number: Optional[str] = None
    y_center: float = 0.0
    x_center: float = 0.0

    def __post_init__(self) -> None:
        if self.bbox and len(self.bbox) >= 4:
            try:
                floats = [float(v) for v in self.bbox[:4]]
                self.y_center = (floats[1] + floats[3]) / 2.0
                self.x_center = (floats[0] + floats[2]) / 2.0
            except (ValueError, TypeError):
                self.y_center = 0.0
                self.x_center = 0.0
        else:
            self.y_center = float("inf")
            self.x_center = 0.0


@dataclass
class _StructBlock:
    """
    Группа параллельных элементов на одной вертикальной позиции.
    Может содержать один или два языка (ru и/или en).
    """
    block_id: Optional[str]
    y_position: float
    page: int
    elements: List[_StructElement] = field(default_factory=list)
    ru_element: Optional[_StructElement] = None
    en_element: Optional[_StructElement] = None
    is_heading: bool = False

    def resolve_languages(self) -> None:
        """Выбрать по одному представителю для каждого языка."""
        ru_candidates: List[_StructElement] = []
        en_candidates: List[_StructElement] = []

        for el in self.elements:
            if el.detected_lang == "ru":
                ru_candidates.append(el)
            elif el.detected_lang == "en":
                en_candidates.append(el)

        def _best(candidates: List[_StructElement]) -> Optional[_StructElement]:
            if not candidates:
                return None
            headings = [e for e in candidates if e.element_type == "heading"]
            pool = headings if headings else candidates
            return max(pool, key=lambda e: (_count_chars(e.text), len(e.text)))

        self.ru_element = _best(ru_candidates)
        self.en_element = _best(en_candidates)

        if self.ru_element is None and self.en_element is None:
            neutral = [e for e in self.elements if e.detected_lang == "other"]
            if neutral:
                best_neutral = max(neutral, key=lambda e: (_count_chars(e.text), len(e.text)))
                self.ru_element = best_neutral
                self.en_element = best_neutral

    def get_for_language(self, lang: str) -> Optional[_StructElement]:
        """
        Вернуть элемент для целевого языка.
        Fallback: если нужного языка нет, берём другой/нейтральный.
        """
        lang = (lang or "").lower()
        if lang == "ru":
            return self.ru_element or self.en_element
        if lang == "en":
            return self.en_element or self.ru_element
        return self.ru_element or self.en_element

    @property
    def has_both_languages(self) -> bool:
        return self.ru_element is not None and self.en_element is not None


_CLAUSE_PATTERNS = [
    re.compile(r"^(\d+(?:\.\d+)*)\s*[.)]\s*(.+)?$"),
    re.compile(r"^(\d+)\s*[.)]\s*(.+)?$"),
    re.compile(r"^(I{1,3}|IV|V?I{0,3})[.)]\s*(.+)?$", re.IGNORECASE),
    re.compile(r"^([A-Fa-f])[.)]\s*(.+)?$"),
]


class _StructuralAnalyzer:
    """
    Билингвальный структурный анализатор.

    Группирует элементы layout по вертикальной позиции (page, y_center),
    выравнивает параллельные блоки по номерам пунктов,
    и для каждого блока предоставляет выбор нужного языка.
    """

    def __init__(self, y_tolerance: float = _Y_TOLERANCE):
        self.y_tolerance = y_tolerance

    def analyze(self, elements: List[Dict[str, Any]]) -> List[_StructBlock]:
        """Основная точка входа."""
        if not elements:
            return []

        struct_els = self._convert_elements(elements)
        if not struct_els:
            return []

        y_groups = self._group_by_y(struct_els)
        sorted_keys = sorted(y_groups.keys())

        blocks: List[_StructBlock] = []
        for key in sorted_keys:
            block = self._create_block(
                y_center=key[1],
                page=key[0],
                elements=y_groups[key],
            )
            if block:
                blocks.append(block)

        blocks = self._align_by_clause_numbers(blocks)
        return self._finalize_blocks(blocks)

    def _convert_elements(self, elements: List[Dict[str, Any]]) -> List[_StructElement]:
        result: List[_StructElement] = []

        for el in elements:
            raw_text = el.get("text", "")
            text = raw_text.strip()
            if len(_clean_artifacts(text)) < _STRUCT_MIN_TEXT_LEN:
                continue

            page_val = _safe_int_page(el.get("page", 1), default=1)
            safe_bbox = _safe_bbox(el.get("bbox", [0, 0, 0, 0]))

            # В structural-анализ не берём полностью нулевые bbox:
            # они создают ложные группировки в (0,0) и сильно шумят.
            if _is_zero_bbox(safe_bbox):
                continue

            el_type = str(el.get("type", "text") or "text").lower()
            detected_lang = _detect_script(text)
            clause_num = self._extract_clause_number(text, el_type)

            result.append(
                _StructElement(
                    original=el,
                    element_id=str(el.get("element_id", "")),
                    text=text,
                    page=page_val,
                    bbox=safe_bbox,
                    element_type=el_type,
                    detected_lang=detected_lang,
                    clause_number=clause_num,
                )
            )

        return result

    @staticmethod
    def _extract_clause_number(text: str, el_type: str) -> Optional[str]:
        is_heading = el_type == "heading" or text.strip().isupper()
        stripped = text.strip()

        if not is_heading:
            if not any(p.match(stripped) for p in _CLAUSE_PATTERNS):
                return None

        for pattern in _CLAUSE_PATTERNS:
            match = pattern.match(stripped)
            if match:
                return match.group(1)
        return None

    def _group_by_y(
        self,
        elements: List[_StructElement],
    ) -> Dict[Tuple[int, float], List[_StructElement]]:
        """Группировка по (page, y_center) с допуском y_tolerance."""
        groups: Dict[Tuple[int, float], List[_StructElement]] = {}
        current_key: Optional[Tuple[int, float]] = None

        sorted_els = sorted(elements, key=lambda e: (e.page, e.y_center, e.x_center))

        for el in sorted_els:
            if (
                current_key is not None
                and current_key[0] == el.page
                and abs(el.y_center - current_key[1]) <= self.y_tolerance
            ):
                groups[current_key].append(el)
            else:
                current_key = (el.page, el.y_center)
                groups[current_key] = [el]

        return groups

    def _create_block(
        self,
        y_center: float,
        page: int,
        elements: List[_StructElement],
    ) -> Optional[_StructBlock]:
        if not elements:
            return None

        block = _StructBlock(
            block_id=None,
            y_position=y_center,
            page=page,
            elements=elements,
        )
        block.resolve_languages()

        headings_with_num = [
            e for e in elements
            if e.element_type == "heading" and e.clause_number
        ]
        if headings_with_num:
            # Берём наиболее "сильный" heading как источник block_id
            best_heading = max(headings_with_num, key=lambda e: (_count_chars(e.text), len(e.text)))
            block.block_id = best_heading.clause_number
            block.is_heading = True

        return block

    def _align_by_clause_numbers(self, blocks: List[_StructBlock]) -> List[_StructBlock]:
        """
        Объединяем блоки с одинаковым block_id (номером пункта).
        Это нужно для случаев, когда параллельные блоки договора
        оказались на слегка разных y-координатах.
        """
        num_to_blocks: Dict[str, List[_StructBlock]] = {}
        unnumbered: List[_StructBlock] = []

        for block in blocks:
            if block.block_id:
                num_to_blocks.setdefault(block.block_id, []).append(block)
            else:
                unnumbered.append(block)

        merged: List[_StructBlock] = []
        for number, blks in num_to_blocks.items():
            if len(blks) == 1:
                merged.append(blks[0])
            else:
                merged.append(self._merge_blocks(number, blks))

        merged.extend(unnumbered)
        return merged

    @staticmethod
    def _merge_blocks(number: str, blocks: List[_StructBlock]) -> _StructBlock:
        avg_y = sum(b.y_position for b in blocks) / len(blocks)
        all_els = [e for b in blocks for e in b.elements]
        result = _StructBlock(
            block_id=number,
            y_position=avg_y,
            page=blocks[0].page,
            elements=all_els,
        )
        result.resolve_languages()
        result.is_heading = any(b.is_heading for b in blocks)
        return result

    @staticmethod
    def _finalize_blocks(blocks: List[_StructBlock]) -> List[_StructBlock]:
        """Сортируем и дедуплицируем элементы внутри блоков."""
        blocks.sort(key=lambda b: (b.page, b.y_position))
        seen_ids: set[str] = set()

        for block in blocks:
            unique: List[_StructElement] = []
            for element in sorted(block.elements, key=lambda e: (e.y_center, e.x_center, e.element_id)):
                dedupe_key = element.element_id or f"{element.page}:{element.bbox}:{element.text}"
                if dedupe_key not in seen_ids:
                    seen_ids.add(dedupe_key)
                    unique.append(element)
            block.elements = unique

        return blocks


# ---------------------------------------------------------------------------
# Оценка качества фильтрации
# ---------------------------------------------------------------------------


def _assess_quality(
    original: List[Dict[str, Any]],
    selected: List[Dict[str, Any]],
) -> Dict[str, Any]:
    e_b = len(original)
    e_a = len(selected)
    c_b = sum(_count_chars(el.get("text", "")) for el in original)
    c_a = sum(_count_chars(el.get("text", "")) for el in selected)

    element_retention_ratio = e_a / e_b if e_b else 0.0
    char_retention_ratio = c_a / c_b if c_b else 0.0

    degraded_reasons: List[str] = []

    if e_b > 0 and e_a == 0:
        degraded_reasons.append("no_elements_after_filter")
    if c_b > 0 and c_a == 0:
        degraded_reasons.append("no_chars_after_filter")
    if e_b >= _STRUCTURAL_MIN_ELEMENTS and element_retention_ratio < _MIN_ELEMENT_RETENTION_RATIO:
        degraded_reasons.append(
            f"low_element_retention_ratio:{element_retention_ratio:.3f}"
        )
    if c_b > 0 and char_retention_ratio < _MIN_CHAR_RETENTION_RATIO:
        degraded_reasons.append(
            f"low_char_retention_ratio:{char_retention_ratio:.3f}"
        )

    degraded = bool(degraded_reasons)

    return {
        "elements_before": e_b,
        "elements_after": e_a,
        "chars_before": c_b,
        "chars_after": c_a,
        "element_retention_ratio": element_retention_ratio,
        "char_retention_ratio": char_retention_ratio,
        "degraded": degraded,
        "degraded_reason": ";".join(degraded_reasons) if degraded_reasons else None,
    }


def _build_metadata(
    layout: Dict[str, Any],
    target: str,
    quality: Dict[str, Any],
    is_bilingual: bool = False,
    structural_filter_used: bool = False,
) -> Dict[str, Any]:
    """
    Собрать metadata для layout_primary.
    """
    base = dict(layout.get("metadata") or {})
    base["language_filter"] = {
        "target_language": target,
        "bilingual_mode": is_bilingual,
        "structural_filter_used": structural_filter_used,
        **quality,
    }
    base["element_count"] = quality["elements_after"]
    return base


# ---------------------------------------------------------------------------
# Простой фильтр (монолингвальный / short document fallback)
# ---------------------------------------------------------------------------


def _simple_filter(
    layout: Dict[str, Any],
    target: str,
    elements: List[Dict[str, Any]],
    tables: List[Any],
    is_bilingual: bool = False,
) -> Dict[str, Any]:
    """
    Простая посимвольная фильтрация по скрипту.
    """
    filtered: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for el in elements:
        text = el.get("text", "")
        lang = _detect_script(text)

        keep = False
        if lang == target:
            keep = True
        elif lang == "other" and _should_keep_neutral(text):
            keep = True

        if not keep:
            continue

        dedupe_key = str(el.get("element_id") or "") or f"{_bbox_sort_key(el)}:{text.strip()}"
        if dedupe_key in seen_ids:
            continue
        seen_ids.add(dedupe_key)
        filtered.append(el)

    filtered.sort(key=_bbox_sort_key)

    quality = _assess_quality(elements, filtered)
    metadata = _build_metadata(
        layout,
        target,
        quality,
        is_bilingual=is_bilingual,
        structural_filter_used=False,
    )

    return {
        "document_version_id": layout.get("document_version_id"),
        "document_id": layout.get("document_id"),
        "elements": filtered,
        "tables": tables,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Структурный фильтр (билингвальный режим)
# ---------------------------------------------------------------------------


def _structural_filter(
    layout: Dict[str, Any],
    target: str,
    elements: List[Dict[str, Any]],
    tables: List[Any],
) -> Dict[str, Any]:
    """
    Структурный фильтр для билингвальных документов.
    """
    analyzer = _StructuralAnalyzer()
    blocks = analyzer.analyze(elements)

    selected_elements: List[Dict[str, Any]] = []
    selected_ids: set[str] = set()
    last_heading_uid: Optional[str] = None
    bilingual_block_count = 0

    for block in blocks:
        if block.has_both_languages:
            bilingual_block_count += 1

        chosen = block.get_for_language(target)
        if not chosen:
            continue

        out = dict(chosen.original)
        out["text"] = chosen.text

        if block.is_heading and block.block_id:
            out["clause_uid"] = block.block_id
            last_heading_uid = block.block_id
        elif not block.is_heading and last_heading_uid and not out.get("parent_clause_uid"):
            out["parent_clause_uid"] = last_heading_uid

        dedupe_key = str(out.get("element_id") or "") or f"{_safe_int_page(out.get('page', 1))}:{_safe_bbox(out.get('bbox'))}:{out.get('text', '')}"
        if dedupe_key in selected_ids:
            continue

        selected_ids.add(dedupe_key)
        selected_elements.append(out)

    selected_elements.sort(key=_bbox_sort_key)

    quality = _assess_quality(elements, selected_elements)
    metadata = _build_metadata(
        layout,
        target,
        quality,
        is_bilingual=True,
        structural_filter_used=True,
    )
    metadata["language_filter"]["bilingual_blocks_found"] = bilingual_block_count
    metadata["language_filter"]["structural_blocks_total"] = len(blocks)

    return {
        "document_version_id": layout.get("document_version_id"),
        "document_id": layout.get("document_id"),
        "elements": selected_elements,
        "tables": tables,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Главная точка входа
# ---------------------------------------------------------------------------


def filter_layout_to_language(
    layout: Dict[str, Any],
    target_language: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Отфильтровать layout до одного языка.

    Аргументы:
      layout          — text_layout_raw
      target_language — "ru" или "en"
      context         — опциональный dict с ключами:
                        "is_bilingual" (bool)
                        "document_id"  (str)
                        "deal_id"      (str)

    Возвращает layout_primary.
    """
    target = (target_language or "").lower()
    if target not in ("ru", "en"):
        logger.warning(
            "filter_layout_to_language: unsupported target language, returning raw",
            target_language=target_language,
        )
        return layout

    elements: List[Dict[str, Any]] = layout.get("elements") or []
    tables: List[Any] = layout.get("tables") or []

    if not elements:
        return {
            "document_version_id": layout.get("document_version_id"),
            "document_id": layout.get("document_id"),
            "elements": [],
            "tables": tables,
            "metadata": _build_metadata(
                layout,
                target,
                _assess_quality([], []),
                is_bilingual=False,
                structural_filter_used=False,
            ),
        }

    is_bilingual = bool(context.get("is_bilingual")) if context else False
    doc_id = (context or {}).get("document_id", "unknown")

    if not is_bilingual or len(elements) < _STRUCTURAL_MIN_ELEMENTS:
        result = _simple_filter(
            layout,
            target,
            elements,
            tables,
            is_bilingual=is_bilingual,
        )
        logger.info(
            "filter_layout_to_language: simple filter applied",
            document_id=doc_id,
            target=target,
            elements_in=len(elements),
            elements_out=len(result.get("elements") or []),
            degraded=result.get("metadata", {}).get("language_filter", {}).get("degraded", False),
            degraded_reason=result.get("metadata", {}).get("language_filter", {}).get("degraded_reason"),
        )
        return result

    try:
        result = _structural_filter(layout, target, elements, tables)
        logger.info(
            "filter_layout_to_language: structural filter applied",
            document_id=doc_id,
            target=target,
            elements_in=len(elements),
            elements_out=len(result.get("elements") or []),
            bilingual_blocks=result.get("metadata", {}).get("language_filter", {}).get("bilingual_blocks_found", 0),
            degraded=result.get("metadata", {}).get("language_filter", {}).get("degraded", False),
            degraded_reason=result.get("metadata", {}).get("language_filter", {}).get("degraded_reason"),
        )
        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "filter_layout_to_language: structural filter failed, falling back to simple filter",
            document_id=doc_id,
            target=target,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        result = _simple_filter(layout, target, elements, tables, is_bilingual=True)
        logger.info(
            "filter_layout_to_language: simple fallback applied after structural failure",
            document_id=doc_id,
            target=target,
            elements_in=len(elements),
            elements_out=len(result.get("elements") or []),
            degraded=result.get("metadata", {}).get("language_filter", {}).get("degraded", False),
            degraded_reason=result.get("metadata", {}).get("language_filter", {}).get("degraded_reason"),
        )
        return result


# ---------------------------------------------------------------------------
# Удобные алиасы
# ---------------------------------------------------------------------------


def filter_layout_to_ru(layout: Dict[str, Any]) -> Dict[str, Any]:
    return filter_layout_to_language(layout, "ru")


def filter_layout_to_en(layout: Dict[str, Any]) -> Dict[str, Any]:
    return filter_layout_to_language(layout, "en")

