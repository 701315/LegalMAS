# src/engine/content/evidence_bundle_builder.py

"""
EvidenceBundleBuilder — построение evidence bundles из LegalUnit по retrieval profile.

Для непрофессионального программиста:
- До Этапа 6: детектор получал плоский список чанков и сам искал нужные.
  Это медленно и шумно — детектор видит весь документ.
- После Этапа 6: детектор получает отобранный EvidenceBundle —
  список релевантных LegalUnit уже отфильтрованных по теме и типу.

Что такое EvidenceBundle:
- primary_units: главные units которые непосредственно отвечают на вопрос
  (например, для проверки "есть ли governing_law?" — это units с темой governing_law)
- supporting_units: контекстные units (определения, ссылки и т.д.)
- query_topic: тема запроса ("governing_law", "liability_cap" и т.д.)
- confidence: насколько мы уверены что нашли правильные units

Архитектурная роль:
- Вызывается из check runner или retrieval layer.
- Принимает список LegalUnit (уже с topic_tags) и retrieval profile.
- Возвращает EvidenceBundle для конкретного check.
- Не знает про БД, MinIO, LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.structure.legal_unit_models import LegalUnit, LegalUnitType

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Модели
# ---------------------------------------------------------------------------

@dataclass
class EvidenceBundle:
    """
    Набор LegalUnit для одного check/query.

    query_topic:     тема запроса (из retrieval profile)
    primary_units:   главные релевантные units
    supporting_units: контекстные units (определения, cross-refs)
    confidence:      уверенность в полноте bundle [0.0..1.0]
    missing_topics:  темы которые ожидались но не найдены
    diagnostics:     дополнительная информация для debugging
    """
    query_topic: str
    primary_units: list[LegalUnit] = field(default_factory=list)
    supporting_units: list[LegalUnit] = field(default_factory=list)
    confidence: float = 0.0
    missing_topics: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def all_units(self) -> list[LegalUnit]:
        """Все units в bundle (primary + supporting, без дубликатов)."""
        seen: set[str] = set()
        result: list[LegalUnit] = []
        for unit in self.primary_units + self.supporting_units:
            if unit.unit_id not in seen:
                seen.add(unit.unit_id)
                result.append(unit)
        return result

    @property
    def is_empty(self) -> bool:
        return len(self.primary_units) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_topic": self.query_topic,
            "primary_units_count": len(self.primary_units),
            "supporting_units_count": len(self.supporting_units),
            "confidence": self.confidence,
            "missing_topics": self.missing_topics,
            "primary_unit_ids": [u.unit_id for u in self.primary_units],
            "supporting_unit_ids": [u.unit_id for u in self.supporting_units],
            "diagnostics": self.diagnostics,
        }


@dataclass
class RetrievalProfile:
    """
    Профиль поиска для конкретного типа check.

    profile_id:       идентификатор профиля ("governing_law_check")
    query_topic:      основная тема ("governing_law")
    required_topics:  темы которые должны быть найдены (primary)
    supporting_topics: темы для контекста (supporting)
    required_unit_types: типы units которые ищем
    min_citability:   минимальный citability_band ("high"/"medium"/"low")
    max_primary_units: максимум primary units в bundle
    max_supporting_units: максимум supporting units в bundle
    """
    profile_id: str
    query_topic: str
    required_topics: list[str] = field(default_factory=list)
    supporting_topics: list[str] = field(default_factory=list)
    required_unit_types: list[LegalUnitType] = field(default_factory=list)
    min_citability: str = "low"
    max_primary_units: int = 10
    max_supporting_units: int = 5


# ---------------------------------------------------------------------------
# EvidenceBundleBuilder
# ---------------------------------------------------------------------------

class EvidenceBundleBuilder:
    """
    Строит EvidenceBundle из списка LegalUnit по RetrievalProfile.

    Использование:
        builder = EvidenceBundleBuilder()
        bundle = builder.build(
            units=snapshot.units,
            profile=GOVERNING_LAW_PROFILE,
        )
        # bundle.primary_units содержит нормы про governing_law
    """

    def build(
        self,
        units: list[LegalUnit],
        profile: RetrievalProfile,
    ) -> EvidenceBundle:
        """
        Построить EvidenceBundle для конкретного profile.

        Алгоритм:
        1. Фильтруем units по min_citability.
        2. Ищем primary units: совпадение с required_topics.
        3. Ищем supporting units: совпадение с supporting_topics.
        4. Если required_unit_types задан — дополнительно фильтруем.
        5. Вычисляем confidence.
        6. Выявляем missing_topics.
        """
        bundle = EvidenceBundle(query_topic=profile.query_topic)

        if not units:
            bundle.missing_topics = list(profile.required_topics)
            bundle.diagnostics["reason"] = "no_units_provided"
            return bundle

        # Шаг 1: фильтр по citability
        citability_order = {"high": 3, "medium": 2, "low": 1}
        min_citability_score = citability_order.get(profile.min_citability, 1)

        eligible_units = [
            u for u in units
            if citability_order.get(u.citability.citability_band, 0) >= min_citability_score
        ]

        bundle.diagnostics["total_units"] = len(units)
        bundle.diagnostics["eligible_units"] = len(eligible_units)

        # Шаг 2: primary units — совпадение с required_topics
        required_topics_set = set(profile.required_topics)
        type_filter = set(profile.required_unit_types) if profile.required_unit_types else None

        primary_candidates: list[tuple[LegalUnit, int]] = []  # (unit, match_score)

        for unit in eligible_units:
            unit_topics = set(unit.topic_tags)
            topic_matches = len(unit_topics & required_topics_set)

            if topic_matches == 0:
                continue

            # Дополнительно проверяем unit_type если задан фильтр
            if type_filter and unit.unit_type not in type_filter:
                continue

            # Score: topic_matches + bonus за citability + bonus за unit_type
            score = topic_matches
            if unit.citability.citability_band == "high":
                score += 2
            elif unit.citability.citability_band == "medium":
                score += 1

            if type_filter and unit.unit_type in type_filter:
                score += 3

            primary_candidates.append((unit, score))

        # Сортируем по score убывание, потом по page_start для determinism
        primary_candidates.sort(key=lambda x: (-x[1], x[0].page_start))
        primary_units = [u for u, _ in primary_candidates[:profile.max_primary_units]]
        bundle.primary_units = primary_units

        # Шаг 3: supporting units — совпадение с supporting_topics
        supporting_topics_set = set(profile.supporting_topics)
        primary_ids = {u.unit_id for u in primary_units}

        supporting_candidates: list[tuple[LegalUnit, int]] = []

        for unit in eligible_units:
            if unit.unit_id in primary_ids:
                continue  # уже в primary

            unit_topics = set(unit.topic_tags)
            topic_matches = len(unit_topics & supporting_topics_set)

            if topic_matches == 0:
                continue

            # Проверяем cross-refs: если unit ссылается на primary — это supporting
            cross_ref_bonus = 0
            for ref in unit.cross_refs:
                if ref.target_unit_id and ref.target_unit_id in primary_ids:
                    cross_ref_bonus += 2

            score = topic_matches + cross_ref_bonus
            supporting_candidates.append((unit, score))

        supporting_candidates.sort(key=lambda x: (-x[1], x[0].page_start))
        bundle.supporting_units = [
            u for u, _ in supporting_candidates[:profile.max_supporting_units]
        ]

        # Шаг 4: missing_topics
        found_topics: set[str] = set()
        for unit in primary_units:
            found_topics.update(unit.topic_tags)

        bundle.missing_topics = [
            topic for topic in profile.required_topics
            if topic not in found_topics
        ]

        # Шаг 5: confidence
        bundle.confidence = self._compute_confidence(
            primary_units=primary_units,
            required_topics=profile.required_topics,
            found_topics=found_topics,
        )

        bundle.diagnostics.update({
            "primary_candidates_before_limit": len(primary_candidates),
            "supporting_candidates_before_limit": len(supporting_candidates),
            "required_topics": list(profile.required_topics),
            "found_topics": list(found_topics),
            "missing_topics": list(bundle.missing_topics),
        })

        logger.debug(
            "EvidenceBundleBuilder: bundle built",
            extra={
                "profile_id": profile.profile_id,
                "query_topic": profile.query_topic,
                "primary_count": len(primary_units),
                "supporting_count": len(bundle.supporting_units),
                "confidence": bundle.confidence,
                "missing_topics": bundle.missing_topics,
            },
        )

        return bundle

    def build_multi(
        self,
        units: list[LegalUnit],
        profiles: list[RetrievalProfile],
    ) -> dict[str, EvidenceBundle]:
        """
        Построить EvidenceBundle для нескольких profiles за один проход.

        Возвращает dict: profile_id -> EvidenceBundle.
        """
        results: dict[str, EvidenceBundle] = {}
        for profile in profiles:
            results[profile.profile_id] = self.build(units=units, profile=profile)

        logger.info(
            "EvidenceBundleBuilder: multi-build complete",
            extra={
                "profiles_count": len(profiles),
                "total_units": len(units),
                "bundles_with_primary": sum(
                    1 for b in results.values() if not b.is_empty
                ),
            },
        )

        return results

    def _compute_confidence(
        self,
        primary_units: list[LegalUnit],
        required_topics: list[str],
        found_topics: set[str],
    ) -> float:
        """
        Вычислить confidence bundle.

        Факторы:
        - Доля required_topics которые были найдены.
        - Среднее citability_score primary units.
        - Штраф если нет primary units.
        """
        if not primary_units:
            return 0.0

        citability_scores = {
            "high": 0.9,
            "medium": 0.6,
            "low": 0.3,
        }

        avg_citability = sum(
            citability_scores.get(u.citability.citability_band, 0.3)
            for u in primary_units
        ) / len(primary_units)

        if required_topics:
            topic_coverage = len(
                set(required_topics) & found_topics
            ) / len(required_topics)
        else:
            topic_coverage = 1.0 if primary_units else 0.0

        confidence = avg_citability * 0.6 + topic_coverage * 0.4
        return round(min(1.0, max(0.0, confidence)), 3)
    

