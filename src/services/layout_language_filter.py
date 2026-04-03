# src/services/layout_language_filter.py
"""
Layout language filter.

Фильтрует layout (text_layout_raw) до одного целевого языка.

Два режима работы:
- Простой (monolingual или короткий документ): посимвольная детекция скрипта,
  оставляем элементы целевого языка + нейтральные короткие блоки.
- Структурный (bilingual, ≥10 элементов): StructuralAnalyzer группирует
  параллельные блоки по вертикальной позиции и номерам пунктов,
  затем из каждой пары выбирается нужный язык.

Форматы:

  ВХОД (text_layout_raw):
  {
    "document_id": str,
    "document_version_id": str,
    "elements": [
      {
        "element_id": str,        # обязательно
        "text": str,              # обязательно
        "type": str,              # "text" | "heading" | "table" | ...
        "page": int,
        "bbox": [x0, y0, x1, y1],
        "clause_uid": str | None,     # может отсутствовать на этой стадии
        ...                           # любые другие поля — сохраняются as-is
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
        "clause_uid": str | None,         # если структурный анализ нашёл номер
        "parent_clause_uid": str | None,  # если блок является телом пункта
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

import traceback
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Константы детекции языка
# ---------------------------------------------------------------------------

# Порог доли символов нужного скрипта для однозначной классификации
_SCRIPT_DOMINANCE = 0.70
# Минимальное число символов скрипта для классификации (защита от "A" → "en")
_SCRIPT_MIN_CHARS = 3
# Нейтральный блок (цифры, пунктуация) включается только если короткий
_NEUTRAL_MAX_CHARS = 40
# Минимальная длина текста для структурного анализа (чтобы не анализировать мусор)
_STRUCT_MIN_TEXT_LEN = 5
# Y-допуск при группировке параллельных блоков (пиксели/pt PDF)
_Y_TOLERANCE = 8.0
# Минимальный размер документа для включения структурного анализа
_STRUCTURAL_MIN_ELEMENTS = 10


# ---------------------------------------------------------------------------
# Детекция скрипта
# ---------------------------------------------------------------------------

def _detect_script(text: str) -> str:
    """
    Определить доминирующий скрипт строки.

    Возвращает:
      "ru"    — доминирует кириллица
      "en"    — доминирует латиница
      "other" — нейтральный (цифры, пунктуация, пустая строка)

    ВАЖНО: метод намеренно НЕ возвращает "mixed".
    Если оба скрипта присутствуют, побеждает тот, которого больше.
    Это позволяет корректно обработать строки вида "Griffin-Autoservice ООО"
    (название компании с латинским и кириллическим текстом).
    """
    if not text:
        return "other"

    cyr = 0
    lat = 0

    for ch in text:
        code = ord(ch)
        # Кириллица: основной блок + расширенный
        if 0x0400 <= code <= 0x04FF or 0x0500 <= code <= 0x052F:
            cyr += 1
        # Латиница: ASCII + латинское дополнение
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

    # Оба скрипта присутствуют, но ни один не доминирует.
    # Отдаём доминирующему, а не выбрасываем — см. docstring.
    if cyr >= _SCRIPT_MIN_CHARS or lat >= _SCRIPT_MIN_CHARS:
        return "ru" if cyr >= lat else "en"

    return "other"


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _count_chars(text: str) -> int:
    """Число символов без пробелов и переносов."""
    return len(text.replace(" ", "").replace("\n", "")) if text else 0


def _should_keep_neutral(text: str) -> bool:
    """
    Нейтральный блок (числа, знаки, короткие подписи) включаем только если он
    короткий — это номера пунктов, даты, подписи.
    Длинный нейтральный текст — скорее всего ошибка детекции, пропускаем.
    """
    return _count_chars(text) <= _NEUTRAL_MAX_CHARS


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
    block_id: Optional[str]     # номер пункта, если блок является заголовком
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
            # "other" добавляем к тому языку, который уже есть в блоке,
            # или оставляем для финального решения

        # Выбираем лучшего кандидата: приоритет — heading, затем самый длинный текст
        def _best(candidates: List[_StructElement]) -> Optional[_StructElement]:
            if not candidates:
                return None
            headings = [e for e in candidates if e.element_type == "heading"]
            pool = headings if headings else candidates
            return max(pool, key=lambda e: len(e.text))

        self.ru_element = _best(ru_candidates)
        self.en_element = _best(en_candidates)

        # Если блок полностью нейтральный (только "other"), назначаем его обоим языкам
        if self.ru_element is None and self.en_element is None:
            neutral = [e for e in self.elements if e.detected_lang == "other"]
            if neutral:
                best_neutral = max(neutral, key=lambda e: len(e.text))
                self.ru_element = best_neutral
                self.en_element = best_neutral

    def get_for_language(self, lang: str) -> Optional[_StructElement]:
        """
        Вернуть элемент для целевого языка.
        Fallback: если нужного языка нет, берём другой (нейтральный контент).
        """
        lang = lang.lower()
        if lang == "ru":
            return self.ru_element or self.en_element
        if lang == "en":
            return self.en_element or self.ru_element
        return self.ru_element or self.en_element

    @property
    def has_both_languages(self) -> bool:
        return self.ru_element is not None and self.en_element is not None


# Паттерны для распознавания номеров пунктов в заголовках
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
        sorted_keys = sorted(y_groups.keys())  # (int, float) — безопасная сортировка

        blocks: List[_StructBlock] = []
        for key in sorted_keys:
            block = self._create_block(y_center=key[1], page=key[0], elements=y_groups[key])
            if block:
                blocks.append(block)

        blocks = self._align_by_clause_numbers(blocks)
        return self._finalize_blocks(blocks)

    def _convert_elements(self, elements: List[Dict[str, Any]]) -> List[_StructElement]:
        result: List[_StructElement] = []
        for el in elements:
            text = el.get("text", "")
            if len(text) < _STRUCT_MIN_TEXT_LEN:
                continue

            # Агрессивное приведение типов — page всегда int
            raw_page = el.get("page", 1)
            try:
                page_val = int(float(str(raw_page).strip()))
            except (ValueError, TypeError, AttributeError):
                page_val = 1

            # bbox всегда list[float]
            raw_bbox = el.get("bbox", [0, 0, 0, 0])
            safe_bbox: List[float] = [0.0, 0.0, 0.0, 0.0]
            try:
                if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
                    safe_bbox = [float(str(v).strip()) for v in raw_bbox[:4]]
            except (ValueError, TypeError, AttributeError):
                pass

            el_type = el.get("type", "text")
            detected_lang = _detect_script(text)
            clause_num = self._extract_clause_number(text, el_type)

            result.append(_StructElement(
                original=el,
                element_id=str(el.get("element_id", "")),
                text=text,
                page=page_val,
                bbox=safe_bbox,
                element_type=el_type,
                detected_lang=detected_lang,
                clause_number=clause_num,
            ))
        return result

    @staticmethod
    def _extract_clause_number(text: str, el_type: str) -> Optional[str]:
        is_heading = el_type == "heading" or text.strip().isupper()
        stripped = text.strip()
        if not is_heading:
            # Для не-заголовков проверяем только если строка начинается как пункт
            if not any(p.match(stripped) for p in _CLAUSE_PATTERNS):
                return None
        for pattern in _CLAUSE_PATTERNS:
            m = pattern.match(stripped)
            if m:
                return m.group(1)
        return None

    def _group_by_y(
        self, elements: List[_StructElement]
    ) -> Dict[Tuple[int, float], List[_StructElement]]:
        """Группировка по (page, y_center) с допуском y_tolerance."""
        groups: Dict[Tuple[int, float], List[_StructElement]] = {}
        current_key: Optional[Tuple[int, float]] = None

        sorted_els = sorted(elements, key=lambda e: (e.page, e.y_center))

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

        # Блок является заголовком если есть heading-элемент с номером пункта
        headings_with_num = [
            e for e in elements
            if e.element_type == "heading" and e.clause_number
        ]
        if headings_with_num:
            block.block_id = headings_with_num[0].clause_number
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

        for b in blocks:
            if b.block_id:
                num_to_blocks.setdefault(b.block_id, []).append(b)
            else:
                unnumbered.append(b)

        merged: List[_StructBlock] = []
        for num, blks in num_to_blocks.items():
            if len(blks) == 1:
                merged.append(blks[0])
            else:
                merged.append(self._merge_blocks(num, blks))

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
        for b in blocks:
            unique: List[_StructElement] = []
            for e in b.elements:
                if e.element_id not in seen_ids:
                    seen_ids.add(e.element_id)
                    unique.append(e)
            b.elements = unique
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

    return {
        "elements_before": e_b,
        "elements_after": e_a,
        "chars_before": c_b,
        "chars_after": c_a,
        "element_retention_ratio": e_a / e_b if e_b else 0.0,
        "char_retention_ratio": c_a / c_b if c_b else 0.0,
        "degraded": False,
        "degraded_reason": None,
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

    Добавляем language_filter секцию с флагами bilingual_mode и
    structural_filter_used — они используются в extract_worker для
    корректного выбора порогов degraded, и в structure_builder для
    понимания что уже сделано.
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

    Правила:
    - Элемент целевого языка → включаем всегда.
    - Нейтральный "other" → включаем только если текст короткий
      (_NEUTRAL_MAX_CHARS). Длинный нейтральный = ошибка детекции, пропускаем.
    - НЕ включаем элементы другого языка (ни при каких условиях).

    ВАЖНО: "mixed" здесь не возникает, т.к. _detect_script больше не
    возвращает "mixed" — он всегда разрешает в один из языков или "other".
    """
    filtered: List[Dict[str, Any]] = []

    for el in elements:
        text = el.get("text", "")
        lang = _detect_script(text)

        if lang == target:
            filtered.append(el)
        elif lang == "other" and _should_keep_neutral(text):
            # Нейтральные короткие блоки (номера, даты, подписи) включаем
            filtered.append(el)
        # lang == другой язык → пропускаем

    quality = _assess_quality(elements, filtered)
    metadata = _build_metadata(
        layout, target, quality,
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

    Использует _StructuralAnalyzer для группировки параллельных блоков
    и выбора нужного языка из каждой пары.

    Добавляет к каждому элементу:
    - clause_uid — если блок является заголовком пункта
    - parent_clause_uid — если блок является телом пункта

    Эти поля используются structure_builder как подсказки при построении
    clause_tree, что резко улучшает качество структуры.
    """
    analyzer = _StructuralAnalyzer()
    blocks = analyzer.analyze(elements)

    selected_elements: List[Dict[str, Any]] = []
    last_heading_uid: Optional[str] = None
    bilingual_block_count = 0

    for block in blocks:
        if block.has_both_languages:
            bilingual_block_count += 1

        chosen = block.get_for_language(target)
        if not chosen:
            continue

        # Копируем оригинальный элемент (сохраняем все поля)
        out = dict(chosen.original)
        out["text"] = chosen.text

        # Добавляем структурные подсказки
        if block.is_heading and block.block_id:
            out["clause_uid"] = block.block_id
            last_heading_uid = block.block_id
        elif not block.is_heading and last_heading_uid:
            out["parent_clause_uid"] = last_heading_uid

        selected_elements.append(out)

    # Сортируем по странице и y-позиции
    selected_elements.sort(
        key=lambda e: (
            e.get("page", 1),
            (e.get("bbox") or [0, 0, 0, 0])[1],
        )
    )

    quality = _assess_quality(elements, selected_elements)
    metadata = _build_metadata(
        layout, target, quality,
        is_bilingual=True,
        structural_filter_used=True,
    )
    # Добавляем статистику билингвальности для диагностики
    metadata["language_filter"]["bilingual_blocks_found"] = bilingual_block_count

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
      layout          — text_layout_raw (см. формат выше)
      target_language — "ru" или "en"
      context         — опциональный dict с ключами:
                        "is_bilingual" (bool) — флаг из extract_worker
                        "document_id"  (str)  — для логов
                        "deal_id"      (str)  — для логов

    Возвращает layout_primary (см. формат выше).
    """
    target = (target_language or "").lower()
    if target not in ("ru", "en"):
        # Неизвестный язык — возвращаем как есть, не ломаем пайплайн
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
                layout, target,
                _assess_quality([], []),
                is_bilingual=False,
                structural_filter_used=False,
            ),
        }

    is_bilingual = bool(context.get("is_bilingual")) if context else False
    doc_id = (context or {}).get("document_id", "unknown")

    # Для коротких документов или мономодальных — простой фильтр без анализа
    if not is_bilingual or len(elements) < _STRUCTURAL_MIN_ELEMENTS:
        return _simple_filter(layout, target, elements, tables, is_bilingual=is_bilingual)

    # Билингвальный режим — пробуем структурный анализ
    try:
        result = _structural_filter(layout, target, elements, tables)
        logger.info(
            "filter_layout_to_language: structural filter applied",
            document_id=doc_id,
            target=target,
            elements_in=len(elements),
            elements_out=len(result.get("elements") or []),
            bilingual_blocks=result.get("metadata", {})
                .get("language_filter", {})
                .get("bilingual_blocks_found", 0),
        )
        return result

    except Exception as exc:  # noqa: BLE001
        # Структурный анализ упал — fallback на простой фильтр.
        # Логируем полный traceback чтобы понять причину.
        logger.warning(
            "filter_layout_to_language: structural filter failed, "
            "falling back to simple filter",
            document_id=doc_id,
            target=target,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return _simple_filter(layout, target, elements, tables, is_bilingual=True)


# ---------------------------------------------------------------------------
# Удобные алиасы
# ---------------------------------------------------------------------------

def filter_layout_to_ru(layout: Dict[str, Any]) -> Dict[str, Any]:
    return filter_layout_to_language(layout, "ru")


def filter_layout_to_en(layout: Dict[str, Any]) -> Dict[str, Any]:
    return filter_layout_to_language(layout, "en")

