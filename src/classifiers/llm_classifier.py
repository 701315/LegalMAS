"""
L4 LLM Classifier — provider-agnostic interface and factory.

Provider selection:
  - "none": L4 is skipped (default for MVP)
  - "local": Local GGUF model via llama-cpp-python (no PII leak risk,
             file at LLM_LOCAL_MODEL_PATH)
  - "openai": OpenAI API (MUST use sanitized text)
  - "anthropic": Anthropic API (MUST use sanitized text)
"""

import json
import os

from classifiers.base import BaseLLMClassifier, ClassificationResult
from classifiers.registry_loader import get_doc_type_config, load_registry
from core.config import settings
from core.constants import ClassificationLevel
from core.logging import get_logger

logger = get_logger(__name__)

# ── System prompt template ───────────────────────────────────────────────────

_CLASSIFY_PROMPT = """You are a legal document classifier.
Given a document text, classify it into one of these types:
{types_list}

Previous classification attempts suggested these candidates:
{candidates}

Respond ONLY with a JSON object:
{{"doctype": "type_id", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""


def _build_types_list(registry_path: str) -> str:
    """Build a formatted list of known types for the LLM prompt."""
    registry = load_registry(registry_path)
    lines = []
    for cfg in registry.get("document_types", []):
        doc_type = cfg.get("type", "")
        name = cfg.get("name", "")
        if doc_type:
            lines.append(f"  - {doc_type}: {name}")
    return "\n".join(lines)


class LocalLLMClassifier(BaseLLMClassifier):
    """
    L4 via local GGUF model using llama-cpp-python.
    Safe for raw text — model runs locally, no PII leak.
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
        """Lazy-load the GGUF model."""
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

        # GGUF может принимать сырой текст (безопасно)
        doc_text = text[:2000]
        full_prompt = f"{prompt}\n\nDocument text:\n{doc_text}"

        try:
            response = self.llm(
                full_prompt,
                max_tokens=200,
                temperature=0.1,
                stop=["\n\n"],
            )
            response_text = response["choices"][0]["text"].strip()
            # Пытаемся найти JSON в ответе (иногда LLM пишет лишний текст)
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1
            if start_idx != -1 and end_idx != 0:
                result = json.loads(response_text[start_idx:end_idx])
            else:
                raise ValueError("No JSON found in LLM response")

            best_type = result.get("doctype", "UNKNOWN")

            # Извлекаем метаданные для найденного типа из реестра
            cfg = get_doc_type_config(registry, best_type) or {}
            doc_meta = cfg.get("metadata", {}) or {}

            return ClassificationResult(
                doctype=best_type,
                confidence=float(result.get("confidence", 0.0)),
                level=ClassificationLevel.L4_LLM,
                method="local_gguf",
                evidence=result.get("reasoning", ""),
                language=doc_meta.get("language", "ru"),
                jurisdiction=doc_meta.get("jurisdiction", "RU"),
            )
        except (json.JSONDecodeError, ValueError, Exception) as e:
            logger.warning("Local LLM classification failed", error=str(e))
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=ClassificationLevel.L4_LLM,
                method="local_llm_error",
                evidence=str(e),
            )


# Классы OpenAIClassifier и AnthropicClassifier остаются без изменений (заглушки для Stage 8)
# Но в методе classify они также должны возвращать поля language/jurisdiction (по дефолту "ru"/"RU")


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
