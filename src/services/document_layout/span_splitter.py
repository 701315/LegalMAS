# src/services/document_layout/span_splitter.py

"""
Span Splitter Module (Layer 6).

Унифицированный сервис безопасного разделения многоязычных текстовых фрагментов:
- Рекурсивно применим для обычных строк текста и ячеек таблиц;
- Разделение по типографским разделителям (\, /, —, |, \n);
- Разделение по границам Unicode-скриптов;
- Оценка уверенности split_confidence (с отправкой в quarantine при confidence < 0.75).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.document_layout.config import layout_config
from services.document_layout.language_classifier import _detect_char_script, classify_text

logger = get_logger(__name__)


@dataclass(slots=True)
class SplitResult:
    target_text: str
    original_text: str
    split_method: str  # "separator" | "script_boundary" | "none"
    confidence: float
    is_split_successful: bool


def _split_by_script_boundary(text: str, target_language: str) -> str | None:
    """
    Разделяет смешанную строку по границе перехода между Unicode-скриптами.
    Универсально: работает для любой пары скриптов (Cyrillic, Latin, Han, Arabic и т.д.).
    """
    if not text:
        return None

    target_script = None
    for script, lang in layout_config.script_to_language.items():
        if lang == target_language:
            target_script = script
            break

    if not target_script:
        return None

    runs: list[tuple[str, str]] = []
    current_run: list[str] = []
    current_script: str | None = None

    for ch in text:
        script = _detect_char_script(ch)
        if script is not None:
            if script != current_script:
                if current_run and current_script:
                    runs.append((current_script, "".join(current_run)))
                current_run = [ch]
                current_script = script
            else:
                current_run.append(ch)
        else:
            if current_run:
                current_run.append(ch)

    if current_run and current_script:
        runs.append((current_script, "".join(current_run)))

    target_parts = []
    for r_script, r_text in runs:
        cleaned = r_text.strip()
        if r_script == target_script and len(cleaned) >= layout_config.min_substantive_letter_count:
            target_parts.append(cleaned)

    if target_parts:
        return " ".join(target_parts)

    return None


class SpanSplitter:
    """
    Универсальный сервис разделения смешанных текстовых подстрок.
    """

    def split_span(
        self,
        text: str,
        target_language: str,
    ) -> SplitResult:
        target_lang = target_language.lower().strip()
        stripped = text.strip()

        if not stripped:
            return SplitResult(
                target_text="",
                original_text=text,
                split_method="none",
                confidence=1.0,
                is_split_successful=False,
            )

        # 1. Попытка сплита по типографским разделителям
        for sep in layout_config.inline_cell_split_separators:
            if sep in stripped:
                parts = [p.strip() for p in stripped.split(sep) if p.strip()]
                if len(parts) >= 2:
                    for part in parts:
                        lang_class = classify_text(part)
                        if lang_class.language == target_lang:
                            return SplitResult(
                                target_text=part,
                                original_text=text,
                                split_method="separator",
                                confidence=0.90,
                                is_split_successful=True,
                            )

        # 2. Попытка сплита по границе Unicode-скриптов
        script_part = _split_by_script_boundary(stripped, target_lang)
        if script_part:
            return SplitResult(
                target_text=script_part,
                original_text=text,
                split_method="script_boundary",
                confidence=0.85,
                is_split_successful=True,
            )

        # 3. Не удалось разделить безопасно
        return SplitResult(
            target_text=text,
            original_text=text,
            split_method="none",
            confidence=0.50,
            is_split_successful=False,
        )
