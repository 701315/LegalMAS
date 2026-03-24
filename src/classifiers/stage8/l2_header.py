# src/classifiers/stage8/l2_header.py

"""
L2 Header Classifier — классификация по заголовку документа (Stage 8).

Назначение:
- Второй уровень каскада после L1.
- Анализирует заголовок / шапку документа (первые строки текста) и
  ищет характерные шаблоны для типов документов.

Источники сигналов:
- YAMLRegistry.get_all_configs() возвращает DocumentTypeConfig для каждого типа.
- В DocumentTypeConfig ожидаются:
  - header_patterns (compiled regex) — характерные паттерны шапки;
  - keywords_high / keywords_medium / keywords_low — ключевые слова;
  - exclusions — слова/фразы, которые подавляют тип.

Как работает:
- На вход подаётся уже извлечённый header_text.
- Для каждого типа:
  - матчим header_patterns (regex);
  - считаем попадания по keywords_high/medium/low (строки);
  - считаем exclusions (строки).
- На основании количества попаданий по уровням и exclusions вычисляем confidence.

Роль в каскаде:
- L2 даёт более надёжный сигнал, чем L1.
- При высокой уверенности и отсутствии exclusions HybridClassifier может остановиться на L2.
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

from ..base import BaseClassifier, ClassificationResult
from ..yaml_registry import YAMLRegistry, DocumentTypeConfig
from core.config import settings
from core.constants import ClassificationLevel
from core.logging import get_logger

logger = get_logger(__name__)


class L2HeaderClassifier(BaseClassifier):
    """
    L2: Header/keyword classifier на базе YAMLRegistry.

    Ожидает, что DocumentTypeConfig формирует для каждого типа:
      - header_patterns (compiled regex, re.IGNORECASE),
      - keywords_high / keywords_medium / keywords_low (compiled regex),
      - exclusions (compiled regex из classification_runtime_v1.rules.exclusions).
    """


    def __init__(self, registry: YAMLRegistry | None = None) -> None:
        # Используем singleton по умолчанию, но даём возможность подменять в тестах.
        self._registry = registry or YAMLRegistry.get_instance()

    @property
    def level(self) -> ClassificationLevel:
        """Возвращает агрегированный уровень каскада для этого классификатора."""
        return ClassificationLevel.L2_KEYWORDS

    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        """
        Классификация по заголовку/шапке.

        text — сюда должен приходить уже подготовленный header_text (или полный текст,
        из которого первые строки содержат заголовок).
        filename, folder_path, text_sanitized, metadata — сейчас не используются.
        """
        header_text = (text or "").strip()

        logger.info(
            "L2 classify start",
            extra={
                "filename": filename,
                "folder_path": folder_path,
                "header_len": len(header_text),
                "header_preview": repr(header_text[:400]),
            },
        )

        # Если заголовка нет, сразу возвращаем UNKNOWN с нулевой уверенностью.
        if not header_text:
            logger.info(
                "L2 final result",
                extra={
                    "best_type": "UNKNOWN",
                    "best_conf": 0.0,
                    "best_evidence": None,
                    "best_extra": None,
                },
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="header_pattern",
                evidence=None,
            )

        best_type: str = "UNKNOWN"
        best_conf: float = 0.0
        best_evidence: Optional[str] = None
        best_extra: Dict[str, Any] = {}

        base_conf = float(getattr(settings, "CLASSIFICATION_L2_ACCEPT", 0.75))
        excl_hard_threshold = int(getattr(settings, "CLASSIFICATION_L2_EXCL_HARD", 2))
        excl_soft_threshold = int(getattr(settings, "CLASSIFICATION_L2_EXCL_SOFT", 1))

        # Перебираем все doc_types из реестра.
        for cfg in self._registry.get_all_configs():
            cfg: DocumentTypeConfig

            header_patterns = getattr(cfg, "header_patterns", []) or []
            keywords_high = getattr(cfg, "keywords_high", []) or []
            keywords_medium = getattr(cfg, "keywords_medium", []) or []
            keywords_low = getattr(cfg, "keywords_low", []) or []
            exclusion_keywords = getattr(cfg, "exclusions", []) or []

            if (
                not header_patterns
                and not keywords_high
                and not keywords_medium
                and not keywords_low
                and not exclusion_keywords
            ):
                continue

            high_hits = 0
            medium_hits = 0
            low_hits = 0
            exclusion_hits = 0
            matched_patterns: List[str] = []

            logger.debug(
                "L2 patterns used",
                extra={
                    "type_code": cfg.type_code,
                    "header_patterns": [
                        getattr(p, "pattern", str(p)) for p in header_patterns[:10]
                    ],
                    "keywords_high": keywords_high[:10],
                    "keywords_medium": keywords_medium[:10],
                    "keywords_low": keywords_low[:10],
                    "exclusions": exclusion_keywords[:10],
                },
            )

            # 1) Матчим header_patterns (compiled regex с IGNORECASE).
            for p in header_patterns:
                try:
                    if p.search(header_text):
                        # Все header_patterns считаем как medium-сигнал заголовка,
                        # более тонкая градация идёт через keywords_*.
                        medium_hits += 1
                        matched_patterns.append(getattr(p, "pattern", str(p)))
                except Exception as e:
                    logger.warning(
                        "Invalid header pattern in YAMLRegistry",
                        extra={
                            "pattern": getattr(p, "pattern", str(p)),
                            "type_code": cfg.type_code,
                            "error": str(e),
                        },
                    )

            # Вспомогательная функция для списков regex-паттернов.
            def _match_patterns(patterns: List[Any]) -> int:
                """
                Считает, сколько regex-паттернов из списка нашли совпадение в header_text.

                Ожидает, что patterns — это списки re.Pattern, подготовленные YAMLRegistry.
                Если в списке случайно окажется строка, мы попытаемся
                скомпилировать её на лету, чтобы не ломать работу.
                """
                hits = 0
                for p in patterns or []:
                    try:
                        if hasattr(p, "search"):
                            regex = p
                        else:
                            # fallback для строк, если где-то остались необработанные значения
                            pattern_str = (str(p) or "").strip()
                            if not pattern_str:
                                continue
                            regex = re.compile(pattern_str)
                        if regex.search(header_text):
                            hits += 1
                            matched_patterns.append(getattr(regex, "pattern", str(regex)))
                    except Exception as e:
                        logger.warning(
                            "L2 keyword/exclusion pattern error",
                            extra={
                                "type_code": cfg.type_code,
                                "pattern": getattr(p, "pattern", str(p)),
                                "error": str(e),
                            },
                        )
                return hits

            # 2) Матчим keywords по уровням.
            high_hits += _match_patterns(keywords_high)
            medium_hits += _match_patterns(keywords_medium)
            low_hits += _match_patterns(keywords_low)

            # 3) Матчим exclusions.
            exclusion_hits += _match_patterns(exclusion_keywords)

            # Если нет ни одного позитивного попадания — этот тип не рассматриваем.
            if high_hits == 0 and medium_hits == 0 and low_hits == 0:
                continue

            has_exclusion_hit = exclusion_hits > 0

            # --- Жёсткое подавление типа при сильных exclusions ---
            if exclusion_hits >= excl_hard_threshold:
                logger.info(
                    "L2 type suppressed by exclusions",
                    extra={
                        "type_code": cfg.type_code,
                        "high_hits": high_hits,
                        "medium_hits": medium_hits,
                        "low_hits": low_hits,
                        "exclusion_hits": exclusion_hits,
                    },
                )
                continue

            # --- Расчёт confidence ---
            conf = 0.0

            # При мягком exclusion (одиночный хит) не запрещаем тип, но сильно режем потолок.
            if has_exclusion_hit and exclusion_hits < excl_hard_threshold:
                penalty_cap = 0.4
            else:
                penalty_cap = 1.0

            if high_hits > 0:
                # High-сигналы обязательны для «уверенного» типа.
                # base_conf — базовая уверенность L2 при наличии хотя бы одного high.
                conf = base_conf

                # High дают основную массу уверенности.
                conf += 0.15 * min(high_hits, 3)      # максимум +0.45

                # Medium/low лишь слегка докручивают сверху.
                conf += 0.03 * min(medium_hits, 4)    # максимум +0.12
                conf += 0.01 * min(low_hits, 5)       # максимум +0.05
            else:
                # Без high: medium/low дают только слабый сигнал.
                # Используются как подсказка, но не могут конкурировать с L3 и L1.
                conf = 0.1 * min(medium_hits, 4) + 0.03 * min(low_hits, 5)
                # Жёсткий потолок для случаев без high-хитов.
                conf = min(conf, 0.4)

            # Применяем потолок при мягких exclusions.
            conf = min(conf, penalty_cap)

            # Нормализация.
            conf = max(0.0, min(1.0, conf))

            logger.info(
                "L2 type stats",
                extra={
                    "type_code": cfg.type_code,
                    "high_hits": high_hits,
                    "medium_hits": medium_hits,
                    "low_hits": low_hits,
                    "exclusion_hits": exclusion_hits,
                    "has_exclusion_hit": has_exclusion_hit,
                    "conf": conf,
                },
            )

            # Обновляем лучший тип, если уверенность выше.
            if conf > best_conf:
                best_conf = conf
                best_type = cfg.type_code
                best_evidence = (
                    f"high={high_hits}, medium={medium_hits}, low={low_hits}, "
                    f"exclusions={exclusion_hits}; patterns={matched_patterns[:10]}"
                )
                best_extra = {
                    "high_hits": high_hits,
                    "medium_hits": medium_hits,
                    "low_hits": low_hits,
                    "exclusion_hits": exclusion_hits,
                    "has_exclusion_hit": has_exclusion_hit,
                    "matched_type": cfg.type_code,
                }

        logger.info(
            "L2 final result",
            extra={
                "best_type": best_type,
                "best_conf": best_conf,
                "best_evidence": best_evidence,
                "best_extra": best_extra or None,
            },
        )

        return ClassificationResult(
            doctype=best_type,
            confidence=best_conf,
            level=self.level,
            method="header_pattern",
            evidence=best_evidence,
            extra=best_extra or None,
        )
