# src/services/structure/heading_llm_refiner.py

"""
LLM-рефайнер для спорных кандидатов заголовков структуры документа.

Зачем нужен этот модуль:
- deterministic-эвристики и scoring хорошо отрабатывают очевидные случаи,
  но часть строк остаётся пограничной: они похожи на заголовки, но могут быть
  элементами оглавления, списков, фрагментами основного текста или шумом OCR/layout;
- для таких ambiguous-кандидатов можно подключать локальную LLM как
  узкий слой доуточнения, а не как основной механизм построения структуры.

Как используется в пайплайне:
1. heading_patterns.py пытается распарсить строку как возможный заголовок;
2. heading_scoring.py относит кандидата к accepted / rejected / ambiguous;
3. только ambiguous-кандидаты передаются в этот модуль;
4. локальная LLM получает:
   - исходную строку,
   - распарсенные uid/title,
   - страницу,
   - соседний контекст,
   - причину, по которой deterministic scoring не смог принять решение;
5. LLM возвращает строго JSON-ответ:
   - accept/reject,
   - нормализованный uid,
   - нормализованный title,
   - confidence,
   - краткую причину;
6. pipeline.py использует этот ответ как refinement-слой перед финальной
   фильтрацией и сборкой иерархии.

Принципы безопасности:
- LLM не должна строить всё дерево документа;
- LLM не должна получать весь документ целиком без необходимости;
- LLM используется только для спорных локальных случаев;
- если LLM не ответила, вернула плохой JSON или слабую уверенность,
  пайплайн обязан безопасно откатиться к deterministic-логике;
- ошибка LLM никогда не должна ломать общий build структуры.

Важно:
- этот модуль описывает контракт и точку интеграции;
- реальный вызов локальной модели инкапсулирован в _call_local_llm();
- модель должна возвращать только JSON без пояснительного текста.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import requests

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

LLMDecision = Literal["accept", "reject"]


@dataclass(slots=True)
class ScoredHeadingCandidate:
    """
    Минимальная модель кандидата, пригодная для LLM-refinement.

    Предполагается, что такой объект приходит из scoring-слоя:
    - raw_text: исходный текст layout-элемента;
    - uid/title: результат deterministic parse;
    - decision: accepted / rejected / ambiguous;
    - reason: причина текущего решения rules-слоя;
    - score: численная уверенность deterministic-слоя;
    - scope: логический контекст (main_contract / appendix_* / act_* и т.п.).
    """

    elem_i: int
    page: int
    raw_text: str
    uid: str
    title: str
    decision: Literal["accepted", "rejected", "ambiguous"]
    reason: str
    score: float = 0.0
    decision_source: str = "rules"
    metadata: dict[str, Any] | None = None
    scope: str | None = None


@dataclass(slots=True)
class LLMHeadingRefinement:
    decision: LLMDecision
    normalized_uid: str
    normalized_title: str
    confidence: float
    reason: str


def _build_prompt(
    *,
    raw_text: str,
    parsed_uid: str,
    parsed_title: str,
    page: int,
    prev_heading: str | None,
    next_heading: str | None,
    deterministic_reason: str,
    scope: str | None,
) -> str:
    scope_info = f"scope: {scope!r}" if scope is not None else "scope: null"
    return f"""
Ты проверяешь, является ли строка документа настоящим заголовком раздела, пункта или подпункта.

Нужно вернуть ТОЛЬКО JSON-объект без markdown, без пояснений и без дополнительного текста.

Формат ответа:
{{
  "decision": "accept" | "reject",
  "normalized_uid": "строка",
  "normalized_title": "строка",
  "confidence": число от 0 до 1,
  "reason": "короткая причина"
}}

Правила:
- accept ставь только если строка с высокой вероятностью является настоящим заголовком документа;
- reject ставь, если строка больше похожа на основной текст, строку оглавления, элемент списка, мусор OCR/layout или некорректную нумерацию;
- если decision = "reject", то normalized_uid и normalized_title должны быть пустыми строками;
- если нумерация валидна, сохрани её;
- если в строке нет надёжной нумерации, не придумывай её;
- title нормализуй аккуратно: убери явный шум, лишние пробелы и висячую пунктуацию;
- не выдумывай новые слова, которых нет в строке;
- будь консервативен: если есть сомнение, лучше reject;
- confidence должен отражать уверенность именно в решении accept/reject.

