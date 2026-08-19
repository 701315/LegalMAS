# src/services/multilingual/models.py

"""
Dataclasses для multilingual pipeline (Итерация 1, v3).

Принципы дизайна:
─────────────────
1. Frozen dataclasses для неизменяемых примитивов (BBox, NormalizationHints)
   — защита от случайной мутации в pipeline.

2. Обычные dataclasses для объектов, которые дополняются несколькими слоями
   (LanguageSegment: Layer 2 создаёт, Layer 3 добавляет language,
    Layer 5 добавляет visibility). Мутация явная и локализована в каждом слое.

3. Все ID — строки, не UUID. Причина: segment_id строится как
   "seg_{element_id}_{sub_index}", что удобнее для отладки.

4. BBox хранит координаты pdfplumber: [x0, top, x1, bottom].
   top — расстояние от верхнего края страницы.
   Этот формат используется во всём pipeline, включая existing _safe_bbox() утилиты.

5. OutputElement и PipelineResult — JSON-ready:
   bbox как list[float], detection_metadata как dict.
   Совместимо с существующим classify_elements.

6. Три типа Group: ParallelGroup, OrphanGroup, MonolingualGroup.
   MonolingualGroup нужен чтобы монолингвальные страницы не засоряли
   orphan_ratio метрику.

7. Visibility — строковый enum из 5 значений:
   visible | hidden | visible_orphan_target | visible_orphan_foreign | visible_ambiguous.
   Читается в JSON без декодирования.

8. LanguageSegment (multilingual pipeline) НЕ путать с SegmentDocument
   (existing structure pipeline). Разные уровни абстракции:
   - SegmentDocument — логический раздел документа (10-100 на документ)
   - LanguageSegment — атомарная языковая единица (1000-10000 на документ)

Совместимость с существующим кодом:
────────────────────────────────────
- BBox.to_list() → list[float]: совместим с _safe_bbox() и primary_pdf_builder
- OutputElement — drop-in replacement для существующего layout_primary element
- analysis_source_kind = "canonical_filtered_layout_v2" — новая версия
- language_filter dict в PipelineMetadata сохраняет backward compatibility
  с полями contract_version, downstream_requires_primary_source

Ключевые архитектурные решения (v3):
─────────────────────────────────────
- Cross-language anchor нормализация делается в alignment_helpers.py,
  не в моделях. Модели хранят только исходный anchor_uid.
- split_from_single_element pair'ы matchятся через alignment_method=
  "coordinate_columns" с confidence=1.0. Отдельный метод не нужен.
- Scope tracking делается в Layer 4, не хранится в моделях сегментов.
- Hidden elements хранят максимальный контекст в detection_metadata.
- filter_visible_elements реализован как метод PipelineResult.to_monolingual_layout().
- MIN_TARGET_LANGUAGE_RATIO = 0.15 сохраняется как есть, настраивается через settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Константы схемы
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "primary_layout/v2"
"""
Версия схемы layout_primary_v2.json.
Extract_worker и другие consumers проверяют это значение для routing.
"""

ANALYSIS_SOURCE_KIND = "canonical_filtered_layout_v2"
"""
Значение поля metadata.language_filter.analysis_source_kind.
Отличает multilingual pipeline output от legacy layout_primary.
"""

# ---------------------------------------------------------------------------
# Типы-алиасы для читаемости
# ---------------------------------------------------------------------------

LanguageCode = str
"""
Язык сегмента.
ISO 639-1 код ("ru", "en", "ar", "fr") или специальная метка:
- "structured_data" — SWIFT/IBAN/email/phone (bypass)
- "neutral"         — только цифры/пунктуация без букв
- "mixed"           — два+ языков внутри одного сегмента
- "unknown"         — не удалось определить
"""

ScriptCode = str
"""
Тип письменности.
"cyrillic" | "latin" | "arabic" | "hebrew" | "cjk" | "devanagari" | "other"
"""

DetectionMethod = str
"""
Метод определения языка.
"lingua"                    — через lingua-language-detector
"script_only"               — только по Unicode range (быстрый путь)
"neighbor_inheritance"      — унаследовано от соседей (низкая уверенность)
"structured_data_bypass"    — SWIFT/IBAN/email (не язык, технический код)
"neutral_bypass"            — только цифры/пунктуация
"too_short"                 — текст слишком короткий для надёжного detection
"""

SplitReason = Literal[
    "explicit_separator",       # разделитель "/", "\", "|" с пробелами
    "script_boundary",          # переход между скриптами без разделителя
    "digit_letter_boundary",    # "13.Land" без пробела на границе цифра-буква
    "none",                     # не разбивался — sub_index всегда 0
]
"""Причина разбивки элемента на LanguageSegments."""

BboxSplitMethod = Literal[
    "original",                 # bbox не менялся (элемент не split)
    "proportional",             # bbox вычислен пропорционально длине текста
    "separator_position",       # bbox вычислен по позиции separator'а (более точно)
]
"""Как был вычислен bbox сегмента после split."""

PageLayoutType = Literal[
    "parallel_columns",         # EN слева, RU справа (две колонки)
    "interleaved_lines",        # EN и RU строки чередуются
    "stacked_pairs",            # EN+RU в паре, EN сверху
    "stacked_blocks",           # большой EN блок, потом большой RU блок
    "monolingual",              # только один язык
    "table_page",               # страница содержит только таблицу
    "empty",                    # пустая страница
    "unknown",                  # не удалось классифицировать
]
"""Тип layout страницы документа."""

VisibilityStatus = Literal[
    "visible",                  # target язык — показываем
    "hidden",                   # скрыт, есть перевод на target
    "visible_orphan_target",    # target язык без пары
    "visible_orphan_foreign",   # чужой язык без пары (нет перевода на target)
    "visible_ambiguous",        # mixed/unknown, показываем с флагом
]
"""Видимость сегмента в финальном output."""

AlignmentMethod = Literal[
    "structural_anchor",        # по нормализованному номеру клаузы
    "coordinate_columns",       # по X координатам (включая split-siblings)
    "stacked_cells",            # вертикальное соседство
    "interleaved_lines",        # чередование в reading order
    "positional_sequential",    # позиционное pairing внутри блоков
    "monolingual",              # нет пары — монолингвальный сегмент
]
"""Метод которым была найдена пара для alignment."""


# ---------------------------------------------------------------------------
# БЛОК 1: Примитивы
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BBox:
    """
    Bounding box в координатах pdfplumber.

    x0, top — верхний левый угол.
    x1, bottom — нижний правый угол.

    top — расстояние от верхнего края страницы (не от нижнего).
    Это соглашение pdfplumber, отличающееся от ReportLab где (0,0) внизу.

    Для непрофессионального программиста:
    - представьте страницу как экран браузера, где y=0 вверху;
    - top=50 означает "50 пунктов от верха страницы";
    - bottom > top всегда.

    Frozen: BBox не мутирует после создания. Для нового bbox — создать новый объект.
    """

    x0: float
    top: float
    x1: float
    bottom: float

    def __post_init__(self) -> None:
        # Нормализация инвертированных координат через object.__setattr__
        # потому что frozen=True запрещает прямое присвоение.
        #
        # ВАЖНО: сохраняем исходные значения в локальных переменных ДО присваивания.
        # object.__setattr__ мутирует self немедленно, поэтому если сначала записать
        # self.x0 = self.x1, то следующий self.x1 = self.x0 прочитает уже
        # обновлённое значение и swap не сработает.
        if self.x1 < self.x0:
            original_x0 = self.x0
            original_x1 = self.x1
            object.__setattr__(self, "x0", original_x1)
            object.__setattr__(self, "x1", original_x0)
        if self.bottom < self.top:
            original_top = self.top
            original_bottom = self.bottom
            object.__setattr__(self, "top", original_bottom)
            object.__setattr__(self, "bottom", original_top)

    @classmethod
    def from_list(cls, lst: list[Any] | tuple[Any, ...] | None) -> "BBox":
        """
        Создать BBox из списка [x0, top, x1, bottom].
        Невалидные значения заменяются нулями — метод никогда не падает.
        Совместим с существующим _safe_bbox() поведением.
        """
        if not lst or len(lst) < 4:
            return cls(0.0, 0.0, 0.0, 0.0)
        coords: list[float] = []
        for v in lst[:4]:
            try:
                coords.append(float(v))
            except (TypeError, ValueError):
                coords.append(0.0)
        return cls(*coords)

    def to_list(self) -> list[float]:
        """Вернуть [x0, top, x1, bottom] — формат для JSON и existing утилит."""
        return [self.x0, self.top, self.x1, self.bottom]

    @property
    def y_center(self) -> float:
        """Центр по вертикали. Используется для alignment и grouping."""
        return (self.top + self.bottom) / 2.0

    @property
    def x_center(self) -> float:
        """Центр по горизонтали. Используется для column detection."""
        return (self.x0 + self.x1) / 2.0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def is_zero(self) -> bool:
        """True если bbox нулевой или вырожденный."""
        return self.width < 1e-9 and self.height < 1e-9


# ---------------------------------------------------------------------------
# БЛОК 2: Layer 1 — Normalization
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizationHints:
    """
    Результат анализа элемента Layer 1 (Normalization).

    Каждое поле — это подсказка для Layer 2 (Segmentation) о том,
    как разбить элемент на LanguageSegments.

    Для непрофессионального программиста:
    - Layer 1 не разбивает текст — он только помечает где разбивать.
    - Если script_boundary_detected=True на позиции 15 — значит
      на позиции 15 кириллица переходит в латиницу (или наоборот).
    - Layer 2 смотрит на эти позиции и решает: разбивать или нет.

    Frozen: Layer 1 создаёт hints один раз, Layer 2 их читает но не меняет.

    Позиции — exact character positions:
    - script_boundary_positions[i] = позиция символа откуда начинается
      новый скрипт. text[:pos] содержит один скрипт, text[pos:] — другой.
    - explicit_separator_positions[i] = позиция самого символа разделителя.
      text[:pos] = левая часть, text[pos+1:] = правая часть.

    Primary vs secondary signals:
    - script_boundary — PRIMARY signal (покрывает 90% случаев)
    - explicit_separator — SECONDARY signal (более точная позиция когда есть)
    - digit_letter_boundary — TERTIARY signal (редкие случаи)
    """

    source_element_id: str

    # ── PRIMARY: Script boundaries ────────────────────────────────────────────
    # Переходы между письменностями внутри текста.
    # Пример: "TABLE OF CONTENTS / СОДЕРЖАНИЕTABLE OF CONTENTS"
    # → boundary на позиции 18 (перед "СОДЕРЖАНИЕ"), 30 (перед "TABLE")
    script_boundary_detected: bool
    script_boundary_positions: tuple[int, ...]

    # ── SECONDARY: Explicit separators ────────────────────────────────────────
    # Разделители языков: "/", "\", "|", "\t".
    # Обязательно окружены пробелами (или на границе строки) И
    # обязательно с разными скриптами по бокам.
    # Пример: "APPENDICES / ПРИЛОЖЕНИЯ" — separator "/" на позиции 10
    explicit_separator_detected: str | None
    explicit_separator_positions: tuple[int, ...]

    # ── TERTIARY: Digit-letter boundaries ─────────────────────────────────────
    # Артефакт PDF extraction: цифра прилипла к букве.
    # Пример: "1. DEFINITIONS 1 ОПРЕДЕЛЕНИЯ"
    # → boundary после "DEFINITIONS" перед "1" (позиция 14)
    digit_letter_boundary_detected: bool
    digit_letter_boundary_positions: tuple[int, ...]

    # ── Table cell info ───────────────────────────────────────────────────────
    is_table_cell: bool
    cell_position: tuple[int, int] | None     # (row, col) начиная с 0

    # ── Cleanup info ──────────────────────────────────────────────────────────
    has_zero_width_chars: bool                # были ли zero-width удалены
    cleaned_text: str                         # текст после _clean_artifacts()

    @property
    def needs_split(self) -> bool:
        """
        True если хотя бы одна причина split обнаружена.
        Layer 2 использует это как быстрый фильтр перед детальным анализом.
        """
        return (
            self.script_boundary_detected
            or self.explicit_separator_detected is not None
            or self.digit_letter_boundary_detected
        )

    @property
    def all_split_positions(self) -> tuple[int, ...]:
        """
        Все обнаруженные позиции split, отсортированные и дедуплицированные.
        Layer 2 использует их для multi-split (если элемент содержит >2 языков).
        """
        positions: set[int] = set()
        positions.update(self.script_boundary_positions)
        positions.update(self.explicit_separator_positions)
        positions.update(self.digit_letter_boundary_positions)
        return tuple(sorted(positions))


# ---------------------------------------------------------------------------
# БЛОК 3: Layer 2 — Segmentation
# ---------------------------------------------------------------------------


@dataclass
class LanguageSegment:
    """
    Атомарная языковая единица после Layer 2 (Segmentation).

    ВАЖНО: LanguageSegment ≠ SegmentDocument.
    - SegmentDocument (existing) — логический раздел документа (10-100 на документ)
    - LanguageSegment (multilingual) — языковая единица (1000-10000 на документ)

    Может быть:
    - целым элементом из raw_layout (sub_index=0, split_reason="none")
    - частью элемента после split (sub_index=1,2,..., split_reason указана)

    Жизненный цикл полей:
    - Layer 2 заполняет: все поля кроме language/visibility групп
    - Layer 3 заполняет: language, script, detection_confidence, detection_method,
                         is_reliable
    - Layer 5 заполняет: visibility, hidden_reason, translation_of,
                         is_orphan_target, is_orphan_foreign, is_ambiguous,
                         orphan_display_prefix, translation_pair_confidence,
                         translation_language, parallel_group_id

    LOSSLESS инвариант:
    - text содержит исходный текст (или под-текст) БЕЗ изменений
    - никакой слой не имеет права изменять text после создания
    - при split: original.text.strip() == " ".join(seg.text.strip() for seg in segments).strip()

    Bbox invariants:
    - bbox_is_approximate=False только когда split_reason="none"
    - bbox_split_method="original" ↔ bbox_is_approximate=False
    - для split сегментов bbox всегда is_approximate=True
    """

    # ── Идентификация ────────────────────────────────────────────────────────
    segment_id: str
    """
    Формат: "seg_{source_element_id}_{sub_index}"
    Пример: "seg_e3a9f12b45_0", "seg_e3a9f12b45_1"
    Детерминированный — один и тот же input даёт тот же segment_id.
    """

    source_element_id: str
    """element_id из raw_layout"""

    sub_index: int
    """0 если элемент не разбивался; 1, 2, ... для частей после split"""

    # ── Текст и позиция ──────────────────────────────────────────────────────
    text: str
    """LOSSLESS: исходный текст элемента или под-строка (при split)"""

    page: int
    """Номер страницы, начиная с 1"""

    bbox: BBox
    """Bounding box сегмента (оригинальный или вычисленный)"""

    bbox_is_approximate: bool
    """
    True если bbox был вычислен после split (не оригинальный из pdfplumber).
    Downstream может использовать это для decision making:
    если True, не полагаться на точность координат для критичных решений.
    """

    bbox_split_method: BboxSplitMethod
    """Как был вычислен bbox после split."""

    reading_order_raw: int
    """
    Исходный reading_order из raw_layout или позиция по (page, top, x0).
    Layer 6 пересчитает финальный reading_order с учётом split.
    """

    # ── Структурная информация ───────────────────────────────────────────────
    anchor_uid: str | None
    """
    Извлечённый anchor uid через существующую parse_raw_heading /
    extract_appendix_number.
    Примеры: "1", "1.1", "appendix-1", "приложение-1"
    None если сегмент не содержит anchor'а.

    Layer 4 alignment использует cross_language_anchor_key() из
    alignment_helpers.py для нормализации перед matching.
    """

    is_table_cell: bool
    cell_position: tuple[int, int] | None     # (row, col)

    source_element_type: str
    """
    "heading" | "text" — raw hint from PDF extraction.
    NOT authoritative — DOCX ставит "heading" на любой bold текст.
    Существующий classify_elements пересчитает семантику через свою логику.
    """

    split_reason: SplitReason
    """Причина создания этого сегмента (или "none" если не разбивался)"""

    split_confidence: float
    """
    Уверенность в правильности split (0.0-1.0).
    Значения:
    - 1.0 если split_reason="none" (не разбивался — гарантированно корректен)
    - 0.95 для explicit_separator с разными скриптами по бокам
    - 0.90 для script_boundary с длинными фрагментами (>10 символов каждый)
    - 0.60-0.80 для маргинальных случаев
    Layer 4 и Layer 5 могут использовать для decision making.
    """

    # ── Layer 3: Language classification ─────────────────────────────────────
    # Заполняется Layer 3, defaults до обработки

    language: LanguageCode = "unknown"
    """ISO 639-1 код или специальная метка (structured_data, neutral, mixed, unknown)"""

    script: ScriptCode = "other"

    detection_confidence: float = 0.0

    detection_method: DetectionMethod = "too_short"

    is_reliable: bool = False
    """True если detection_confidence >= threshold и метод надёжный"""

    # ── Layer 5: Visibility selection ────────────────────────────────────────
    # Заполняется Layer 5, defaults до обработки

    visibility: VisibilityStatus = "visible"

    hidden_reason: str | None = None
    """Например: "parallel_translation_available" """

    translation_of: list[str] = field(default_factory=list)
    """
    Segment_ids сегментов на другом языке, перевод которых — этот сегмент.
    Используется hidden сегментами для LLM context access и аудита.
    """

    translation_pair_confidence: float | None = None
    """
    Confidence пары перевода = alignment_confidence из ParallelGroup.
    None если не в паре.
    """

    translation_language: str | None = None
    """
    ISO код языка переведённого сегмента (для hidden — язык partner'а).
    None если не в паре.
    """

    parallel_group_id: str | None = None
    """ID ParallelGroup к которой принадлежит сегмент. None если не в паре."""

    is_orphan_target: bool = False
    """True если сегмент на target языке без пары"""

    is_orphan_foreign: bool = False
    """True если сегмент на чужом языке без перевода на target"""

    is_ambiguous: bool = False
    """True если language="mixed" или "unknown" в ambiguous context"""

    orphan_display_prefix: str | None = None
    """
    Для is_orphan_foreign: "[БЕЗ ПЕРЕВОДА]" или "[NO TRANSLATION]".
    Не изменяет text сегмента, но UI/downstream может добавить префикс при отображении.
    """

    def is_bypass(self) -> bool:
        """
        True если сегмент прошёл через bypass в Layer 3 и не требует alignment.
        Bypass сегменты всегда visible.
        """
        return self.language in ("structured_data", "neutral")

    @property
    def segment_key(self) -> str:
        """Ключ для de-duplication. Используется в Layer 6 для сортировки."""
        return self.segment_id


@dataclass
class PageLayout:
    """
    Классификация layout одной страницы документа.

    Определяется Layer 2 на основе анализа распределения сегментов по X-координате,
    паттернов чередования языков и наличия таблиц.

    Для непрофессионального программиста:
    - "parallel_columns":  EN слева, RU справа (двуязычная таблица)
    - "interleaved_lines": EN строка, потом RU строка, потом снова EN
    - "stacked_pairs":     EN и RU в одной ячейке, EN сверху, RU снизу
    - "stacked_blocks":    сначала весь EN блок, потом весь RU блок (титульный лист)
    - "monolingual":       только один язык на странице
    - "table_page":        страница целиком таблица
    - "empty":             нет элементов
    - "unknown":           не удалось классифицировать
    """

    page: int
    layout_type: PageLayoutType

    # ── Для parallel_columns ──────────────────────────────────────────────────
    left_column_x_range: tuple[float, float] | None = None
    right_column_x_range: tuple[float, float] | None = None

    # ── Для interleaved_lines ─────────────────────────────────────────────────
    interleave_languages: list[str] = field(default_factory=list)
    """Порядок языков в reading order: ["en", "ru", "en", "ru", ...]"""

    # ── Для stacked_blocks ────────────────────────────────────────────────────
    block_boundaries: list[int] = field(default_factory=list)
    """
    Индексы элементов, где начинается новый языковой блок.
    Пример: [0, 14] — блок 1 elements[0:14], блок 2 elements[14:].
    Layer 4 использует для positional_sequential alignment.
    """

    confidence: float = 1.0
    """Уверенность в классификации layout (0.0-1.0)"""


# ---------------------------------------------------------------------------
# БЛОК 4: Layer 4 — Alignment (Groups)
# ---------------------------------------------------------------------------


@dataclass
class ParallelGroup:
    """
    Группа параллельных сегментов на двух и более языках.

    Для непрофессионального программиста:
    - ParallelGroup — это "пара": один и тот же текст на двух языках.
    - segments_by_language["en"] = ["seg_abc_0"] — английская версия
    - segments_by_language["ru"] = ["seg_xyz_0"] — русская версия
    - Layer 5 выбирает один язык visible, остальные — hidden.

    Список segment_ids для каждого языка — потому что один "параллельный"
    блок может содержать несколько сегментов (длинная клауза разбита на абзацы).
    """

    group_id: str
    """f"pair_{номер}" — глобально уникальный в рамках документа"""

    group_type: Literal["parallel_pair"] = field(default="parallel_pair", init=False)

    page: int = 0
    """Страница на которой находится группа. Если группа spans несколько
    страниц — берётся минимальный page."""

    anchor_uid_normalized: tuple[str, str] | None = None
    """
    Нормализованный anchor ключ через cross_language_anchor_key().
    Пример: ("clause", "1.1"), ("appendix", "3")
    None если группа была найдена не через anchor matching.
    """

    scope: str = ""
    """
    Scope tracking результат из Layer 4.
    "" — основной договор
    "appendix::3" — внутри Appendix 3
    "amendment::1" — внутри Amendment 1
    Используется для scope-aware anchor matching.
    """

    segments_by_language: dict[str, list[str]] = field(default_factory=dict)
    """{lang_code → list[segment_id]}"""

    alignment_confidence: float = 1.0

    alignment_method: AlignmentMethod = "structural_anchor"

    @property
    def languages(self) -> list[str]:
        """Список всех языков в группе, отсортированный (для детерминизма)."""
        return sorted(self.segments_by_language.keys())

    def get_segment_ids(self, language: str) -> list[str]:
        """Segment IDs для указанного языка."""
        return self.segments_by_language.get(language, [])

    def all_segment_ids(self) -> list[str]:
        """Все segment_ids в группе, отсортированные."""
        result: list[str] = []
        for lang in self.languages:
            result.extend(self.segments_by_language[lang])
        return sorted(result)


@dataclass
class OrphanGroup:
    """
    Группа сегментов только на одном языке (нет пары).

    Возникает когда:
    - нумерация в одном языке пропущена
    - текст есть только на одном языке
    - alignment не смог найти пару

    Layer 5:
    - orphan_language == target → visible_orphan_target
    - orphan_language != target → visible_orphan_foreign + display_prefix
    """

    group_id: str
    group_type: Literal["orphan"] = field(default="orphan", init=False)
    page: int = 0

    orphan_language: str = "unknown"
    """ISO код языка сиротского сегмента"""

    scope: str = ""

    segment_ids: list[str] = field(default_factory=list)

    orphan_reason: str = "no_pair_found"
    """
    Причина отсутствия пары:
    - "no_pair_found"           — alignment не нашёл совпадения
    - "numbering_gap"           — anchor есть только в одном языке
    - "layout_mismatch"         — layout типы страницы не совпали
    - "low_confidence"          — alignment confidence ниже порога
    - "no_anchor_available"     — нет anchor'а для structural matching
    - "different_element_count" — блоки разной длины при positional_sequential
    - "single_element"          — единственный элемент своего языка на странице
    """


@dataclass
class MonolingualGroup:
    """
    Группа сегментов на монолингвальной странице.

    Используется для страниц layout_type="monolingual" где нет пар вообще.
    Layer 5 делает все сегменты visible.

    Зачем отдельный тип — не OrphanGroup?
    - OrphanGroup: "ожидалась пара, но не нашлась"
    - MonolingualGroup: "пары и не ожидается — страница монолингвальная"

    Различие важно для метрики orphan_ratio:
    MonolingualGroup НЕ считается orphan.
    """

    group_id: str
    group_type: Literal["monolingual"] = field(default="monolingual", init=False)
    page: int = 0
    scope: str = ""
    segment_ids: list[str] = field(default_factory=list)


# Union тип для всех групп — используется в type hints Layers 4-6
Group = ParallelGroup | OrphanGroup | MonolingualGroup


# ---------------------------------------------------------------------------
# БЛОК 5: Layer 6 — Reconstruction output
# ---------------------------------------------------------------------------


@dataclass
class OutputElement:
    """
    Финальный элемент в layout_primary_v2.json.

    JSON-ready: все поля сериализуются напрямую без преобразования.
    bbox — list[float] (не BBox dataclass) для совместимости с existing кодом.

    Совместимость с existing downstream:
    - classify_elements читает: element_id, type, text, page, bbox, confidence
    - Все multilingual-specific поля живут в metadata
    - existing код игнорирует metadata поля которые не знает
    """

    # ── Идентификация (совместимо с existing) ────────────────────────────────
    element_id: str
    """
    Формат: segment_id из LanguageSegment.
    Пример: "seg_e001_0" (не разбивался), "seg_e001_1" (вторая часть split).
    Для не-разбитых сегментов legacy element_id доступен как source_element_id
    в metadata.
    """

    type: str
    """
    "heading" | "text" — унаследовано из source element.
    NOT authoritative — existing classify_elements пересчитает семантику.
    """

    text: str
    """LOSSLESS — исходный текст из LanguageSegment.text"""

    page: int
    bbox: list[float]
    """[x0, top, x1, bottom] — list[float] для JSON compatibility"""

    confidence: float
    """Confidence extraction (унаследовано из raw element)"""

    clause_uid: str | None
    """Всегда None до structure stage. Заполняется существующим build_hierarchy."""

    # ── Reading order ────────────────────────────────────────────────────────
    reading_order: int
    """Финальный reading_order с учётом split. Пересчитан Layer 6."""

    # ── Multilingual metadata (existing code игнорирует) ─────────────────────
    metadata: dict[str, Any] = field(default_factory=dict)
    """
    Всё multilingual-specific здесь:

    Базовые (всегда):
    - language: str
    - language_confidence: float
    - script: str
    - detection_method: str
    - visibility_in_target_language: str
    - source_element_id: str
    - sub_index: int
    - split_reason: str
    - split_confidence: float
    - bbox_is_approximate: bool
    - bbox_split_method: str

    Для hidden (максимальный контекст):
    - hidden_reason: str
    - translation_of: list[str]
    - translation_pair_confidence: float
    - translation_language: str
    - parallel_group_id: str

    Для orphan:
    - is_orphan_target: bool
    - is_orphan_foreign: bool
    - orphan_display_prefix: str | None

    Для ambiguous:
    - is_ambiguous: bool
    - mixed_languages: list[str]
    """


@dataclass
class QualityMetrics:
    """
    Метрики качества pipeline для мониторинга и триггеров Итерации 2.

    Четыре метрики из спецификации:
    A. orphan_ratio               — доля OrphanGroup от группах с парами
    B. language_purity_precision  — точность на целевом языке
    C. language_purity_recall     — полнота на целевом языке
    D. structural_fidelity        — документы без нарушений нумерации

    Для непрофессионального программиста:
    - orphan_ratio > 0.20    → много клауз без пары → нужен semantic alignment
    - purity_precision < 0.92 → в output попадает чужой язык
    - purity_recall < 0.90    → часть целевого языка теряется
    - structural_fidelity < 0.95 → нарушена нумерация клауз
    """

    # Метрика A: соотношение orphan групп
    total_groups: int = 0
    parallel_groups_count: int = 0
    orphan_groups_count: int = 0
    monolingual_groups_count: int = 0
    orphan_ratio: float = 0.0

    # Метрика B+C: чистота языка в output
    visible_segments_count: int = 0
    target_language_segments_visible: int = 0
    foreign_language_segments_visible: int = 0
    total_target_segments_in_document: int = 0
    language_purity_precision: float = 0.0
    language_purity_recall: float = 0.0

    # Метрика D: структурная целостность
    expected_clause_count: int = 0
    found_clause_count: int = 0
    structural_fidelity: float = 0.0

    # Дополнительные счётчики для диагностики
    segments_total: int = 0
    segments_hidden: int = 0
    bypass_segments_count: int = 0

    # Split quality diagnostics
    segments_split: int = 0
    segments_not_split: int = 0
    avg_split_confidence: float = 1.0
    low_confidence_splits_count: int = 0  # split_confidence < 0.7

    # Alignment method breakdown
    alignments_by_method: dict[str, int] = field(default_factory=dict)

    def compute(self) -> None:
        """
        Пересчитать производные метрики.
        Вызывается Layer 6 после сборки всех сегментов.
        """
        denominator_orphan = self.parallel_groups_count + self.orphan_groups_count
        self.orphan_ratio = (
            self.orphan_groups_count / denominator_orphan
            if denominator_orphan > 0
            else 0.0
        )

        self.language_purity_precision = (
            self.target_language_segments_visible / self.visible_segments_count
            if self.visible_segments_count > 0
            else 0.0
        )

        self.language_purity_recall = (
            self.target_language_segments_visible / self.total_target_segments_in_document
            if self.total_target_segments_in_document > 0
            else 0.0
        )

        self.structural_fidelity = (
            self.found_clause_count / self.expected_clause_count
            if self.expected_clause_count > 0
            else 1.0  # нет клауз → нет нарушений
        )


@dataclass
class ProcessingWarning:
    """
    Структурированное warning из processing_trace.

    Все операции с threshold или неоднозначные решения записываются
    сюда для audit и debugging. Не блокируют pipeline, но позволяют
    видеть проблемные документы без чтения кода.
    """

    warning_type: str
    """
    Типы:
    - "low_split_confidence"    — split сделан но confidence < 0.7
    - "unresolved_anchor"       — anchor есть но не сматчен
    - "layout_ambiguous"        — не удалось однозначно классифицировать layout
    - "orphan_cluster"          — много orphan подряд (потенциальный alignment fail)
    - "empty_page"              — пустая страница
    - "table_split_uncertain"   — split ячейки таблицы с низкой уверенностью
    """

    element_id: str | None = None
    """Связанный element_id, если применимо"""

    page: int | None = None
    """Связанная страница, если применимо"""

    details: dict[str, Any] = field(default_factory=dict)
    """Дополнительный контекст"""


@dataclass
class ProcessingTrace:
    """
    Трассировка обработки для отладки и аудита.

    Хранит: версии компонентов, timing, количество элементов на каждом слое,
    warnings из всех слоёв.
    """

    schema_version: str = SCHEMA_VERSION
    analysis_source_kind: str = ANALYSIS_SOURCE_KIND
    pipeline_version: str = "1.0.0"

    # Количество элементов после каждого слоя
    elements_after_layer1: int = 0
    segments_after_layer2: int = 0
    segments_after_layer3: int = 0
    groups_after_layer4: int = 0
    segments_after_layer5: int = 0
    elements_after_layer6: int = 0

    # Timing (секунды)
    layer1_seconds: float = 0.0
    layer2_seconds: float = 0.0
    layer3_seconds: float = 0.0
    layer4_seconds: float = 0.0
    layer5_seconds: float = 0.0
    layer6_seconds: float = 0.0
    total_seconds: float = 0.0

    # Версии зависимостей
    lingua_version: str = "2.0.2"

    # Warnings из всех слоёв
    warnings: list[ProcessingWarning] = field(default_factory=list)


@dataclass
class PipelineMetadata:
    """
    Metadata финального layout_primary_v2.json.

    Секции:
    1. language_pipeline  — информация о языковом составе
    2. quality_metrics    — четыре метрики из спецификации
    3. processing_trace   — трассировка для отладки

    Плюс поля для backward compatibility с existing кодом:
    - language_filter — extract_worker проверяет analysis_source_kind здесь
    - contract_version — existing код проверяет это поле
    """

    # Языковая информация
    detected_languages: list[str] = field(default_factory=list)
    target_language: str = ""
    is_multilingual: bool = False
    language_ratios: dict[str, float] = field(default_factory=dict)
    target_language_ratio: float = 0.0

    # Layout summary
    layout_type_summary: dict[int, str] = field(default_factory=dict)
    """{page_number → layout_type_string}"""

    # Объекты метрик и трассировки
    quality_metrics: QualityMetrics = field(default_factory=QualityMetrics)
    processing_trace: ProcessingTrace = field(default_factory=ProcessingTrace)

    # Backward compatibility с extract_worker
    language_filter: dict[str, Any] = field(default_factory=lambda: {
        "analysis_source_kind": ANALYSIS_SOURCE_KIND,
        "contract_version": 2,
        "downstream_requires_primary_source": False,
    })

    language_pipeline: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать в dict для JSON.
        Ключи в отсортированном порядке для deterministic output.
        """
        qm_dict = {k: v for k, v in vars(self.quality_metrics).items()}
        # alignments_by_method — sort для детерминизма
        if "alignments_by_method" in qm_dict:
            qm_dict["alignments_by_method"] = dict(
                sorted(qm_dict["alignments_by_method"].items())
            )

        pt_dict = {k: v for k, v in vars(self.processing_trace).items()}
        # warnings — serialize список ProcessingWarning
        pt_dict["warnings"] = [
            {
                "warning_type": w.warning_type,
                "element_id": w.element_id,
                "page": w.page,
                "details": dict(sorted(w.details.items())) if w.details else {},
            }
            for w in self.processing_trace.warnings
        ]

        return {
            "detected_languages": sorted(self.detected_languages),
            "target_language": self.target_language,
            "is_multilingual": self.is_multilingual,
            "language_ratios": dict(sorted(self.language_ratios.items())),
            "target_language_ratio": self.target_language_ratio,
            "layout_type_summary": {
                str(k): v for k, v in sorted(self.layout_type_summary.items())
            },
            "quality_metrics": qm_dict,
            "processing_trace": pt_dict,
            "language_filter": dict(sorted(self.language_filter.items())),
            "language_pipeline": dict(sorted(self.language_pipeline.items()))
                if self.language_pipeline else {},
        }


@dataclass
class PipelineResult:
    """
    Итоговый результат работы всего multilingual pipeline.

    Это и есть layout_primary_v2.json после сериализации.

    Содержит:
    - все OutputElement (visible и hidden)
    - tables (с обработанными билингвальными ячейками)
    - metadata с метриками и трассировкой

    Для непрофессионального программиста:
    - downstream (classify, structure, chunks) читает только visible элементы
      через метод to_monolingual_layout()
    - hidden элементы физически остаются в elements[] для LLM context access
    - groups не сохраняются в JSON — они промежуточные объекты Layer 4
    """

    schema_version: str = SCHEMA_VERSION
    document_id: str = ""
    document_version_id: str = ""
    target_language: str = ""
    detected_languages: list[str] = field(default_factory=list)

    elements: list[OutputElement] = field(default_factory=list)
    """
    ВСЕ элементы — visible и hidden.
    Sorted by reading_order.
    """

    tables: list[dict[str, Any]] = field(default_factory=list)
    """
    Tables с обработанными билингвальными ячейками.
    Формат совместим с existing raw_layout.tables.
    Билингвальные ячейки помечены полем "bilingual_cell": true.
    """

    metadata: PipelineMetadata = field(default_factory=PipelineMetadata)

    def get_visible_elements(self) -> list[OutputElement]:
        """
        Вернуть только visible элементы в порядке reading_order.
        Это то что видят downstream стадии.
        """
        return [
            el for el in self.elements
            if el.metadata.get("visibility_in_target_language") != "hidden"
        ]

    def get_hidden_elements(self) -> list[OutputElement]:
        """Вернуть скрытые элементы (переводы на другой язык)."""
        return [
            el for el in self.elements
            if el.metadata.get("visibility_in_target_language") == "hidden"
        ]

    def to_monolingual_layout(self) -> dict[str, Any]:
        """
        Вернуть layout с только visible элементами.

        Drop-in replacement для existing layout_primary.
        Готов для передачи в classify_elements() и остальной existing downstream.

        Использование:
            result = pipeline.run(raw_layout, target_language="ru")
            monolingual = result.to_monolingual_layout()
            classified = classify_elements(monolingual["elements"])

        Format совместим с существующим text_layout_raw:
        - document_id, document_version_id на верхнем уровне
        - elements — list of dicts с полями element_id, type, text, page, bbox
        - tables — list of table dicts
        - metadata — с analysis_source_kind = canonical_filtered_layout_v2
        """
        visible = self.get_visible_elements()

        elements_dicts = []
        for el in visible:
            # Copy metadata и убираем hidden-specific поля для чистоты
            el_metadata = dict(el.metadata)

            # Формируем dict в порядке совместимом с existing layout format
            el_dict = {
                "element_id": el.element_id,
                "type": el.type,
                "text": el.text,
                "page": el.page,
                "bbox": el.bbox,
                "confidence": el.confidence,
                "clause_uid": el.clause_uid,
                "reading_order": el.reading_order,
                "metadata": el_metadata,
            }
            elements_dicts.append(el_dict)

        return {
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "elements": elements_dicts,
            "tables": self.tables,
            "metadata": self.metadata.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать полный PipelineResult в dict для сохранения
        в MinIO как layout_primary_v2.json.

        Содержит ВСЕ элементы (visible + hidden) для аудита и LLM context.
        """
        elements_dicts = []
        for el in self.elements:
            el_dict = {
                "element_id": el.element_id,
                "type": el.type,
                "text": el.text,
                "page": el.page,
                "bbox": el.bbox,
                "confidence": el.confidence,
                "clause_uid": el.clause_uid,
                "reading_order": el.reading_order,
                "metadata": dict(sorted(el.metadata.items())) if el.metadata else {},
            }
            elements_dicts.append(el_dict)

        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "target_language": self.target_language,
            "detected_languages": sorted(self.detected_languages),
            "elements": elements_dicts,
            "tables": self.tables,
            "metadata": self.metadata.to_dict(),
        }


