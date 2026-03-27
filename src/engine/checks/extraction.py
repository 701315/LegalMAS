# src/engine/checks/extraction.py

"""
ExtractionExecutor: structured data extraction for a check.

Назначение:
- На основе ExtractionConfig в CheckDefinition извлечь структурированные поля
  из того же контекста, который используется для детекции риска.
- Вернуть payload, пригодный для записи в CheckResult.structured_data.
"""

from __future__ import annotations

import re
from typing import Any

from core.logging import get_logger
from ..detectors.extraction_llm_detector import ExtractionLLMDetector
from ..llm.client import LLMClient
from ..playbook.models import (
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)

logger = get_logger(__name__)

# Набор "мусорных" значений которые LLM возвращает когда не нашёл ответ.
# Все значения в нижнем регистре — сравниваем через .lower().strip()
_NULL_VALUES = frozenset(
    {
        "null",
        "none",
        "not_found",
        "n/a",
        "na",
        "не найдено",
        "отсутствует",
        "нет данных",
        "",
        "unknown",
        "неизвестно",
        "-",
        "—",
    }
)


def _is_null_value(raw: Any) -> bool:
    """
    Проверяет, является ли значение "пустым" ответом LLM или rules.

    Возвращает True если значение нужно отбросить (не добавлять в structured).
    Возвращает False если значение реальное и его нужно сохранить.
    """
    if raw is None:
        return True
    return str(raw).strip().lower() in _NULL_VALUES


