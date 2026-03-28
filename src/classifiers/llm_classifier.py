# src/classifiers/llm_classifier.py

"""
L4: классификация документов через LLM (обёртка и фабрика).

Назначение:
- Предоставить единый интерфейс для L4‑классификаторов на базе LLM
  (локальная GGUF‑модель, OpenAI, Anthropic и т.п.).
- Дать фабрику create_llm_classifier, которая по настройкам выбирает,
  какой провайдер LLM использовать или отключить L4 полностью.

Варианты провайдера (settings.LLM_PROVIDER):
- "none"      — L4 отключён, каскад работает только на L1–L3.
- "local"     — локальная GGUF‑модель через llama‑cpp‑python
                (без риска утечки ПДн, модель работает на своём сервере).
- "openai"    — облачный OpenAI API (обязательно использовать очищенный текст).
- "anthropic" — облачный Anthropic API (обязательно использовать очищенный текст).

Текущий статус:
- В Stage 8 основным L4 является логика внутри HybridClassifier.
- Этот модуль полезен как отдельный «чистый» LLM‑классификатор
  или как заготовка для будущего расширения.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from .base import BaseLLMClassifier, ClassificationResult
from .registry_loader import get_doc_type_config, load_registry
from core.config import settings
from core.constants import ClassificationLevel
from core.logging import get_logger

logger = get_logger(__name__)


# ── Шаблон системного промпта для LLM‑классификации ──────────────────────────
# ВАЖНО: текст промпта хранится в отдельном файле
# /prompts/classification/classify_document.txt.
# Здесь оставляем только контракт по JSON: ожидаем поля
#  - type_code: строка с кодом типа или "UNKNOWN" / null
#  - confidence: число 0–1
#  - reasoning: строка с кратким обоснованием.

_CLASSIFY_PROMPT = (
    "Ты — классификатор юридических документов.\n"
    "Твоя задача — отнести документ РОВНО к одному типу из разрешённого списка.\n\n"
    "Разрешённые типы документов (type_code: человекочитаемое название):\n"
    "{types_list}\n\n"
    "Предыдущие уровни классификации (L1–L3) предложили такие кандидаты (может быть пусто):\n"
    "{candidates}\n\n"
    "Инструкция:\n"
    "1) Внимательно прочитай имя файла, путь к папке (если есть) и начало текста документа.\n"
    "2) Выбери РОВНО ОДИН type_code из списка выше, который лучше всего описывает документ.\n"
    "3) Если ни один тип явно не подходит, верни значение null или строку \"UNKNOWN\" в поле type_code.\n"
    "4) Ответь СТРОГО одним JSON-объектом следующего вида:\n"
    "{"
    "\"type_code\": \"<один type_code из списка, либо \"UNKNOWN\" или null>\", "
    "\"confidence\": <число от 0 до 1>, "
    "\"reasoning\": \"краткое объяснение в 1–2 предложениях\""
    "}\n\n"
    "Не добавляй никакого текста до или после JSON. "
    "Не объясняй рассуждения вне поля reasoning внутри JSON.\n"
)


def _build_types_list(registry_path: str) -> str:
    """Собрать список известных типов для подстановки в промпт LLM."""
    registry = load_registry(registry_path)
    lines: list[str] = []
    for cfg in registry.get("document_types", []):
        doc_type = cfg.get("type", "")
        name = cfg.get("name", "")
        if doc_type:
            lines.append(f"  - {doc_type}: {name}")
    return "\n".join(lines)


def _parse_llm_json(
    raw_text: str,
    registry: Dict[str, Any],
) -> tuple[str, float, str]:
    """
    Аккуратно разобрать JSON из ответа LLM и привести к безопасным значениям.

    Возвращает кортеж (best_type, confidence, reasoning):
    - best_type:
        * если type_code валидный и есть в реестре → он;
        * если type_code пустой/None/"UNKNOWN"/левый → "UNKNOWN".
    - confidence:
        * число 0–1, любые NaN/отрицательные/больше 1 обрезаются в [0, 1].
    - reasoning:
        * строка (даже если в JSON было что-то иное).
    """
    # 1. Вырезаем JSON-объект из текста (на случай, если модель добавила мусор).
    start_idx = raw_text.find("{")
    end_idx = raw_text.rfind("}") + 1
    if start_idx == -1 or end_idx <= start_idx:
        raise ValueError("No JSON object found in LLM response")

    obj = json.loads(raw_text[start_idx:end_idx])

    # 2. Нормализуем type_code.
    raw_type = obj.get("type_code")
    # На всякий случай поддерживаем старое имя поля "doctype"
    if raw_type is None:
        raw_type = obj.get("doctype")

    if isinstance(raw_type, str):
        raw_type = raw_type.strip()
    else:
        # Если это не строка (None, число и т.п.) — считаем, что типа нет.
        raw_type = ""

    # Всё, что похоже на "UNKNOWN" (в любом регистре), трактуем как отсутствие типа.
    if raw_type.upper() == "UNKNOWN":
        raw_type = ""

    # Проверяем, что тип есть в YAML‑реестре.
    allowed_types = {cfg.get("type", "") for cfg in registry.get("document_types", [])}
    best_type = raw_type if raw_type in allowed_types else "UNKNOWN"

    # 3. Нормализуем confidence.
    raw_conf = obj.get("confidence", 0.0)
    try:
        conf = float(raw_conf)
    except (TypeError, ValueError):
        conf = 0.0
    if conf < 0.0:
        conf = 0.0
    if conf > 1.0:
        conf = 1.0

    # 4. Нормализуем reasoning.
    reasoning = obj.get("reasoning", "")
    if not isinstance(reasoning, str):
        reasoning = str(reasoning)

    return best_type, conf, reasoning


class LocalLLMClassifier(BaseLLMClassifier):
    """
    L4‑классификатор на базе локальной GGUF‑модели (llama‑cpp‑python).

    Особенности:
    - Модель загружается из файла LLM_LOCAL_MODEL_PATH.
    - Работает локально, поэтому безопасна для сырого текста (без анонимизации).
    - Использует общий промпт _CLASSIFY_PROMPT и список типов из YAML‑реестра.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
        registry_path: str = "playbooks/document_types",
    ):
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self.registry_path = registry_path
        self._llm = None

    @property
    def llm(self):
        """
        Ленивая загрузка GGUF‑модели.

        Если модель уже загружена, возвращается существующий объект.
        Если загрузка не удалась, в лог пишется ошибка, а свойство остаётся None.
        """
        if self._llm is None:
            try:
                from llama_cpp import Llama

                self._llm = Llama(
                    model_path=self.model_path,
                    n_ctx=self.n_ctx,
                    n_gpu_layers=self.n_gpu_layers,
                    verbose=False,
                )
                logger.info(
                    "Local GGUF model loaded",
                    path=self.model_path,
                    n_ctx=self.n_ctx,
                )
            except Exception as e:
                logger.error(
                    "Failed to load GGUF model",
                    path=self.model_path,
                    error=str(e),
                )
        return self._llm

    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        """
        Классификация документа через локальную GGUF‑модель.

        Параметры:
        - text          : полный текст документа (можно сырой, без маскировки).
        - filename      : имя файла (используется только в промптах, при необходимости).
        - folder_path   : путь к папке (резерв на будущее).
        - text_sanitized: зарезервировано для облачных провайдеров (здесь не используется).
        - metadata      : дополнительная информация (например, кандидаты предыдущих уровней).

        Возвращает ClassificationResult с полями:
        - doctype       : выбранный type_code или "UNKNOWN".
        - confidence    : уверенность LLM в диапазоне 0–1.
        - level         : ClassificationLevel.L4_LLM.
        - method        : строка "local_gguf" или описание ошибки.
        - evidence      : краткое текстовое объяснение из поля reasoning.
        - language/jurisdiction: берутся из YAML‑конфига типа, если есть.
        """
        if self.llm is None:
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=ClassificationLevel.L4_LLM,
                method="local_llm_unavailable",
            )

        registry = load_registry(self.registry_path)
        candidates = (metadata or {}).get("candidates", [])
        candidates_str = json.dumps(candidates, ensure_ascii=False)
        types_list = _build_types_list(self.registry_path)

        prompt = _CLASSIFY_PROMPT.format(
            types_list=types_list,
            candidates=candidates_str,
        )

        # GGUF‑модель можно кормить сырым текстом (безопасно с точки зрения ПДн).
        doc_text = (text or "")[:2000]
        full_prompt = f"{prompt}\n\nDocument text:\n{doc_text}"

        try:
            response = self.llm(
                full_prompt,
                max_tokens=200,
                temperature=0.1,
                stop=["\n\n"],
            )
            response_text = response["choices"][0]["text"].strip()

            best_type, confidence, reasoning = _parse_llm_json(
                raw_text=response_text,
                registry=registry,
            )

            # Извлекаем метаданные для найденного типа из реестра.
            cfg = get_doc_type_config(registry, best_type) or {}
            doc_meta = cfg.get("metadata", {}) or {}

            return ClassificationResult(
                doctype=best_type,
                confidence=confidence,
                level=ClassificationLevel.L4_LLM,
                method="local_gguf",
                evidence=reasoning,
                language=doc_meta.get("language", "ru"),
                jurisdiction=doc_meta.get("jurisdiction", "RU"),
            )
        except (json.JSONDecodeError, ValueError) as e:
            # Типичная ситуация: LLM вернул текст без валидного JSON.
            logger.warning(
                "Local LLM classification failed: JSON parse error",
                error=str(e),
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=ClassificationLevel.L4_LLM,
                method="local_llm_error",
                evidence=str(e),
            )
        except Exception as e:
            # Любая другая ошибка — тоже не должна ронять пайплайн.
            logger.warning(
                "Local LLM classification failed: unexpected error",
                error=str(e),
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=ClassificationLevel.L4_LLM,
                method="local_llm_error",
                evidence=str(e),
            )


