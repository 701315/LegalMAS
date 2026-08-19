"""
Shared document language detection service.

Назначение:
- единая точка раннего language detection для документов;
- используется и pre-run language discovery orchestrator'ом,
  и build_primary_language_source worker'ом;
- не пишет в БД и не знает про Deal/Document status — только строит
  лёгкое представление входных данных и возвращает список найденных языков.

Поддерживаемые входы:
- PDF bytes -> quick layout -> language detection;
- plain OCR text -> lightweight text layout -> language detection.

MULTILINGUAL поддержка:
- возвращает реальные ISO 639-1 коды всех найденных языков;
- поддерживает 75+ языков через lingua;
- корректно работает для bilingual OCR текста, если разные языки
  находятся в разных строках/абзацах.

Важно:
- этот модуль ничего не знает про Celery, БД и статусы документов;
- он только вычисляет и возвращает результат;
- worker-слои сами решают, как сохранять completed / failed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.logging import get_logger
from services.layout_language_filter import detect_languages_in_layout
from services.quick_pdf_layout import build_quick_layout_from_pdf

logger = get_logger(__name__)

_MIN_LANG_CODE_LEN = 2
_MAX_LANG_CODE_LEN = 8
_MIN_QUICK_TEXT_BLOCK_CHARS = 5
_MAX_BLOCK_LEN_BEFORE_SENTENCE_SPLIT = 400


@dataclass(slots=True)
class DocumentLanguageDetectionResult:
    quick_layout: dict
    detected_languages: list[str]


def _normalize_detected_languages(value: list[str] | None) -> list[str]:
    if not value:
        return []
    normalized: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        lang = item.strip().lower()
        if not lang or not lang.isalpha():
            continue
        if len(lang) < _MIN_LANG_CODE_LEN or len(lang) > _MAX_LANG_CODE_LEN:
            continue
        normalized.add(lang)
    return sorted(normalized)


def _normalize_text_input(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\t", " ")
    cleaned = re.sub(r"[ \xa0]+", " ", cleaned)
    return cleaned.strip()


def _split_long_block_into_sentences(block: str) -> list[str]:
    block = (block or "").strip()
    if not block:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁ0-9])", block)
    if len(parts) == 1:
        parts = re.split(r"(?<=[;:])\s+", block)
    result: list[str] = []
    for part in parts:
        part = part.strip()
        if len(part) >= _MIN_QUICK_TEXT_BLOCK_CHARS:
            result.append(part)
    return result or [block]


def _split_text_into_quick_blocks(text: str) -> list[str]:
    """
    Разбить OCR/plain text на pseudo-elements для language detection.

    Критически важно:
    - НЕ склеивать весь OCR текст в один giant element.
    - detect_languages_in_layout() определяет язык по элементам.
    - Если bilingual OCR текст схлопнуть в один element,
      lingua выберет только доминирующий язык.
    - Разбивка на строки/абзацы/предложения позволяет найти
      все реально присутствующие языки.
    """
    normalized = _normalize_text_input(text)
    if not normalized:
        return []

    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if len(lines) > 1:
        blocks: list[str] = []
        for line in lines:
            if len(line) >= _MIN_QUICK_TEXT_BLOCK_CHARS:
                if len(line) > _MAX_BLOCK_LEN_BEFORE_SENTENCE_SPLIT:
                    blocks.extend(_split_long_block_into_sentences(line))
                else:
                    blocks.append(line)
        return blocks

    paragraphs = [
        p.strip()
        for p in re.split(r"\n\s*\n", normalized)
        if p and p.strip()
    ]
    if len(paragraphs) > 1:
        blocks = []
        for p in paragraphs:
            if len(p) >= _MIN_QUICK_TEXT_BLOCK_CHARS:
                if len(p) > _MAX_BLOCK_LEN_BEFORE_SENTENCE_SPLIT:
                    blocks.extend(_split_long_block_into_sentences(p))
                else:
                    blocks.append(p)
        return blocks

    if len(normalized) > _MAX_BLOCK_LEN_BEFORE_SENTENCE_SPLIT:
        return _split_long_block_into_sentences(normalized)

    return [normalized] if len(normalized) >= _MIN_QUICK_TEXT_BLOCK_CHARS else []


def _build_quick_layout_from_text(*, text: str) -> dict:
    """
    Построить layout-совместимый объект из plain/OCR text.

    КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ:
    - раньше здесь создавался ОДИН element на весь документ;
    - теперь создаём несколько pseudo-elements по строкам/абзацам/предложениям.

    Это позволяет detect_languages_in_layout() находить все
    реально присутствующие языки, а не только доминирующий.
    """
    blocks = _split_text_into_quick_blocks(text)

    elements = [
        {
            "element_id": f"text_input_e{i:03d}",
            "type": "text",
            "text": block,
            "page": 1,
            "bbox": [0.0, float(i * 20), 500.0, float(i * 20 + 15)],
            "confidence": 1.0,
        }
        for i, block in enumerate(blocks, start=1)
    ]

    return {
        "elements": elements,
        "tables": [],
        "metadata": {
            "source": "text_input",
            "pages": 1,
            "quick_text_block_count": len(elements),
            "quick_text_total_chars": sum(len(el["text"]) for el in elements),
        },
    }


def detect_document_languages_from_pdf_bytes(
    *,
    pdf_bytes: bytes,
    document_id: str,
    document_version_id: str,
) -> DocumentLanguageDetectionResult:
    quick_layout = build_quick_layout_from_pdf(
        pdf_bytes=pdf_bytes,
        document_id=document_id,
        document_version_id=document_version_id,
    )
    raw_detected = detect_languages_in_layout(quick_layout)
    detected_languages = _normalize_detected_languages(raw_detected)

    logger.info(
        "Document language detection from PDF complete",
        document_id=document_id,
        document_version_id=document_version_id,
        detected_languages=detected_languages,
        detected_count=len(detected_languages),
        source_type="pdf_bytes",
    )

    return DocumentLanguageDetectionResult(
        quick_layout=quick_layout,
        detected_languages=detected_languages,
    )


def detect_document_languages_from_text(
    *,
    text: str,
    document_id: str,
    document_version_id: str,
) -> DocumentLanguageDetectionResult:
    cleaned_text = (text or "").strip()
    quick_layout = _build_quick_layout_from_text(text=cleaned_text)
    raw_detected = detect_languages_in_layout(quick_layout)
    detected_languages = _normalize_detected_languages(raw_detected)

    logger.info(
        "Document language detection from text complete",
        document_id=document_id,
        document_version_id=document_version_id,
        detected_languages=detected_languages,
        detected_count=len(detected_languages),
        source_type="text",
        text_length=len(cleaned_text),
        quick_text_block_count=len(quick_layout.get("elements") or []),
    )

    return DocumentLanguageDetectionResult(
        quick_layout=quick_layout,
        detected_languages=detected_languages,
    )
