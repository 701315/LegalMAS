"""
Language Classifier Module (Phase 3).

Отвечает за универсальную классификацию языка канонических атомов:
- Анализ скриптов символов Unicode (Cyrillic, Latin, Han, Arabic и др.);
- Определение 4 категорий: ISO 639-1 / shared / mixed;
- Формирование доказательной базы LanguageEvidence для каждого атома;
- Конфигурируемые пороги из layout_config.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from core.logging import get_logger
from services.document_layout.config import layout_config
from services.document_layout.schemas import (
    CanonicalAtom,
    LanguageClassification,
    LanguageEvidence,
)

logger = get_logger(__name__)


def _detect_char_script(char: str) -> str | None:
    """
    Определяет скрипт символа Unicode по его кодовой точке.
    Возвращает имя скрипта (например, 'Cyrillic', 'Latin') или None для не-букв.
    """
    if not unicodedata.category(char).startswith("L"):
        return None

    cp = ord(char)

    # Кириллица (основная + расширенная)
    if (0x0400 <= cp <= 0x04FF) or (0x0500 <= cp <= 0x052F) or (0x2DE0 <= cp <= 0x2DFF):
        return "Cyrillic"

    # Латиница (Basic, Supplement, Extended A/B)
    if (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A) or (0x00C0 <= cp <= 0x024F):
        return "Latin"

    # Китайские иероглифы (CJK Unified Ideographs)
    if (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF):
        return "Han"

    # Арабский
    if 0x0600 <= cp <= 0x06FF:
        return "Arabic"

    # Деванагари (Хинди)
    if 0x0900 <= cp <= 0x097F:
        return "Devanagari"

    # Корейский (Хангыль)
    if (0xAC00 <= cp <= 0xD7AF) or (0x1100 <= cp <= 0x11FF):
        return "Hangul"

    # Японский (Хирагана / Катакана)
    if 0x3040 <= cp <= 0x309F:
        return "Hiragana"
    if 0x30A0 <= cp <= 0x30FF:
        return "Katakana"

    # Fallback по имени символа из базы данных Unicode
    name = unicodedata.name(char, "")
    for script in layout_config.script_to_language.keys():
        if script.upper() in name:
            return script

    return "Other"


def classify_text(text: str) -> LanguageClassification:
    """
    Классифицирует язык переданного текста на основе распределения Unicode-скриптов.

    Возвращает:
        LanguageClassification с языковым кодом (ISO 639-1, 'shared', 'mixed'),
        уверенностью (0.0-1.0) и доказательной базой LanguageEvidence.
    """
    if not text or not text.strip():
        return LanguageClassification(
            language="shared",
            confidence=1.0,
            evidence=LanguageEvidence(
                cyrillic_chars=0,
                latin_chars=0,
                total_letters=0,
                classification_method="shared_no_letters",
            ),
        )

    script_counts: dict[str, int] = {}
    total_letters = 0

    for ch in text:
        script = _detect_char_script(ch)
        if script:
            script_counts[script] = script_counts.get(script, 0) + 1
            total_letters += 1

    cyrillic_chars = script_counts.get("Cyrillic", 0)
    latin_chars = script_counts.get("Latin", 0)

    evidence_base = LanguageEvidence(
        cyrillic_chars=cyrillic_chars,
        latin_chars=latin_chars,
        total_letters=total_letters,
        classification_method="script_dominant",
    )

    # 1. Если букв слишком мало -> 'shared' (цифры, пунктуация, маркеры)
    if total_letters < layout_config.min_absolute_letter_count:
        return LanguageClassification(
            language="shared",
            confidence=1.0,
            evidence=LanguageEvidence(
                cyrillic_chars=cyrillic_chars,
                latin_chars=latin_chars,
                total_letters=total_letters,
                classification_method="shared_no_letters",
            ),
        )

    # 2. Проверяем наличие значимых букв из >= 2 скриптов -> 'mixed'
    substantive_scripts = [
        script
        for script, count in script_counts.items()
        if count >= layout_config.min_substantive_letter_count
    ]

    if len(substantive_scripts) >= 2:
        return LanguageClassification(
            language="mixed",
            confidence=0.85,
            evidence=LanguageEvidence(
                cyrillic_chars=cyrillic_chars,
                latin_chars=latin_chars,
                total_letters=total_letters,
                classification_method="mixed_scripts",
            ),
        )

    # 3. Находим доминирующий скрипт
    dominant_script, dominant_count = max(
        script_counts.items(), key=lambda item: item[1]
    )
    dominant_ratio = dominant_count / max(total_letters, 1)

    lang_code = layout_config.script_to_language.get(dominant_script, "en")

    if dominant_ratio >= layout_config.dominant_script_ratio:
        confidence = round(dominant_ratio, 3)
    else:
        confidence = round(max(dominant_ratio, 0.5), 3)

    return LanguageClassification(
        language=lang_code,
        confidence=confidence,
        evidence=evidence_base,
    )


class LanguageClassifier:
    """
    Сервис классификации языков канонических атомов.
    """

    def classify_atoms(
        self,
        atoms: list[CanonicalAtom],
    ) -> list[CanonicalAtom]:
        """
        Классифицирует язык каждого атома и возвращает обогащенный список.
        """
        if not atoms:
            return []

        logger.info(
            "Starting language classification pass",
            atoms_count=len(atoms),
        )

        classified_atoms: list[CanonicalAtom] = []
        lang_distribution: dict[str, int] = {}

        for atom in atoms:
            classification = classify_text(atom.text)

            enriched_atom = atom.model_copy(
                update={
                    "language": classification.language,
                    "language_confidence": classification.confidence,
                    "language_evidence": classification.evidence,
                }
            )
            classified_atoms.append(enriched_atom)

            lang = classification.language
            lang_distribution[lang] = lang_distribution.get(lang, 0) + 1

        logger.info(
            "Language classification completed",
            total_atoms=len(atoms),
            distribution=lang_distribution,
        )

        return classified_atoms