# Классы OpenAIClassifier и AnthropicClassifier остаются заглушками для Stage 8.
# В будущем сюда можно перенести реальную интеграцию с облачными провайдерами.
class OpenAIClassifier(BaseLLMClassifier):
    async def classify(
        self, text: str, filename: str, folder_path: str, **kwargs
    ) -> ClassificationResult:
        logger.info("OpenAI L4 called (stub)", model=self.model)
        return ClassificationResult(
            doctype="UNKNOWN",
            confidence=0.0,
            level=ClassificationLevel.L4_LLM,
            method="openai_stub",
        )


class AnthropicClassifier(BaseLLMClassifier):
    async def classify(
        self, text: str, filename: str, folder_path: str, **kwargs
    ) -> ClassificationResult:
        logger.info("Anthropic L4 called (stub)", model=self.model)
        return ClassificationResult(
            doctype="UNKNOWN",
            confidence=0.0,
            level=ClassificationLevel.L4_LLM,
            method="anthropic_stub",
        )


def create_llm_classifier(
    provider: str | None = None,
    pii_mode: str | None = None,
    registry_path: str | None = None,
) -> BaseLLMClassifier | None:
    """
    Создать L4 LLM‑классификатор в зависимости от настроек.

    Параметры:
    - provider      : строка с кодом провайдера ("none", "local", "openai", "anthropic").
                      Если не задан, берётся из settings.LLM_PROVIDER.
    - pii_mode      : режим работы с персональными данными
                      (зарезервирован, текущая реализация не использует).
    - registry_path : путь к YAML‑реестру типов документов.
                      Если не задан, берётся из settings.CLASSIFIER_REGISTRY_PATH.

    Поведение:
    - "none"       → возвращает None, L4 отключён.
    - "local"      → создаёт LocalLLMClassifier для локальной GGUF‑модели.
    - "openai"     → возвращает заглушку OpenAIClassifier.
    - "anthropic"  → возвращает заглушку AnthropicClassifier.
    - Если модель/ключи не найдены, логирует предупреждение и возвращает None.
    """
    provider = provider or settings.LLM_PROVIDER
    reg_path = registry_path or settings.CLASSIFIER_REGISTRY_PATH

    if provider == "none":
        return None

    if provider == "local":
        model_path = settings.LLM_LOCAL_MODEL_PATH
        if not os.path.exists(model_path):
            logger.warning("Local GGUF model not found, L4 disabled", path=model_path)
            return None
        return LocalLLMClassifier(
            model_path=model_path,
            n_ctx=settings.LLM_LOCAL_N_CTX,
            n_gpu_layers=settings.LLM_LOCAL_N_GPU_LAYERS,
            registry_path=reg_path,
        )

    if provider == "openai":
        if not settings.LLM_CLOUD_API_KEY:
            logger.warning("OpenAI API key not configured, L4 disabled")
            return None
        return OpenAIClassifier(
            model=settings.LLM_CLOUD_MODEL,
            api_key=settings.LLM_CLOUD_API_KEY,
            registry_path=reg_path,
        )

    if provider == "anthropic":
        if not settings.LLM_CLOUD_API_KEY:
            logger.warning("Anthropic API key not configured, L4 disabled")
            return None
        return AnthropicClassifier(
            model=settings.LLM_CLOUD_MODEL,
            api_key=settings.LLM_CLOUD_API_KEY,
            registry_path=reg_path,
        )

    return None