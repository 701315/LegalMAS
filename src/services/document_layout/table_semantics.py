"""
Table Semantics Module (Layer 7).

Отвечает за определение топологии многоязычных таблиц и ячеечную фильтрацию:
- Статистическая классификация топологии: TableTopologyType (PARALLEL_COLUMN / INLINE_CELL / MIXED_ROW);
- Фильтрация столбцов противоположного языка для parallel-column таблиц;
- Вызов рекурсивного SpanSplitter для ячеек с inline-склейкой (\, /);
- Сборка итогового построчного Markdown-текста таблицы.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from services.document_layout.config import layout_config
from services.document_layout.language_classifier import classify_text
from services.document_layout.schemas import CanonicalTable, TableTopologyType
from services.document_layout.span_splitter import SpanSplitter

logger = get_logger(__name__)


class TableSemanticsProcessor:
    """
    Сервис анализа топологии и ячеечной фильтрации многоязычных таблиц.
    """

    def __init__(self, splitter: SpanSplitter | None = None):
        self.splitter = splitter or SpanSplitter()

    def classify_topology(
        self,
        table: CanonicalTable,
        target_language: str,
    ) -> TableTopologyType:
        """
        Статистически определяет топологию многоязычной таблицы.
        """
        target_lang = target_language.lower().strip()
        if not table.cells or table.num_rows < layout_config.table_topology_min_rows_for_classification:
            return TableTopologyType.UNKNOWN

        # Проверяем наличие inline-разделителей (\, /) в ячейках
        inline_sep_count = 0
        for cell in table.cells:
            if any(sep in cell.text for sep in layout_config.inline_cell_split_separators):
                inline_sep_count += 1

        if inline_sep_count >= 2:
            return TableTopologyType.INLINE_CELL

        # Анализ чистоты столбцов
        col_languages: dict[int, list[str]] = {}
        for cell in table.cells:
            if cell.text.strip():
                lang_class = classify_text(cell.text)
                if lang_class.language not in ("shared", "mixed"):
                    col_languages.setdefault(cell.col, []).append(lang_class.language)

        if not col_languages:
            return TableTopologyType.MONOLINGUAL

        # Если есть столбцы, где 100% ячеек на противоположном языке — это PARALLEL_COLUMN
        opposite_cols_count = 0
        for col_idx, langs in col_languages.items():
            if langs:
                target_ratio = sum(1 for l in langs if l == target_lang) / len(langs)
                if target_ratio == 0.0:
                    opposite_cols_count += 1

        if opposite_cols_count >= 1:
            return TableTopologyType.PARALLEL_COLUMN

        return TableTopologyType.MIXED_ROW

    def process_table(
        self,
        table: CanonicalTable,
        target_language: str,
    ) -> tuple[str, TableTopologyType]:
        """
        Обрабатывает таблицу с учётом её топологии и возвращает (markdown_text, topology_type).
        """
        target_lang = target_language.lower().strip()
        topology = self.classify_topology(table, target_lang)

        logger.info(
            "Processing table semantics",
            table_id=table.table_id,
            topology=topology.value,
            target_language=target_lang,
        )

        rows_map: dict[int, list[str]] = {}

        if topology == TableTopologyType.PARALLEL_COLUMN:
            # Отфильтровываем столбцы противоположного языка
            for cell in table.cells:
                text = cell.text.strip()
                if not text:
                    continue
                lang_class = classify_text(text)
                if lang_class.language in (target_lang, "shared", "mixed"):
                    rows_map.setdefault(cell.row, []).append(text)

        elif topology == TableTopologyType.INLINE_CELL:
            # Для каждой ячейки вызываем рекурсивный SpanSplitter
            for cell in table.cells:
                text = cell.text.strip()
                if not text:
                    continue
                split_res = self.splitter.split_span(text, target_lang)
                if split_res.target_text:
                    rows_map.setdefault(cell.row, []).append(split_res.target_text)

        else:
            # Default / MIXED_ROW / MONOLINGUAL: ячеечная фильтрация
            for cell in table.cells:
                text = cell.text.strip()
                if not text:
                    continue
                lang_class = classify_text(text)
                if lang_class.language in (target_lang, "shared"):
                    rows_map.setdefault(cell.row, []).append(text)
                elif lang_class.language == "mixed":
                    split_res = self.splitter.split_span(text, target_lang)
                    if split_res.target_text:
                        rows_map.setdefault(cell.row, []).append(split_res.target_text)

        markdown_rows = []
        for row_idx in sorted(rows_map.keys()):
            row_cells = rows_map[row_idx]
            if row_cells:
                markdown_rows.append("| " + " | ".join(row_cells) + " |")

        if markdown_rows:
            final_text = "\n".join(markdown_rows)
        else:
            final_text = table.markdown if table.markdown else f"Таблица {table.table_id}"

        return final_text, topology