class ExtractionExecutor:
    """
    Исполнитель structured-data извлечения.

    Интерфейс:
      run(doc, check, contexts, detection) -> dict | None

    На вход:
      - doc: ORM Document (для идентификатора).
      - check: CheckDefinition с полем extraction: ExtractionConfig | None.
      - contexts: тот же список чанков, что использовался в CheckExecutor
        (List[Dict] с ключами "id", "text", "metadata").
      - detection: словарь DetectionResult-подобного вида из HybridDetector.

    На выход:
      - dict с извлечёнными полями или None, если extraction отключён или ничего не нашли.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()
        self.llm_detector = ExtractionLLMDetector(self.llm_client)

    def run(
        self,
        doc: Any,
        check: CheckDefinition,
        contexts: list[dict[str, Any]],
        detection: dict[str, Any],
    ) -> dict[str, Any] | None:
        extraction_cfg: ExtractionConfig | None = getattr(check, "extraction", None)
        if not extraction_cfg or not extraction_cfg.enabled:
            return None

        mode = getattr(extraction_cfg, "mode", None)
        logger.debug(
            "ExtractionExecutor.run started",
            check_id=check.id,
            doc_id=str(getattr(doc, "id", None)),
            mode=str(mode),
        )

        # Базовый текст для извлечения: evidence из detection, а при необходимости — весь контекст.
        base_text = self._build_extraction_text(detection, contexts)
        if not base_text:
            return None

        # Локация риска из HybridDetector: page / clause_uid / element_id / ...
        # Это будет общей базовой location для всех полей, если LLM не вернул более точную.
        raw_location = detection.get("location") or None
        base_location: dict[str, Any] | None = None
        if isinstance(raw_location, dict):
            base_location = {
                "page": raw_location.get("page"),
                "clause_uid": raw_location.get("clause_uid"),
                "element_id": raw_location.get("element_id"),
                "start_page": raw_location.get("start_page"),
                "end_page": raw_location.get("end_page"),
                "path_titles": raw_location.get("path_titles"),
            }

        structured: dict[str, dict[str, Any]] = {}

        # 1. RULES часть (работает для mode == rules и для hybrid/llm как baseline)
        for field_cfg in extraction_cfg.fields or []:
            field_result = self._extract_field(field_cfg, base_text)
            if field_result is not None:
                # если rules не проставил location, используем общую base_location
                if "location" not in field_result or field_result.get("location") is None:
                    field_result["location"] = base_location
                structured[field_cfg.name] = field_result

        # 2. LLM / HYBRID часть
        # Если mode == "llm" или "hybrid" и LLM доступен, подтянем значения из LLM.
        if mode in {"llm", "hybrid"} and self.llm_client.is_available():
            try:
                llm_fields = self.llm_detector.extract(check, base_text)
            except Exception as e:
                logger.warning("LLM extraction failed", error=str(e))
                llm_fields = {}

            if llm_fields:
                for field_cfg in extraction_cfg.fields or []:
                    name = field_cfg.name
                    llm_payload = llm_fields.get(name)
                    if not llm_payload:
                        continue

                    value_raw = llm_payload.get("value")

                    # Фильтруем "мусорные" значения сразу после получения от LLM.
                    if _is_null_value(value_raw):
                        logger.debug(
                            "LLM returned null-like value for field, skipping",
                            field_name=name,
                            value_raw=str(value_raw),
                            check_id=check.id,
                        )
                        continue

                    conf_raw = llm_payload.get("confidence", 0.7)
                    try:
                        confidence_llm = float(conf_raw)
                    except (TypeError, ValueError):
                        confidence_llm = 0.7

                    # Локация конкретного поля, если LLM её вернул (иначе общая base_location).
                    field_location = llm_payload.get("location") or base_location

                    # Приводим к типу поля (MVP: через _cast_value)
                    value_cast = self._cast_value(field_cfg, str(value_raw))

                    if name not in structured:
                        # rules ничего не дал — используем LLM
                        structured[name] = {
                            "value": value_cast,
                            "unit": field_cfg.unit,
                            "source": "llm",
                            "confidence": confidence_llm,
                            "found": True,
                            "location": field_location,
                        }
                    else:
                        # оба дали значение — если LLM увереннее, заменим
                        if confidence_llm > structured[name].get("confidence", 0.0):
                            structured[name] = {
                                "value": value_cast,
                                "unit": field_cfg.unit,
                                "source": "llm",
                                "confidence": confidence_llm,
                                "found": True,
                                "location": field_location,
                            }

        # 3. Нормализация: гарантируем запись для каждого поля из extraction_cfg
        for field_cfg in extraction_cfg.fields or []:
            name = field_cfg.name

            if name in structured:
                field = structured[name]
                # дефолты
                field.setdefault("unit", field_cfg.unit)
                field.setdefault("source", field.get("source", "rules"))
                try:
                    field["confidence"] = float(field.get("confidence", 0.0))
                except (TypeError, ValueError):
                    field["confidence"] = 0.0
                field.setdefault("found", True)
                # каркас location и qc
                field.setdefault("location", None)
                field.setdefault(
                    "qc",
                    {
                        "status": "pending",
                        "by": None,
                        "comment": None,
                        "at": None,
                    },
                )
                continue

            # поле вообще не найдено ни rules, ни LLM — создаём "пустую" запись
            structured[name] = {
                "value": None,
                "unit": field_cfg.unit,
                "source": "none",
                "confidence": 0.0,
                "found": False,
                "location": None,
                "qc": {
                    "status": "pending",
                    "by": None,
                    "comment": None,
                    "at": None,
                },
            }

        if not structured:
            return None

        return structured

    def _build_extraction_text(
        self,
        detection: dict[str, Any],
        contexts: list[dict[str, Any]],
    ) -> str:
        """
        Сформировать текст, по которому будем делать extraction.

        Приоритет:
          1) detection["evidence"], если есть.
          2) иначе текст из всех contexts, склеенный.
        """
        evidence = detection.get("evidence") or ""
        if evidence.strip():
            return evidence

        parts: list[str] = []
        for c in contexts:
            text = c.get("text") or ""
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    def _extract_field(
        self,
        field_cfg: ExtractionFieldConfig,
        text: str,
    ) -> dict[str, Any] | None:
        """
        Извлечь одно поле по regex_patterns и keyword_hints.

        Возвращает:
          {"value": ..., "unit": ..., "source": "rules", "confidence": float, "found": bool}
          или None, если ничего не нашли или найденное значение — "мусор".
        """
        # 1. Regex-поиск: берём первый match из первого сработавшего паттерна.
        for pattern in field_cfg.regex_patterns or []:
            try:
                m = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            except re.error as e:
                logger.warning(
                    "Invalid regex pattern in ExtractionFieldConfig",
                    field_name=field_cfg.name,
                    pattern=pattern,
                    error=str(e),
                )
                continue

            if m:
                raw_value = m.group(1) if m.groups() else m.group(0)

                # Regex может поймать "N/A" или "не указано" прямо из текста договора.
                if _is_null_value(raw_value):
                    continue

                value = self._cast_value(field_cfg, raw_value)
                return {
                    "value": value,
                    "unit": field_cfg.unit,
                    "source": "rules",
                    "confidence": 0.8,
                    "found": True,
                }

        # 2. keyword_hints: если regex не сработал, попробуем понять "есть/нет" по ключевым словам.
        if field_cfg.keyword_hints:
            lowered = text.lower()
            hits = [kw for kw in field_cfg.keyword_hints if kw.lower() in lowered]
            if hits:
                if field_cfg.type == ExtractionFieldType.BOOLEAN:
                    value: Any = True
                else:
                    value = ", ".join(hits)

                # Для keyword_hints тоже применяем фильтр на всякий случай
                if _is_null_value(value):
                    return None

                return {
                    "value": value,
                    "unit": field_cfg.unit,
                    "source": "rules",
                    "confidence": 0.5,
                    "found": True,
                }

        return None

    def _cast_value(self, field_cfg: ExtractionFieldConfig, raw_value: str) -> Any:
        """
        Привести найденное значение к типу из ExtractionFieldConfig.

        Поддержка (MVP):
          - NUMBER: к float / int при возможности.
          - BOOLEAN: по простым паттернам ("yes/no", "да/нет", "true/false").
          - STRING: как есть.
        """
        field_type = field_cfg.type

        if field_type == ExtractionFieldType.NUMBER:
            cleaned = raw_value.replace(" ", "").replace(",", ".")
            try:
                num = float(cleaned)
                if num.is_integer():
                    return int(num)
                return num
            except ValueError:
                return raw_value

        if field_type == ExtractionFieldType.BOOLEAN:
            v = raw_value.strip().lower()
            true_vals = {"yes", "true", "1", "да", "верно"}
            false_vals = {"no", "false", "0", "нет", "неверно"}
            if v in true_vals:
                return True
            if v in false_vals:
                return False
            return raw_value

        # По умолчанию STRING
        return raw_value
