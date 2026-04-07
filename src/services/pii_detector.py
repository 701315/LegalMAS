# src/services/pii_detector.py

"""
PII Detector.

Обнаруживает PII‑сущности в тексте гибридным подходом:
- детерминированные regex‑паттерны для структурированных идентификаторов
  (ИНН, ОГРН, кадастровый номер, паспорт, телефон, email, адрес);
- опциональный NER на базе natasha для имён персон (PERSON_NAME).

Основные части:
- PIIEntity — единая модель найденной сущности (тип, span, текст, confidence, источник);
- get_preserve_types() — динамически строит набор типов, которые не токенизируются,
  исходя из settings (PII_PRESERVE_INN/OGRN/CADASTRAL);
- PIIDetector.detect(...) — находит сущности в тексте: сначала контекстные
  паттерны (ИНН/ОГРН/паспорт с ключевыми словами), затем общие паттерны, затем
  NER‑имена, после чего удаляет пересечения с приоритетом контекстных матчей;
- get_pii_detector()/reset_detector() — singleton‑фабрика для детектора, чтобы
  переиспользовать NER и настройки в пайплайне.
"""

import re
from dataclasses import dataclass
from core.config import settings
from core.constants import PIIEntityType
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PIIEntity:
    """Найденная PII-сущность."""

    type: PIIEntityType
    start: int
    end: int
    text: str
    confidence: float = 1.0
    source: str = "regex"  # "regex" или "ner"

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)


# ═══════════════════════════════════════════════════════════════════════════════
# Regex patterns
#
# ВАЖНО: паттерны упорядочены по приоритету при дедупликации.
# ИНН/ОГРН/кадастр проверяются РАНЬШЕ паспорта, чтобы 10-значный ИНН
# не был ошибочно распознан как паспорт.
# ═══════════════════════════════════════════════════════════════════════════════

# Паттерны с контекстом (высокий приоритет)
_CONTEXT_PATTERNS: list[tuple[PIIEntityType, re.Pattern]] = [
    # ИНН с контекстом — высший приоритет
    (PIIEntityType.INN, re.compile(r"(?:ИНН|инн|INN)\s*[:.]?\s*(\d{10}|\d{12})", re.IGNORECASE)),
    # ОГРН с контекстом
    (
        PIIEntityType.OGRN,
        re.compile(r"(?:ОГРН|огрн|ОГРНИП|огрнип)\s*[:.]?\s*(\d{13}|\d{15})", re.IGNORECASE),
    ),
    # Паспорт с контекстом
    (
        PIIEntityType.PASSPORT,
        re.compile(
            r"(?:паспорт|серия|passport)\s*[:.]?\s*(\d{2}\s?\d{2})\s*(?:№|номер|N|n)?\s*[:.]?\s*(\d{6})",
            re.IGNORECASE,
        ),
    ),
]

# Паттерны без контекста (проверяются после контекстных)
_PATTERNS: dict[PIIEntityType, re.Pattern] = {
    # Паспорт: ОБЯЗАТЕЛЬНЫЙ пробел между серией и номером (4+6 цифр)
    # Это отличает от 10-значного ИНН без пробела
    PIIEntityType.PASSPORT: re.compile(r"\b(\d{4})\s(\d{6})\b"),
    # Телефон
    PIIEntityType.PHONE: re.compile(
        r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
    ),
    # Email
    PIIEntityType.EMAIL: re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}", re.IGNORECASE),
    # Адрес
    PIIEntityType.ADDRESS: re.compile(
        r"(?:ул\.|улица|пр\.|проспект|пер\.|переулок|д\.|дом|кв\.|квартира)"
        r"\s+[А-ЯЁа-яёA-Za-z0-9\s,\.\-]+",
        re.IGNORECASE,
    ),
    # ИНН без контекста — только 12 цифр (физлицо), чтобы не конфликтовать с паспортом
    # 10-значный ИНН требует контекста "ИНН"
    PIIEntityType.INN: re.compile(r"\b(\d{12})\b"),
    # ОГРН без контекста — 13 или 15 цифр (не конфликтует с другими)
    PIIEntityType.OGRN: re.compile(r"\b(\d{13}|\d{15})\b"),
    # Кадастровый номер — уникальный формат
    PIIEntityType.CADASTRAL: re.compile(r"\b\d{2}:\d{2}:\d{6,7}:\d{1,6}\b"),
}


