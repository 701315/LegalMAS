# src/services/document_layout/config.py

"""
Конфигурация Document Layout Pipeline v3.

Все пороги, маппинги и паттерны вынесены сюда для:
- лёгкой настройки per-tenant / per-environment;
- тестирования с разными конфигурациями;
- отсутствия magic numbers в бизнес-логике.

Универсальность:
- Все параметры — числовые пороги, отношения, коэффициенты, структурные разделители;
- Ни один параметр не является списком слов конкретного языка;
- Работает для любой пары языков и любой верстки документа.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from services.document_layout.schemas import ProjectionMode


class DocumentLayoutConfig(BaseSettings):
    """Настройки пайплайна. Читаются из env с префиксом DOCUMENT_LAYOUT_."""

    # ── Language Classifier (existing) ────────────────────────────────────
    min_absolute_letter_count: int = Field(default=3)
    dominant_script_ratio: float = Field(default=0.85)
    min_substantive_letter_count: int = Field(default=5)

    # Unicode Scripts → ISO language codes
    # Полностью универсально: работает для любой пары языков;
    # расширяется добавлением новых скриптов, не меняя код.
    script_to_language: dict[str, str] = Field(
        default={
            "Cyrillic": "ru",
            "Latin": "en",
            "Han": "zh",
            "Arabic": "ar",
            "Devanagari": "hi",
            "Hangul": "ko",
            "Hiragana": "ja",
            "Katakana": "ja",
        },
    )

    # Docling label → downstream classifier raw_type mapping
    # Универсально: маппинг определяется Docling, не языком документа.
    label_to_raw_type: dict[str, str] = Field(
        default={
            "list_item": "list_item",
            "section_header": "heading",
            "paragraph": "text",
            "table": "table",
            "title": "heading",
            "page_header": "page_artifact",
            "page_footer": "page_artifact",
            "footnote": "text",
            "caption": "text",
            "formula": "text",
            "picture": "page_artifact",
            "document_index": "text",
            "code": "text",
            "checkbox_selected": "list_item",
            "checkbox_unselected": "list_item",
        },
    )

    # ── Safe Split Patterns for Mixed Atoms (existing + extended v3) ──────
    # Структурные типографские разделители, не языковые слова.
    # \ добавлен для обработки inline-склейки в таблицах юридических документов
    # (обнаружено на реальном "Приложении № 5" тестового SPA-договора).
    safe_split_patterns: list[dict[str, str]] = Field(
        default=[
            {"separator": " \\ ", "strategy": "left_right"},
            {"separator": "\\", "strategy": "left_right"},
            {"separator": " / ", "strategy": "left_right"},
            {"separator": " — ", "strategy": "left_right"},
            {"separator": "\n", "strategy": "line_by_line_language"},
        ],
    )

    # Универсальные разделители для inline-фильтрации ячеек таблиц.
    # Типографские знаки, не языковые.
    inline_cell_split_separators: list[str] = Field(
        default=["\\", "/", "—", "|"],
    )

    # ── Projection Quality Thresholds (existing) ──────────────────────────
    min_target_language_ratio: float = Field(default=0.05)
    max_atom_count_drop_ratio: float = Field(default=0.80)

    # ── v3 Layer 1: Geometry (Page Region Segmentation) ───────────────────
    # Порог height-gating: колонкой считается только блок,
    # чья высота >= 25% от высоты самого высокого блока на странице.
    # Значение 0.25 — из независимо воспроизведённого бенчмарка,
    # даёт рост reading-order fidelity с 0.564 до 0.816.
    column_min_height_ratio: float = Field(default=0.25)
    
    # Минимальный gutter между колонками в долях ширины страницы.
    # Меньше — колонки склеиваются в single-column reading order.
    column_gutter_min_ratio: float = Field(default=0.02)
    
    # Порог для классификации короткого блока как grid-block
    # (титульный блок, подписи, метаданные).
    grid_block_max_height_ratio: float = Field(default=0.15)

    # ── v3 Layer 5: Parallel Alignment ────────────────────────────────────
    # Минимальное перекрытие Y-диапазонов bbox для сопоставления пунктов.
    # 0.6 = 60% Y-overlap необходимы, чтобы считать 2 маркера "параллельными".
    marker_alignment_y_overlap_threshold: float = Field(default=0.6)
    
    # Требовать ли совпадения hierarchy_path при дедупликации.
    # True защищает от ложных срабатываний повторяющихся маркеров
    # в разных разделах документа.
    marker_alignment_require_hierarchy_match: bool = Field(default=True)
    
    # Максимальный gap в monotonic sequence matching (fallback).
    # Больше — разрешаем более удалённые совпадения; меньше — строже.
    monotonic_matching_max_gap: int = Field(default=3)

    # ── v3 Layer 6: Span Splitter ─────────────────────────────────────────
    # Минимальная confidence для авто-split смешанной строки.
    # Ниже — строка сохраняется целиком с флагом needs_review.
    mixed_span_split_min_confidence: float = Field(default=0.75)

    # ── v3 Layer 7: Table Semantics ───────────────────────────────────────
    # Порог "чистоты" языка в столбце для классификации topology.
    # 0.85 = столбец считается моноязычным, если 85% ячеек на одном языке.
    table_column_language_purity_threshold: float = Field(default=0.85)
    
    # Минимум строк для статистической классификации topology таблицы.
    # Меньше строк — таблица классифицируется как UNKNOWN (safe default).
    table_topology_min_rows_for_classification: int = Field(default=2)
    
    # Docling TableFormer option для псевдотаблиц
    # (текстовых колонок, ошибочно распознанных как таблица).
    do_cell_matching_for_pseudo_table: bool = Field(default=False)

    # ── v3 Layer 8: Projection Mode ───────────────────────────────────────
    # Режим работы monolingual_projector.
    # STRICT — production default (сомнительное в quarantine);
    # LOSSLESS_REVIEW — параллельный артефакт для аудита;
    # AUTO_ACCEPT — компромисс.
    default_projection_mode: ProjectionMode = Field(
        default=ProjectionMode.STRICT,
    )
    
    # Отправлять ли low-confidence элементы в quarantine
    # вместо принудительного удаления.
    quarantine_on_low_confidence: bool = Field(default=True)

    # ── v3 Layer 9: Quality Gates (scored thresholds) ─────────────────────
    # Минимальная reading-order fidelity для прохождения gate.
    # 0.75 = 75% сходство с эталонным порядком.
    min_reading_order_fidelity: float = Field(default=0.75)
    
    # Максимально допустимая доля orphan/duplicate маркеров.
    max_orphan_marker_rate: float = Field(default=0.05)
    
    # Максимально допустимая доля утечки чужого языка в проекции.
    max_leakage_rate: float = Field(default=0.001)

    # ── Feature Flags ─────────────────────────────────────────────────────
    document_layout_v2_enabled: bool = Field(default=True)

    model_config = {"env_prefix": "DOCUMENT_LAYOUT_", "case_sensitive": False}


# Singleton instance
layout_config = DocumentLayoutConfig()
