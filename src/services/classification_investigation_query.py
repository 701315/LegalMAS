# src/services/classification_investigation_query.py

"""
Read-model сервис для explainability / investigation классификации документов.

Для непрофессионального программиста:

- Этот сервис НИЧЕГО не меняет в базе данных.
- Он только читает документы и их classification_details и превращает их
  в удобные Pydantic-модели для API:

  * список документов сделки с краткими explainability-бейджами;
  * подробные данные по одному документу: какие уровни сработали,
    какие кандидаты рассматривались, какое было голосование и т.п.

- Сервис не отвечает за запуск классификации, только за расследование
  уже сохранённых результатов.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.classification_investigation import (
    ClassificationCandidateResponse,
    ClassificationInvestigationDetailResponse,
    ClassificationInvestigationListResponse,
    ClassificationInvestigationRow,
    ClassificationInvestigationSummary,
    ClassificationLevelResultResponse,
    ClassificationSegmentSummaryResponse,
    ClassificationVotingResponse,
)
from api.schemas.documents import DocumentCompositionSummary
from db.models.document import Document
from db.repositories.document_repo import DocumentRepository
from services.document_composition_query import DocumentCompositionQueryService


class ClassificationInvestigationQueryService:
    """
    Read-only сервис для получения explainability-данных по классификации документов.

    Публичные методы:

    - get_deal_page(...)      — список документов сделки с краткой сводкой.
    - get_document_detail(...) — подробный разбор классификации по одному документу.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._document_repo = DocumentRepository(session)
        self._composition_service = DocumentCompositionQueryService(session)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    async def get_deal_page(
        self,
        *,
        deal_id: uuid.UUID,
        page: int = 1,
        per_page: int = 20,
    ) -> ClassificationInvestigationListResponse:
        """
        Вернуть страницу документов сделки с краткой explainability-информацией.

        Для непрофессионального программиста:

        - Мы берём N документов сделки для указанной страницы.
        - Для этих документов считаем composition (single/multi/primary segment).
        - Для ВСЕХ документов сделки считаем summary-статистику:
          * сколько всего документов;
          * сколько классифицировано;
          * сколько требует ручной проверки;
          * сколько UNKNOWN;
          * сколько документов, где сработал L4;
          * сколько документов с противоречивыми сигналами (contradiction).
        """
        if page < 1:
            page = 1
        if per_page < 1:
            per_page = 20

        # 1) Пагинированный список документов для текущей страницы.
        page_docs, total = await self._document_repo.get_page_for_deal(
            deal_id=deal_id,
            page=page,
            per_page=per_page,
            include_classification=True,
        )

        # 2) Все документы сделки для корректной summary (по всей сделке, а не по странице).
        all_docs = await self._document_repo.list_by_deal_id(deal_id=deal_id)

        # 3) Строим composition только для документов на текущей странице.
        compositions = await self._composition_service.build_for_documents(page_docs)

        # 4) Собираем строки для таблицы.
        items: list[ClassificationInvestigationRow] = []
        for doc in page_docs:
            composition = compositions.get(doc.id)
            raw_result, raw_details = self._unwrap_classification_payload(doc)
            row = self._build_row(
                doc=doc,
                composition=composition,
                raw_result=raw_result,
                raw_details=raw_details,
            )
            items.append(row)

        # 5) Считаем summary по всей сделке.
        summary = self._build_summary(all_docs)

        # 6) Метаданные пагинации.
        total_pages = math.ceil(total / per_page) if per_page > 0 else 1
        has_next = page < total_pages
        has_previous = page > 1

        return ClassificationInvestigationListResponse(
            summary=summary,
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
        )

    async def get_document_detail(
        self,
        *,
        document_id: uuid.UUID,
    ) -> ClassificationInvestigationDetailResponse | None:
        """
        Вернуть подробный explainability detail по одному документу.

        Для непрофессионального программиста:

        - Берём один документ из базы.
        - Строим composition для этого документа (через сервис сегментов).
        - Из classification_details достаём:
          * какие уровни работали (L1/L2/L3/L4);
          * какие кандидаты типов рассматривались;
          * как сработало голосование;
          * был ли L4-фолбэк и почему;
          * были ли противоречивые сигналы.
        - Возвращаем Pydantic-модель для API.
        """
        doc = await self._document_repo.get_by_id(document_id)
        if doc is None:
            return None

        compositions = await self._composition_service.build_for_documents([doc])
        composition = compositions.get(doc.id)

        raw_result, raw_details = self._unwrap_classification_payload(doc)

        return self._build_detail(
            doc=doc,
            composition=composition,
            raw_result=raw_result,
            raw_details=raw_details,
        )

    # --------------------------------------------------------------------- #
    # Internal helpers — safe JSON access
    # --------------------------------------------------------------------- #

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        """Безопасно привести значение к dict или вернуть пустой dict."""
        if isinstance(value, dict):
            return value
        return {}

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        """Безопасно привести значение к list или вернуть пустой список."""
        if isinstance(value, list):
            return value
        return []

    def _unwrap_classification_payload(
        self,
        doc: Document,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Достать raw_result и raw_details из Document.classification_details.

        raw_result — это весь envelope, который сохраняет DocumentRepository.update_classification().
        raw_details — это поле "details" внутри envelope (подробный трейс).
        """
        raw_result = self._as_dict(doc.classification_details or {})
        raw_details = self._as_dict(raw_result.get("details") or {})
        return raw_result, raw_details

    # --------------------------------------------------------------------- #
    # Internal helpers — derived explainability fields
    # --------------------------------------------------------------------- #

    def _extract_decided_by(
        self,
        *,
        doc: Document,
        raw_result: dict[str, Any],
        raw_details: dict[str, Any],
    ) -> str | None:
        """
        Определить, какой механизм принял финальное решение по типу документа.

        Приоритет:
        1) details.decision_summary.decided_by
        2) details.voting.strategy
        3) raw_result.level
        4) doc.classification_level
        """
        decision_summary = self._as_dict(raw_details.get("decision_summary"))
        decided_by = decision_summary.get("decided_by")
        if isinstance(decided_by, str) and decided_by.strip():
            return decided_by

        voting = self._as_dict(raw_details.get("voting"))
        strategy = voting.get("strategy")
        if isinstance(strategy, str) and strategy.strip():
            return strategy

        level = raw_result.get("level")
        if isinstance(level, str) and level.strip():
            return level

        return doc.classification_level

    def _extract_confidence_zone(
        self,
        *,
        raw_details: dict[str, Any],
    ) -> str | None:
        """
        Определить зону уверенности (confident / low / unknown), если есть.

        Приоритет:
        1) details.confidence_zone
        2) details.decision_summary.confidence_zone
        """
        zone = raw_details.get("confidence_zone")
        if isinstance(zone, str) and zone.strip():
            return zone

        decision_summary = self._as_dict(raw_details.get("decision_summary"))
        zone2 = decision_summary.get("confidence_zone")
        if isinstance(zone2, str) and zone2.strip():
            return zone2

        return None

    def _extract_contradiction_detected(
        self,
        *,
        raw_details: dict[str, Any],
    ) -> bool:
        """
        Определить, были ли противоречивые сигналы между уровнями (contradiction).

        Источники:
        - details.contradiction_detected (bool)
        - details.contradiction_summary (dict) — если не пустой, считаем True.
        """
        value = raw_details.get("contradiction_detected")
        if isinstance(value, bool):
            return value

        summary = self._as_dict(raw_details.get("contradiction_summary"))
        return bool(summary)

    def _extract_l4_triggered(
        self,
        *,
        raw_details: dict[str, Any],
    ) -> bool:
        """
        Определить, вызывался ли L4 / LLM-fallback.

        Источники:
        - details.L4 (dict) — если не пустой, считаем, что L4 был.
        - details.decision_summary.l4_triggered (bool).
        """
        l4_block = self._as_dict(raw_details.get("L4"))
        if l4_block:
            return True

        decision_summary = self._as_dict(raw_details.get("decision_summary"))
        value = decision_summary.get("l4_triggered")
        if isinstance(value, bool):
            return value

        return False

    def _extract_levels_tried(
        self,
        *,
        raw_details: dict[str, Any],
    ) -> list[str]:
        """
        Определить список уровней, которые реально были задействованы.

        Приоритет:
        1) details.levels_tried, если есть.
        2) Собираем из известных ключей: MASTERCOPY, L1, L2, L3, L4.
        """
        levels_raw = raw_details.get("levels_tried")
        if isinstance(levels_raw, list):
            return [str(level) for level in levels_raw if isinstance(level, str)]

        levels: list[str] = []
        for key in ("MASTERCOPY", "L1", "L2", "L3", "L4"):
            if key in raw_details and isinstance(raw_details.get(key), dict):
                levels.append(key)
        return levels

    def _extract_candidates(
        self,
        *,
        raw_result: dict[str, Any],
        raw_details: dict[str, Any],
    ) -> list[ClassificationCandidateResponse]:
        """
        Достать кандидатов типов документа из JSON.

        Источники:
        - classification_details["candidates"]
        - classification_details["details"]["candidates"]
        """
        raw_candidates = raw_result.get("candidates")
        if not isinstance(raw_candidates, list):
            raw_candidates = raw_details.get("candidates")

        items = self._as_list(raw_candidates)
        result: list[ClassificationCandidateResponse] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            doctype = item.get("type_code") or item.get("doctype") or item.get("type") or "UNKNOWN"
            confidence = float(item.get("confidence") or 0.0)
            level = str(item.get("level") or "")
            method = item.get("method")
            evidence = item.get("evidence")
            language = item.get("language")
            jurisdiction = item.get("jurisdiction")

            extra: dict[str, Any] = {}
            for k, v in item.items():
                if k in {
                    "type_code",
                    "doctype",
                    "type",
                    "confidence",
                    "level",
                    "method",
                    "evidence",
                    "language",
                    "jurisdiction",
                }:
                    continue
                extra[k] = v

            result.append(
                ClassificationCandidateResponse(
                    doctype=str(doctype),
                    confidence=confidence,
                    level=level,
                    method=str(method) if method is not None else None,
                    evidence=str(evidence) if evidence is not None else None,
                    language=str(language) if language is not None else None,
                    jurisdiction=str(jurisdiction) if jurisdiction is not None else None,
                    extra=extra or None,
                )
            )

        return result

    def _extract_level_results(
        self,
        *,
        raw_details: dict[str, Any],
    ) -> list[ClassificationLevelResultResponse]:
        """
        Собрать нормализованный результат по известным уровням.

        Мы смотрим на блоки:
        - MASTERCOPY
        - L1
        - L2
        - L3
        - L4
        и, если там есть dict, строим по нему ClassificationLevelResultResponse.
        """
        results: list[ClassificationLevelResultResponse] = []

        for level_key in ("MASTERCOPY", "L1", "L2", "L3", "L4"):
            block = raw_details.get(level_key)
            block_dict = self._as_dict(block)
            if not block_dict:
                continue

            level_type = (
                block_dict.get("type_code") or block_dict.get("doctype") or block_dict.get("type")
            )
            confidence = block_dict.get("confidence")
            method = block_dict.get("method")
            evidence = block_dict.get("evidence")

            extra: dict[str, Any] = {}
            for k, v in block_dict.items():
                if k in {
                    "type_code",
                    "doctype",
                    "type",
                    "confidence",
                    "method",
                    "evidence",
                }:
                    continue
                extra[k] = v

            results.append(
                ClassificationLevelResultResponse(
                    level=level_key,
                    type=str(level_type) if level_type is not None else None,
                    confidence=float(confidence) if confidence is not None else None,
                    method=str(method) if method is not None else None,
                    evidence=str(evidence) if evidence is not None else None,
                    extra=extra or None,
                )
            )

        return results

    def _extract_voting(
        self,
        *,
        raw_details: dict[str, Any],
    ) -> ClassificationVotingResponse | None:
        """
        Собрать информацию о голосовании и возможном override.

        Источники:
        - details.voting
        - details.voting_override
        """
        voting_raw = self._as_dict(raw_details.get("voting"))
        override_raw = self._as_dict(raw_details.get("voting_override"))

        if not voting_raw and not override_raw:
            return None

        strategy = voting_raw.get("strategy")
        reason = voting_raw.get("reason")
        v_type = voting_raw.get("type")
        confidence = voting_raw.get("confidence")
        margin = voting_raw.get("margin")
        ranking = self._as_list(voting_raw.get("ranking"))

        return ClassificationVotingResponse(
            strategy=strategy if isinstance(strategy, str) else None,
            reason=str(reason) if isinstance(reason, str) else None,
            type=str(v_type) if isinstance(v_type, str) else None,
            confidence=float(confidence) if confidence is not None else None,
            margin=float(margin) if margin is not None else None,
            ranking=[dict(item) for item in ranking if isinstance(item, dict)],
            override=override_raw or None,
        )

    def _build_segment_summary(
        self,
        *,
        composition: DocumentCompositionSummary | None,
        raw_details: dict[str, Any],
    ) -> ClassificationSegmentSummaryResponse | None:
        """
        Построить лёгкий summary по сегментам (если файл сегментирован).

        Для v1:
        - не ходим в DocumentSegment ещё раз;
        - используем только composition summary;
        - has_segment_classification считаем True, если сегментов больше 1.
        """
        if composition is None:
            return None

        segment_count = composition.segment_count or 0
        has_segment_classification = segment_count > 1

        return ClassificationSegmentSummaryResponse(
            segment_count=segment_count,
            primary_segment_id=str(composition.primary_segment_id)
            if composition.primary_segment_id is not None
            else None,
            primary_segment_label=composition.primary_segment_label,
            has_segment_classification=has_segment_classification,
        )

    # --------------------------------------------------------------------- #
    # Internal helpers — row/detail assembly
    # --------------------------------------------------------------------- #

    def _build_row(
        self,
        *,
        doc: Document,
        composition: DocumentCompositionSummary | None,
        raw_result: dict[str, Any],
        raw_details: dict[str, Any],
    ) -> ClassificationInvestigationRow:
        """Собрать одну строку deal-level investigation списка."""
        decided_by = self._extract_decided_by(
            doc=doc,
            raw_result=raw_result,
            raw_details=raw_details,
        )
        confidence_zone = self._extract_confidence_zone(raw_details=raw_details)
        contradiction_detected = self._extract_contradiction_detected(
            raw_details=raw_details,
        )
        l4_triggered = self._extract_l4_triggered(raw_details=raw_details)
        segment_summary = self._build_segment_summary(
            composition=composition,
            raw_details=raw_details,
        )

        return ClassificationInvestigationRow(
            document_id=doc.id,
            filename=doc.filename,
            folder_path=doc.folder_path,
            status=doc.status,
            doc_type=doc.doc_type,
            classification_level=doc.classification_level,
            classification_confidence=doc.classification_confidence,
            applicable_triggers=list(doc.applicable_triggers or []),
            classification_requires_review=bool(doc.classification_requires_review),
            decided_by=decided_by,
            confidence_zone=confidence_zone,
            contradiction_detected=contradiction_detected,
            l4_triggered=l4_triggered,
            composition=composition,
            segment_summary=segment_summary,
            updated_at=doc.updated_at,
        )

    def _build_detail(
        self,
        *,
        doc: Document,
        composition: DocumentCompositionSummary | None,
        raw_result: dict[str, Any],
        raw_details: dict[str, Any],
    ) -> ClassificationInvestigationDetailResponse:
        """Собрать подробный explainability detail по одному документу."""
        decided_by = self._extract_decided_by(
            doc=doc,
            raw_result=raw_result,
            raw_details=raw_details,
        )
        confidence_zone = self._extract_confidence_zone(raw_details=raw_details)
        contradiction_detected = self._extract_contradiction_detected(
            raw_details=raw_details,
        )
        l4_triggered = self._extract_l4_triggered(raw_details=raw_details)
        levels_tried = self._extract_levels_tried(raw_details=raw_details)
        candidates = self._extract_candidates(
            raw_result=raw_result,
            raw_details=raw_details,
        )
        level_results = self._extract_level_results(raw_details=raw_details)
        voting = self._extract_voting(raw_details=raw_details)
        segment_summary = self._build_segment_summary(
            composition=composition,
            raw_details=raw_details,
        )

        decision_summary = self._as_dict(raw_details.get("decision_summary"))

        return ClassificationInvestigationDetailResponse(
            document_id=doc.id,
            filename=doc.filename,
            folder_path=doc.folder_path,
            status=doc.status,
            doc_type=doc.doc_type,
            classification_level=doc.classification_level,
            classification_confidence=doc.classification_confidence,
            applicable_triggers=list(doc.applicable_triggers or []),
            classification_requires_review=bool(doc.classification_requires_review),
            language=doc.language,
            jurisdiction_guess=doc.jurisdiction_guess,
            decided_by=decided_by,
            confidence_zone=confidence_zone,
            contradiction_detected=contradiction_detected,
            l4_triggered=l4_triggered,
            levels_tried=levels_tried,
            candidates=candidates,
            level_results=level_results,
            voting=voting,
            decision_summary=decision_summary,
            composition=composition,
            segment_summary=segment_summary,
            raw_result=raw_result,
            raw_details=raw_details,
        )

    # --------------------------------------------------------------------- #
    # Internal helpers — summary for deal
    # --------------------------------------------------------------------- #

    def _build_summary(
        self,
        documents: Iterable[Document],
    ) -> ClassificationInvestigationSummary:
        """
        Посчитать summary counters по всей сделке.

        Для непрофессионального программиста:

        - total_documents           — сколько всего документов в сделке;
        - classified_count          — у скольких есть doc_type;
        - manual_review_count       — у скольких classification_requires_review=True;
        - unknown_count             — у скольких doc_type == 'UNKNOWN';
        - l4_count                  — у скольких был вызван L4 / LLM-fallback;
        - contradiction_count       — у скольких были противоречивые сигналы.
        """
        docs_list = list(documents)
        total_documents = len(docs_list)
        classified_count = 0
        manual_review_count = 0
        unknown_count = 0
        l4_count = 0
        contradiction_count = 0

        for doc in docs_list:
            if doc.doc_type:
                classified_count += 1
            if doc.classification_requires_review:
                manual_review_count += 1
            if doc.doc_type == "UNKNOWN":
                unknown_count += 1

            raw_result, raw_details = self._unwrap_classification_payload(doc)
            if self._extract_l4_triggered(raw_details=raw_details):
                l4_count += 1
            if self._extract_contradiction_detected(raw_details=raw_details):
                contradiction_count += 1

        return ClassificationInvestigationSummary(
            total_documents=total_documents,
            classified_count=classified_count,
            manual_review_count=manual_review_count,
            unknown_count=unknown_count,
            l4_count=l4_count,
            contradiction_count=contradiction_count,
        )
