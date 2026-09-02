# src/services/document_layout/docling_extractor.py

"""
Docling Extractor Module (Phase 1 / CPU-Safe).

Отвечает за первичное извлечение семантической структуры документа:
- PDF bytes -> Docling DocumentConverter;
- Принудительное использование CPU для совместимости с Celery prefork;
- Итерация строго по document.texts (canonical backbone без дублей);
- Итерация по document.tables (структурированные таблицы);
- Преобразование координат bbox в систему Fitz (origin top-left, y↓);
- Формирование списков CanonicalAtom, CanonicalTable и CanonicalPage.
"""

from __future__ import annotations

import hashlib
import io
import re
import threading
from typing import Any

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import AcceleratorDevice, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from core.logging import get_logger
from services.document_layout.config import layout_config
from services.document_layout.schemas import (
    CanonicalAtom,
    CanonicalAtomSource,
    CanonicalPage,
    CanonicalTable,
    CanonicalTableCell,
)
from services.document_layout.marker_recovery import recover_markers_from_atoms
from services.document_layout.spatial_marker_recovery import SpatialMarkerRecovery

logger = get_logger(__name__)

_converter_lock = threading.Lock()
_converter_instance: DocumentConverter | None = None

_MARKER_REGEX = re.compile(
    r"^("
    r"\d+(?:\.\d+)*\.?"              # Арабские: 1, 1.1, 2.
    r"|[IVXLCDMivxlcdm]+\.?"         # Римские с опциональной точкой: I, I., II., iv, v.
    r"|[A-Za-zА-Яа-я]\)"             # Буквы со скобкой: А), a)
    r"|\([A-Za-zА-Яа-я\d]+\)"        # Буквы/цифры в скобках: (1), (А)
    r"|[•\-\*—]"                     # Буллеты: •, -, *, —
    r")(?=\s+|$)"                    # Positive lookahead: требует пробел после, но не захватывает
)


def get_document_converter() -> DocumentConverter:
    global _converter_instance
    if _converter_instance is None:
        with _converter_lock:
            if _converter_instance is None:
                pipeline_options = PdfPipelineOptions()
                pipeline_options.do_table_structure = True
                pipeline_options.do_ocr = True
                # Безопасное использование CPU для Celery prefork
                pipeline_options.accelerator_options.device = AcceleratorDevice.CPU

                format_options = {
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options
                    )
                }

                _converter_instance = DocumentConverter(
                    format_options=format_options
                )
                logger.info("Docling DocumentConverter singleton (CPU mode) initialized successfully")
    return _converter_instance


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _convert_bbox_to_fitz(
    bbox: Any,
    page_height: float,
) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    try:
        l = float(getattr(bbox, "l", getattr(bbox, "left", 0.0)))
        b = float(getattr(bbox, "b", getattr(bbox, "bottom", 0.0)))
        r = float(getattr(bbox, "r", getattr(bbox, "right", 0.0)))
        t = float(getattr(bbox, "t", getattr(bbox, "top", 0.0)))

        y0_top = max(0.0, page_height - max(t, b))
        y1_top = max(0.0, page_height - min(t, b))
        x0 = min(l, r)
        x1 = max(l, r)

        return (round(x0, 2), round(y0_top, 2), round(x1, 2), round(y1_top, 2))
    except Exception as exc:
        logger.debug("Failed to convert Docling bbox, returning None", error=str(exc))
        return None


def _extract_marker(text: str) -> tuple[str | None, bool]:
    stripped = text.strip()
    if not stripped:
        return None, False
    match = _MARKER_REGEX.match(stripped)
    if match:
        marker = match.group(1).strip()
        # FIX: Исключить ложные одиночные буквы (г., В, а и т.д.)
        # Разрешаем только если это римская цифра, цифра, или буква с )
        if len(marker) == 1 and marker.isalpha() and marker not in "IVXLCDMivxlcdm":
            # Одиночная буква без скобки — скорее всего не маркер
            if not stripped.startswith(marker + ")"):
                return None, False
        is_marker_only = len(stripped) == len(match.group(0).strip())
        return marker, is_marker_only
    return None, False