Контекст:
- это этап доуточнения после deterministic-эвристик;
- deterministic-слой не смог уверенно принять решение;
- твоя задача — помочь только в пограничном случае.

Входные данные:
raw_text: {raw_text!r}
parsed_uid: {parsed_uid!r}
parsed_title: {parsed_title!r}
page: {page}
previous_accepted_heading: {prev_heading!r}
next_accepted_heading: {next_heading!r}
deterministic_reason: {deterministic_reason!r}
{scope_info}
""".strip()


def _resolve_llm_endpoint_and_model() -> tuple[str | None, str | None]:
    provider = (settings.STRUCTURE_LLM_PROVIDER or "").strip()

    if provider not in ("local", "local_endpoint", "ollama"):
        logger.warning(
            "STRUCTURE llm_refiner_provider_not_supported",
            extra={"provider": provider},
        )
        return None, None

    endpoint = (settings.LOCAL_LLM_ENDPOINT or "").rstrip("/")
    if not endpoint:
        logger.warning("STRUCTURE llm_refiner_no_endpoint_configured")
        return None, None

    model = (settings.STRUCTURE_LLM_MODEL or "").strip()
    if not model:
        logger.warning("STRUCTURE llm_refiner_no_model_configured")
        return None, None

    return endpoint, model


def _call_local_llm(prompt: str) -> str:
    """
    Вызов локальной LLM через Ollama-compatible HTTP endpoint.

    Текущая реализация ожидает endpoint вида:
    POST {LOCAL_LLM_ENDPOINT}/api/generate

    Возвращает строку с JSON-ответом модели.
    """

    provider = (
        str(getattr(settings, "STRUCTURE_LLM_PROVIDER", "") or "").strip() or "local_endpoint"
    )
    if provider != "local_endpoint":
        raise RuntimeError(f"Unsupported STRUCTURE_LLM_PROVIDER: {provider}")

    endpoint, model = _resolve_llm_endpoint_and_model()
    if not endpoint or not model:
        raise RuntimeError("LLM endpoint or model not configured")

    timeout = int(
        getattr(settings, "STRUCTURE_LLM_TIMEOUT_SECONDS", 0)
        or getattr(settings, "LLM_TIMEOUT_SECONDS", 30)
        or 30
    )

    model = str(getattr(settings, "STRUCTURE_LLM_MODEL", "") or "").strip()
    if not model:
        raise RuntimeError("STRUCTURE_LLM_MODEL is not configured")

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
        },
    }

    url = f"{endpoint}/api/generate"

    logger.debug(
        "STRUCTURE llm_refiner_request_start",
        extra={
            "provider": provider,
            "url": url,
            "model": model,
            "timeout": timeout,
        },
    )

    response = requests.post(
        url,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):
        text = data.get("response")
        if isinstance(text, str) and text.strip():
            return text.strip()

    raise RuntimeError("Local LLM returned empty or invalid response payload")


def _parse_llm_response(raw: str) -> LLMHeadingRefinement | None:
    try:
        data = json.loads(raw)
        decision = data.get("decision")
        if decision not in {"accept", "reject"}:
            return None

        normalized_uid = str(data.get("normalized_uid") or "").strip()
        normalized_title = str(data.get("normalized_title") or "").strip()
        confidence = float(data.get("confidence") or 0.0)
        reason = str(data.get("reason") or "").strip()[:300]

        if decision == "reject":
            normalized_uid = ""
            normalized_title = ""

        return LLMHeadingRefinement(
            decision=decision,
            normalized_uid=normalized_uid,
            normalized_title=normalized_title,
            confidence=max(0.0, min(1.0, confidence)),
            reason=reason or "llm_refinement",
        )
    except Exception:
        return None


def refine_ambiguous_candidates(
    *,
    scored_candidates: list[ScoredHeadingCandidate],
    elements: list[dict[str, Any]],
    document_id: str,
    min_confidence: float = 0.75,
    max_candidates: int = 12,
) -> list[ScoredHeadingCandidate]:
    """
    Прогнать ambiguous-кандидатов через локальную LLM и вернуть обновлённый список.

    Правила:
    - обрабатываем только candidates с decision == "ambiguous";
    - accepted/rejected кандидаты возвращаются как есть;
    - если LLM не ответила, вернула невалидный JSON или низкую уверенность,
      кандидат остаётся ambiguous без изменений;
    - если LLM приняла решение accept/reject с достаточной уверенностью,
      обновляем candidate;
    - scope кандидата сохраняется без изменений.
    """
    if not scored_candidates:
        return []

    refined: list[ScoredHeadingCandidate] = []
    llm_processed = 0

    for idx, candidate in enumerate(scored_candidates):
        if candidate.decision != "ambiguous":
            refined.append(candidate)
            continue

        if llm_processed >= max_candidates:
            refined.append(candidate)
            continue

        prev_heading = None
        next_heading = None

        for prev in reversed(scored_candidates[:idx]):
            if prev.decision == "accepted":
                prev_heading = f"{prev.uid} {prev.title}".strip()
                break

        for nxt in scored_candidates[idx + 1 :]:
            if nxt.decision == "accepted":
                next_heading = f"{nxt.uid} {nxt.title}".strip()
                break

        prompt = _build_prompt(
            raw_text=candidate.raw_text,
            parsed_uid=candidate.uid,
            parsed_title=candidate.title,
            page=candidate.page,
            prev_heading=prev_heading,
            next_heading=next_heading,
            deterministic_reason=candidate.reason,
            scope=candidate.scope,
        )

        try:
            raw_response = _call_local_llm(prompt)
            parsed = _parse_llm_response(raw_response)

            if not parsed:
                logger.warning(
                    "STRUCTURE llm_refiner_invalid_response",
                    extra={
                        "document_id": document_id,
                        "element_index": candidate.elem_i,
                        "page": candidate.page,
                        "uid": candidate.uid,
                        "scope": candidate.scope,
                    },
                )
                refined.append(candidate)
                llm_processed += 1
                continue

            if parsed.confidence < min_confidence:
                logger.info(
                    "STRUCTURE llm_refiner_low_confidence",
                    extra={
                        "document_id": document_id,
                        "element_index": candidate.elem_i,
                        "page": candidate.page,
                        "uid": candidate.uid,
                        "scope": candidate.scope,
                        "confidence": parsed.confidence,
                    },
                )
                refined.append(candidate)
                llm_processed += 1
                continue

            if parsed.decision == "accept":
                refined.append(
                    ScoredHeadingCandidate(
                        elem_i=candidate.elem_i,
                        page=candidate.page,
                        raw_text=candidate.raw_text,
                        uid=parsed.normalized_uid or candidate.uid,
                        title=parsed.normalized_title or candidate.title,
                        decision="accepted",
                        reason=parsed.reason,
                        score=parsed.confidence,
                        decision_source="llm",
                        metadata={
                            "previous_decision": candidate.decision,
                            "previous_reason": candidate.reason,
                            "llm_confidence": parsed.confidence,
                        },
                        scope=candidate.scope,
                    )
                )
            else:
                refined.append(
                    ScoredHeadingCandidate(
                        elem_i=candidate.elem_i,
                        page=candidate.page,
                        raw_text=candidate.raw_text,
                        uid="",
                        title="",
                        decision="rejected",
                        reason=parsed.reason,
                        score=parsed.confidence,
                        decision_source="llm",
                        metadata={
                            "previous_decision": candidate.decision,
                            "previous_reason": candidate.reason,
                            "llm_confidence": parsed.confidence,
                        },
                        scope=candidate.scope,
                    )
                )

            llm_processed += 1

        except Exception as e:
            logger.warning(
                "STRUCTURE llm_refiner_call_failed",
                extra={
                    "document_id": document_id,
                    "element_index": candidate.elem_i,
                    "page": candidate.page,
                    "uid": candidate.uid,
                    "scope": candidate.scope,
                    "error": str(e),
                },
            )
            refined.append(candidate)
            llm_processed += 1

    return refined
