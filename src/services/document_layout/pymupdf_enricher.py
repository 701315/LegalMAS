# src/services/document_layout/pymupdf_enricher.py

"""
PyMuPDF Visual Enricher Module (Phase 2).

Отвечает за обогащение канонических атомов Docling визуальными свойствами:
- Шрифты (font name, font size);
- Начертания (bold, italic);
- Цвет текста (RGB int/hex);
- Статус и скор пространственного сопоставления (IoU / text containment).

Контракт:
- Работает по тем же исходным PDF bytes;
- Сохраняет исходный порядок атомов;
- Отсутствие совпадения не является ошибкой (style=None, visual_match_status="not_matched").
"""

from __future__ import annotations

from typing import Any

import pymupdf as fitz

from core.logging import get_logger
from services.document_layout.schemas import CanonicalAtom, ElementStyle

logger = get_logger(__name__)


def _calculate_iou(
    bbox1: tuple[float, float, float, float],
    bbox2: tuple[float, float, float, float],
) -> float:
    """
    Вычисляет Intersection-over-Union (IoU) для двух прямоугольников [x0, y0, x1, y1].
    """
    x0_1, y0_1, x1_1, y1_1 = bbox1
    x0_2, y0_2, x1_2, y1_2 = bbox2

    inter_x0 = max(x0_1, x0_2)
    inter_y0 = max(y0_1, y0_2)
    inter_x1 = min(x1_1, x1_2)
    inter_y1 = min(y1_1, y1_2)

    inter_w = max(0.0, inter_x1 - inter_x0)
    inter_h = max(0.0, inter_y1 - inter_y0)
    inter_area = inter_w * inter_h

    if inter_area <= 0.0:
        return 0.0

    area1 = max(0.0, x1_1 - x0_1) * max(0.0, y1_1 - y0_1)
    area2 = max(0.0, x1_2 - x0_2) * max(0.0, y1_2 - y0_2)
    union_area = area1 + area2 - inter_area

    return inter_area / union_area if union_area > 0.0 else 0.0


def _extract_page_spans(page: fitz.Page) -> list[dict[str, Any]]:
    """
    Извлекает плоский список всех спанов со страницы через page.get_text("dict").
    """
    spans: list[dict[str, Any]] = []
    page_dict = page.get_text("dict", flags=fitz.TEXT_DEHYPHENATE)

    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block, 1 = image block
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                span_text = span.get("text", "").strip()
                if not span_text:
                    continue

                bbox = span.get("bbox", (0.0, 0.0, 0.0, 0.0))
                flags = int(span.get("flags", 0))

                # Битовые флаги PyMuPDF: bit 4 (16) = bold, bit 1 (2) = italic
                is_bold = bool(flags & 16 or "bold" in span.get("font", "").lower())
                is_italic = bool(flags & 2 or "italic" in span.get("font", "").lower())

                spans.append({
                    "text": span_text,
                    "bbox": (
                        round(float(bbox[0]), 2),
                        round(float(bbox[1]), 2),
                        round(float(bbox[2]), 2),
                        round(float(bbox[3]), 2),
                    ),
                    "font": span.get("font"),
                    "font_size": round(float(span.get("size", 0.0)), 1),
                    "bold": is_bold,
                    "italic": is_italic,
                    "color": span.get("color"),
                })
    return spans


class PyMuPDFEnricher:
    """
    Сервис обогащения визуальными стилями атомов Docling через PyMuPDF.
    """

    def enrich(
        self,
        pdf_bytes: bytes,
        atoms: list[CanonicalAtom],
    ) -> list[CanonicalAtom]:
        """
        Сопоставляет атомы со спанами PyMuPDF и обогащает поле style.
        """
        if not atoms:
            return []

        logger.info(
            "Starting PyMuPDF visual enrichment pass",
            atoms_count=len(atoms),
            pdf_size_bytes=len(pdf_bytes),
        )

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.warning(
                "Failed to open PDF in PyMuPDF for visual enrichment, skipping",
                error=str(e),
            )
            return atoms

        # Кэш спанов по номеру страницы (1-based)
        page_spans_cache: dict[int, list[dict[str, Any]]] = {}
        for p_idx in range(len(doc)):
            page_no = p_idx + 1
            page_spans_cache[page_no] = _extract_page_spans(doc[p_idx])

        doc.close()

        enriched_atoms: list[CanonicalAtom] = []
        matched_count = 0

        for atom in atoms:
            if not atom.bbox:
                # Нет провенанса геометрии -> стиль не может быть сматчен
                enriched_atom = atom.model_copy(
                    update={
                        "style": ElementStyle(visual_match_status="not_found")
                    }
                )
                enriched_atoms.append(enriched_atom)
                continue

            candidate_spans = page_spans_cache.get(atom.page, [])
            best_span: dict[str, Any] | None = None
            best_score = 0.0

            atom_text_norm = atom.text.strip().lower()

            for span in candidate_spans:
                iou = _calculate_iou(atom.bbox, span["bbox"])
                span_text_norm = span["text"].lower()

                text_containment = 0.0
                if span_text_norm in atom_text_norm or atom_text_norm in span_text_norm:
                    text_containment = 0.5

                # Комбинированный скор: пространственное перекрытие + текстовое совпадение
                score = (iou * 0.5) + text_containment

                if score > best_score:
                    best_score = score
                    best_span = span

            if best_span and best_score >= 0.2:
                style = ElementStyle(
                    font=best_span.get("font"),
                    font_size=best_span.get("font_size"),
                    bold=best_span.get("bold", False),
                    italic=best_span.get("italic", False),
                    color=best_span.get("color"),
                    match_score=round(best_score, 3),
                    visual_match_status="matched",
                )
                matched_count += 1
            else:
                style = ElementStyle(visual_match_status="not_matched")

            enriched_atom = atom.model_copy(update={"style": style})
            enriched_atoms.append(enriched_atom)

        logger.info(
            "PyMuPDF visual enrichment completed",
            total_atoms=len(atoms),
            matched_atoms=matched_count,
            match_rate=round(matched_count / max(len(atoms), 1), 3),
        )

        return enriched_atoms