class DoclingExtractor:
    def __init__(self, converter: DocumentConverter | None = None):
        self.converter = converter or get_document_converter()

    def extract(
        self,
        pdf_bytes: bytes,
        document_id: str,
        document_version_id: str,
    ) -> tuple[list[CanonicalAtom], list[CanonicalTable], list[CanonicalPage], str]:
        sha256_hash = _compute_sha256(pdf_bytes)

        logger.info(
            "Starting Docling extraction pass",
            document_id=document_id,
            document_version_id=document_version_id,
            pdf_size_bytes=len(pdf_bytes),
            sha256=sha256_hash,
        )

        # ── Явная передача DocumentStream с InputFormat.PDF ───────────────────
        doc_stream = DocumentStream(
            name=f"{document_id}.pdf",
            stream=io.BytesIO(pdf_bytes),
            format=InputFormat.PDF,
        )
        conv_result = self.converter.convert(doc_stream)

        doc = conv_result.document

        doc = conv_result.document

        pages_dict: dict[int, CanonicalPage] = {}
        page_heights: dict[int, float] = {}

        for page_no, page_obj in doc.pages.items():
            p_no = int(page_no)
            width = float(getattr(page_obj.size, "width", 595.28))
            height = float(getattr(page_obj.size, "height", 841.89))
            page_heights[p_no] = height
            pages_dict[p_no] = CanonicalPage(
                page_number=p_no,
                width=width,
                height=height,
                atoms=[],
            )

        if not pages_dict:
            pages_dict[1] = CanonicalPage(page_number=1, width=595.28, height=841.89, atoms=[])
            page_heights[1] = 841.89

        atoms: list[CanonicalAtom] = []

        for idx, text_item in enumerate(doc.texts):
            text_val = getattr(text_item, "text", "") or ""
            raw_label = getattr(text_item, "label", "paragraph")
            label_str = (
                raw_label.value.lower()
                if hasattr(raw_label, "value")
                else str(raw_label).lower()
            )

            page_num = 1
            fitz_bbox: tuple[float, float, float, float] | None = None
            item_ref = getattr(text_item, "self_ref", None) or f"text_{idx}"

            if getattr(text_item, "prov", None):
                prov = text_item.prov[0]
                page_num = int(getattr(prov, "page_no", 1))
                page_h = page_heights.get(page_num, 841.89)
                fitz_bbox = _convert_bbox_to_fitz(getattr(prov, "bbox", None), page_h)

            # Сохранение нативного маркера Docling (data-preservation).
            # Для label=list_item Docling выносит нумерацию в text_item.marker,
            # а text_item.text содержит только тело. Без этого шага downstream
            # теряет нумерацию. Универсально: работает для любого формата/языка.
            _native_marker = getattr(text_item, "marker", None)
            if _native_marker:
                _native_str = str(_native_marker).strip()
                if _native_str:
                    # Пропускаем marker-only элементы: Docling создаёт их
                    # отдельно для list_item (text="I.", marker="I.").
                    # Маркер уже будет добавлен к body-элементу, поэтому
                    # marker-only — дубликат, который засоряет sanitized layout.
                    _text_stripped = text_val.strip()
                    if (
                        not _text_stripped
                        or _text_stripped == _native_str
                        or _text_stripped.rstrip(".") == _native_str.rstrip(".")
                    ):
                        continue
                    if not _text_stripped.startswith(_native_str):
                        text_val = f"{_native_str} {_text_stripped}"

            marker, is_marker_only = _extract_marker(text_val)

            atom = CanonicalAtom(
                element_id=f"atom:{idx:06d}",
                page=page_num,
                bbox=fitz_bbox,
                source_reading_order=idx,
                layout_order=idx,
                layout_order_confidence="unvalidated",
                text=text_val,
                marker=marker,
                is_marker_only=is_marker_only,
                label=label_str,
                parent_ref=None,
                language="shared",
                language_confidence=1.0,
                language_evidence=None,
                style=None,
                source=CanonicalAtomSource(
                    docling_collection="texts",
                    docling_item_ref=str(item_ref),
                ),
            )
            atoms.append(atom)

            if page_num in pages_dict:
                pages_dict[page_num].atoms.append(atom)

        tables: list[CanonicalTable] = []

        for t_idx, table_item in enumerate(doc.tables):
            table_id = f"table:{t_idx:04d}"
            t_page_num = 1
            t_fitz_bbox = None

            if getattr(table_item, "prov", None):
                t_prov = table_item.prov[0]
                t_page_num = int(getattr(t_prov, "page_no", 1))
                t_page_h = page_heights.get(t_page_num, 841.89)
                t_fitz_bbox = _convert_bbox_to_fitz(
                    getattr(t_prov, "bbox", None), t_page_h
                )

            markdown_str = ""
            if hasattr(table_item, "export_to_markdown"):
                try:
                    markdown_str = table_item.export_to_markdown()
                except Exception:
                    markdown_str = ""

            cells: list[CanonicalTableCell] = []
            num_rows = 1
            num_cols = 1

            if hasattr(table_item, "data") and getattr(table_item.data, "grid", None):
                grid = table_item.data.grid
                num_rows = len(grid)
                num_cols = len(grid[0]) if num_rows > 0 else 1

                for r_idx, row in enumerate(grid):
                    for c_idx, cell in enumerate(row):
                        cell_text = getattr(cell, "text", str(cell)) or ""
                        r_span = int(getattr(cell, "row_span", 1) or 1)
                        c_span = int(getattr(cell, "col_span", 1) or 1)
                        cells.append(
                            CanonicalTableCell(
                                row=r_idx,
                                col=c_idx,
                                row_span=r_span,
                                col_span=c_span,
                                text=cell_text,
                                language="shared",
                            )
                        )

            canonical_table = CanonicalTable(
                table_id=table_id,
                page=t_page_num,
                bbox=t_fitz_bbox,
                num_rows=max(num_rows, 1),
                num_cols=max(num_cols, 1),
                language="shared",
                cells=cells,
                markdown=markdown_str,
                source={"docling_collection": "tables", "table_index": t_idx},
            )
            tables.append(canonical_table)

        pages_list = [pages_dict[k] for k in sorted(pages_dict.keys())]

        # Восстановить нумерацию для всех атомов (универсально для всех форматов)
        atoms = recover_markers_from_atoms(atoms)

        # Spatial recovery — compensating control для Docling issue #1345
        # Восстанавливает маргинальные маркеры нумерации (1.1, 1.2, 2.1...)
        atoms, recovery_metrics = SpatialMarkerRecovery.recover(
            atoms=atoms,
            pdf_bytes=pdf_bytes,
            document_id=document_id,
        )

        logger.info(
            "Docling extraction completed with spatial recovery",
            extra={
                "document_id": document_id,
                "atoms_count": len(atoms),
                "markers_recovered": recovery_metrics.markers_recovered_high_confidence,
                "recovery_rate": recovery_metrics.recovery_rate,
            },
        )

        logger.info(
            "Docling extraction completed",
            document_id=document_id,
            atoms_count=len(atoms),
            tables_count=len(tables),
            pages_count=len(pages_list),
            markers_recovered=sum(1 for a in atoms if a.marker),
        )

        return atoms, tables, pages_list, sha256_hash


