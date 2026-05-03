"""
L4-fallback: вызов LLM для классификации документа и парсинг ответа.

Production-ready версия:
- prompt template loading from prompts/classification/classify_document.txt
- structured rendering of allowed_types using YAML metadata
- strict JSON parsing and validation
- safe truncation of document fragment before LLM call
- raw diagnostics for HybridClassifier / postmortem analysis
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..yaml_registry import YAMLRegistry, DocumentTypeConfig
from engine.llm.client import LLMClient, LLMResponse
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


def _clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


class L4LLMClassifier:
    """
    Отвечает за два шага L4:
      1. build_prompt + call_with_retries -> LLMResponse
      2. parse -> {type_code, confidence, reasoning, parse_success, raw}
    """

    def __init__(self, llm_client: LLMClient, registry: YAMLRegistry) -> None:
        self.llm_client = llm_client
        self.registry = registry
        self._prompt_template_cache: str | None = None

    def is_available(self) -> bool:
        return self.llm_client.is_available()

    def call(
        self,
        *,
        text: str,
        filename: str,
        folder_path: str,
        allowed_types: list[str],
    ) -> tuple[LLMResponse | None, dict]:
        """
        Вызывает LLM для задачи классификации документа.

        Возвращает:
          (LLMResponse | None, errordetails: dict)
        """
        prompt = self._build_prompt(
            text=text,
            filename=filename,
            folder_path=folder_path,
            allowed_types=allowed_types,
        )

        logger.info(
            "L4LLMClassifier.call",
            extra={
                "allowed_types_count": len(allowed_types or []),
                "allowed_types": allowed_types or [],
                "filename": filename,
                "folder_path": folder_path,
                "prompt_preview": prompt[:300],
            },
        )

        response, errordetails = self.llm_client.call_with_retries(
            prompt=prompt,
            temperature=0.0,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        return response, errordetails

    def parse(
        self,
        response: LLMResponse,
        *,
        allowed_types: List[str],
    ) -> Dict[str, Any]:
        """
        Строго разобрать JSON из ответа LLM и привести к безопасным значениям.

        Контракт возврата:
          {type_code, confidence, reasoning, parse_success, raw}
        """
        text = (getattr(response, "text", "") or "").strip()
        allowed_set = set(allowed_types or [])

        raw: Dict[str, Any] = {
            "provider": getattr(response, "provider", None),
            "model": getattr(response, "model", None),
            "tokens_used": getattr(response, "tokens_used", None),
            "parse_success": False,
            "error_type": None,
            "error_message": None,
            "response_text": text,
            "parsed_json": None,
            "allowed_types": list(allowed_types or []),
        }

        type_code = "UNKNOWN"
        confidence = 0.0
        reasoning = ""
        parse_success = False

        try:
            obj = self._extract_single_json_object(text)
            if not isinstance(obj, dict):
                raise ValueError("LLM response JSON is not an object")

            raw["parsed_json"] = obj

            allowed_keys = {"type_code", "confidence", "reasoning"}
            extra_keys = set(obj.keys()) - allowed_keys
            if extra_keys:
                raise ValueError(f"Unexpected JSON keys: {sorted(extra_keys)}")

            if "type_code" not in obj:
                raise ValueError("Missing required key: type_code")
            if "confidence" not in obj:
                raise ValueError("Missing required key: confidence")
            if "reasoning" not in obj:
                raise ValueError("Missing required key: reasoning")

            raw_type = obj.get("type_code")
            if raw_type is None:
                parsed_type_code = "UNKNOWN"
            elif isinstance(raw_type, str):
                cleaned = raw_type.strip()
                if not cleaned or cleaned.upper() == "UNKNOWN":
                    parsed_type_code = "UNKNOWN"
                elif cleaned in allowed_set:
                    parsed_type_code = cleaned
                else:
                    raise ValueError(f"type_code '{cleaned}' is not in allowed_types")
            else:
                raise ValueError("type_code must be string or null")

            raw_conf = obj.get("confidence")
            if isinstance(raw_conf, bool):
                raise ValueError("confidence must be a float, not bool")
            try:
                parsed_confidence = float(raw_conf)
            except (TypeError, ValueError):
                raise ValueError("confidence must be numeric")

            if not (0.0 <= parsed_confidence <= 1.0):
                raise ValueError("confidence must be between 0 and 1")

            raw_reasoning = obj.get("reasoning")
            if not isinstance(raw_reasoning, str):
                raise ValueError("reasoning must be a string")

            parsed_reasoning = raw_reasoning.strip()
            if not parsed_reasoning:
                raise ValueError("reasoning must be non-empty")
            if len(parsed_reasoning) > 1000:
                parsed_reasoning = parsed_reasoning[:1000].rstrip()

            if parsed_type_code == "UNKNOWN":
                parsed_confidence = 0.0 if parsed_confidence < 0.05 else parsed_confidence

            type_code = parsed_type_code
            confidence = round(_clamp(parsed_confidence, 0.0, 1.0), 4)
            reasoning = parsed_reasoning
            parse_success = True
            raw["parse_success"] = True

        except Exception as e:
            raw.update(
                {
                    "error_type": "parse_error",
                    "error_message": str(e),
                    "parse_success": False,
                }
            )
            type_code = "UNKNOWN"
            confidence = 0.0
            reasoning = ""

            logger.warning(
                "L4LLMClassifier.parse failed",
                extra={
                    "error": str(e),
                    "response_preview": text[:300],
                    "allowed_types": list(allowed_types or []),
                },
            )

        return {
            "type_code": type_code,
            "confidence": confidence,
            "reasoning": reasoning,
            "parse_success": parse_success,
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        *,
        text: str,
        filename: str,
        folder_path: str,
        allowed_types: list[str],
    ) -> str:
        template = self._load_prompt_template()
        available_types_block = self._render_available_types(allowed_types)
        document_fragment = self._build_document_fragment(
            text=text,
            filename=filename,
            folder_path=folder_path,
        )

        prompt = template.format(
            available_types=available_types_block,
            document_fragment=document_fragment,
        )

        logger.debug(
            "L4 prompt built",
            extra={
                "allowed_types_count": len(allowed_types or []),
                "document_fragment_len": len(document_fragment),
                "prompt_len": len(prompt),
            },
        )
        return prompt

    def _load_prompt_template(self) -> str:
        if self._prompt_template_cache:
            return self._prompt_template_cache

        configured = getattr(
            settings,
            "CLASSIFICATION_L4_PROMPT_PATH",
            "/home/vladi/projects/LegalMAS/prompts/classification/classify_document.txt",
        )
        path = Path(configured)

        if not path.exists():
            raise FileNotFoundError(f"L4 prompt template not found: {path}")

        template = path.read_text(encoding="utf-8").strip()
        if "{available_types}" not in template:
            raise ValueError("Prompt template missing required placeholder: {available_types}")
        if "{document_fragment}" not in template:
            raise ValueError("Prompt template missing required placeholder: {document_fragment}")

        self._prompt_template_cache = template
        return template

    def _render_available_types(self, allowed_types: list[str]) -> str:
        rendered: list[dict[str, Any]] = []

        for type_code in allowed_types or []:
            cfg: DocumentTypeConfig | None = self.registry.get_config(type_code)

            if cfg is None:
                rendered.append(
                    {
                        "type_code": type_code,
                        "name": "",
                        "category": "",
                        "language": "",
                        "jurisdiction": "",
                        "risk_level": "",
                    }
                )
                continue

            metadata = (cfg.raw or {}).get("metadata", {}) or {}
            description = str((cfg.raw or {}).get("description", "") or "").strip()
            doc_types_supported = metadata.get("doc_types_supported", []) or []
            subcategory = metadata.get("subcategory", "")

            item: dict[str, Any] = {
                "type_code": cfg.type_code,
                "name": cfg.name,
                "category": cfg.category,
                "subcategory": subcategory,
                "language": cfg.language,
                "jurisdiction": cfg.jurisdiction,
                "risk_level": cfg.risk_level,
            }

            if description:
                item["description"] = description[:500]

            if doc_types_supported:
                item["doc_types_supported"] = [
                    str(x)[:120] for x in doc_types_supported[:8] if str(x).strip()
                ]

            if cfg.aliases:
                item["aliases"] = [str(x)[:80] for x in cfg.aliases[:6] if str(x).strip()]

            rendered.append(item)

        return json.dumps(rendered, ensure_ascii=False, separators=(",", ":"))

    def _build_document_fragment(
        self,
        *,
        text: str,
        filename: str,
        folder_path: str,
    ) -> str:
        max_chars = int(getattr(settings, "CLASSIFICATION_L4_MAX_INPUT_CHARS", 6000))
        safe_text = (text or "").strip()

        prefix = (
            f"Имя файла: {filename or ''}\n"
            f"Путь к папке: {folder_path or ''}\n\n"
            f"Фрагмент текста:\n"
        )

        available_for_text = max(500, max_chars - len(prefix))
        trimmed_text = safe_text[:available_for_text]
        if len(safe_text) > available_for_text:
            trimmed_text = trimmed_text.rstrip() + "\n...[TRUNCATED]"

        return prefix + trimmed_text

    @staticmethod
    def _extract_single_json_object(text: str) -> Dict[str, Any]:
        if not text:
            raise ValueError("Empty LLM response")

        stripped = text.strip()

        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines.startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()

        start_idx = stripped.find("{")
        end_idx = stripped.rfind("}")

        if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
            raise ValueError("No JSON object found in LLM response")

        candidate = stripped[start_idx : end_idx + 1].strip()
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        return obj
    
    
    
    