def get_preserve_types() -> frozenset[PIIEntityType]:
    """
    Получить набор типов PII, которые НЕ токенизируются.

    Строится динамически из настроек.
    """

    preserve = set()
    if settings.PII_PRESERVE_INN:
        preserve.add(PIIEntityType.INN)
    if settings.PII_PRESERVE_OGRN:
        preserve.add(PIIEntityType.OGRN)
    if settings.PII_PRESERVE_CADASTRAL:
        preserve.add(PIIEntityType.CADASTRAL)

    return frozenset(preserve)


class PIIDetector:
    """
    Детектор PII-сущностей.

    Использует:
    - Regex для структурированных данных
    - Natasha NER для person names (опционально)
    """

    def __init__(self, ner_enabled: bool = True):
        """
        Args:
            ner_enabled: Включить NER через natasha
        """
        self._ner = None
        self._ner_enabled = ner_enabled

        if ner_enabled:
            self._init_ner()

    def _init_ner(self) -> None:
        """Ленивая инициализация NER."""
        try:
            from natasha import MorphVocab, NamesExtractor

            morph = MorphVocab()
            self._ner = NamesExtractor(morph)
            logger.info("natasha NER initialized")
        except ImportError as e:
            logger.warning(f"natasha not available, regex-only mode: {e}")
        except Exception as e:
            logger.warning(f"NER init failed: {e}")

    def detect(self, text: str) -> list[PIIEntity]:
        """
        Обнаружить PII-сущности в тексте.

        Returns:
            Список PIIEntity, отсортированный по позиции, без пересечений.
        """
        if not text or not text.strip():
            return []

        entities: list[PIIEntity] = []

        # 1. Контекстные паттерны (высокий приоритет)
        for entity_type, pattern in _CONTEXT_PATTERNS:
            for match in pattern.finditer(text):
                # Берём полное совпадение
                entities.append(
                    PIIEntity(
                        type=entity_type,
                        start=match.start(),
                        end=match.end(),
                        text=match.group(),
                        confidence=1.0,
                        source="regex_context",
                    )
                )

        # 2. Обычные паттерны
        for entity_type, pattern in _PATTERNS.items():
            for match in pattern.finditer(text):
                entities.append(
                    PIIEntity(
                        type=entity_type,
                        start=match.start(),
                        end=match.end(),
                        text=match.group(),
                        confidence=1.0,
                        source="regex",
                    )
                )

        # 3. NER person names
        if self._ner:
            entities.extend(self._detect_person_names(text))

        # 4. Дедупликация и сортировка
        # Контекстные паттерны имеют приоритет (добавлены первыми)
        return _deduplicate_overlapping(sorted(entities, key=lambda e: (e.start, -len(e.text))))

    def _detect_person_names(self, text: str) -> list[PIIEntity]:
        """Детекция имён через NER."""
        result = []
        try:
            for match in self._ner(text).matches:
                span = match.span
                result.append(
                    PIIEntity(
                        type=PIIEntityType.PERSON_NAME,
                        start=span.start,
                        end=span.stop,
                        text=text[span.start : span.stop],
                        confidence=0.9,
                        source="ner",
                    )
                )
        except Exception as e:
            logger.debug(f"NER extraction failed: {e}")
        return result


def _deduplicate_overlapping(entities: list[PIIEntity]) -> list[PIIEntity]:
    """
    Удалить пересекающиеся сущности.

    Приоритет:
    1. Более ранние в списке (контекстные паттерны добавляются первыми)
    2. Более длинные spans при равной позиции

    Entities должны быть отсортированы по (start, -length).
    """
    if not entities:
        return []

    result: list[PIIEntity] = []
    for ent in entities:
        # Проверяем пересечение с уже добавленными
        has_overlap = False
        for existing in result:
            if ent.start < existing.end and ent.end > existing.start:
                has_overlap = True
                break

        if not has_overlap:
            result.append(ent)

    # Финальная сортировка по позиции
    return sorted(result, key=lambda e: e.start)


# ═══════════════════════════════════════════════════════════════════════════════
# Factory function
# ═══════════════════════════════════════════════════════════════════════════════

_detector_instance: PIIDetector | None = None


def get_pii_detector(ner_enabled: bool | None = None) -> PIIDetector:
    """
    Получить singleton-экземпляр детектора.

    Args:
        ner_enabled: Включить NER. None = использовать settings.PII_NER_ENABLED
    """
    global _detector_instance

    if _detector_instance is None:
        if ner_enabled is None:

            ner_enabled = settings.PII_NER_ENABLED

        _detector_instance = PIIDetector(ner_enabled=ner_enabled)

    return _detector_instance


def reset_detector() -> None:
    """Сбросить singleton (для тестов)."""
    global _detector_instance
    _detector_instance = None
