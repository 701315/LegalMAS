# src/services/global_instruction_compiler.py

"""
Compiler for global instruction YAML.

Global instruction YAML описывает ОДИН check (в отличие от doc-type instruction,
где YAML может содержать массив checks_v8).

Структура global instruction YAML:
  id: "confidentiality_and_trade_secrets"
  name: "..."
  group: "Confidentiality"
  description: "..."
  doc_types: []
  severity: "high"
  detector_type: "hybrid"
  rules: {...}
  llm: {...}
  retrieval: {...}
  extraction: {...}
  ...

compiled_payload = нормализованный dict, совместимый с GlobalCheckConfig
из core/playbooks/compiler.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import yaml

from classifiers.yaml_registry import DocumentTypeConfig
from core.playbooks.compiler import GlobalCheckConfig


class GlobalInstructionCompilationError(Exception):
    """Ошибка parse/validation/compilation global instruction source."""


@dataclass(slots=True)
class GlobalInstructionDiagnostic:
    level: str  # "error" | "warning" | "info"
    message: str
    path: str | None = None


@dataclass(slots=True)
class CompiledGlobalInstruction:
    instruction_code: str
    name: str | None
    group: str | None
    source_yaml: str
    source_sha256: str
    compiled_payload: dict[str, Any]
    compiled_payload_sha256: str
    diagnostics: list[GlobalInstructionDiagnostic]
    validation_report: dict[str, Any]
    is_valid: bool


class GlobalInstructionCompiler:
    """
    Единая точка parse/validate/hash для global instructions.

    Global instruction YAML описывает один check.
    Валидация: проверяем обязательные поля и совместимость с GlobalCheckConfig.
    """

    # Обязательные поля верхнего уровня в global instruction YAML
    REQUIRED_FIELDS = ("id", "name", "detector_type")

    # Допустимые значения detector_type
    VALID_DETECTOR_TYPES = ("rules", "llm", "hybrid")

    def compile(
        self,
        *,
        instruction_code: str,
        source: str | dict[str, Any],
    ) -> CompiledGlobalInstruction:
        instruction_code = str(instruction_code or "").strip()
        if not instruction_code:
            raise GlobalInstructionCompilationError("instruction_code is required")

        raw = self._parse_source(source)
        canonical_yaml = self._dump_canonical(raw)
        source_sha256 = DocumentTypeConfig._compute_sha256(canonical_yaml)

        diagnostics: list[GlobalInstructionDiagnostic] = []

        # Валидация обязательных полей
        for field_name in self.REQUIRED_FIELDS:
            if not raw.get(field_name):
                diagnostics.append(GlobalInstructionDiagnostic(
                    level="error",
                    message=f"Required field '{field_name}' is missing or empty.",
                    path=field_name,
                ))

        # Проверка что id в YAML совпадает с instruction_code
        yaml_id = str(raw.get("id") or "").strip()
        if yaml_id and yaml_id != instruction_code:
            diagnostics.append(GlobalInstructionDiagnostic(
                level="error",
                message=(
                    f"YAML 'id' field ('{yaml_id}') does not match "
                    f"instruction_code ('{instruction_code}')."
                ),
                path="id",
            ))

        # Валидация detector_type
        detector_type = str(raw.get("detector_type") or "").strip()
        if detector_type and detector_type not in self.VALID_DETECTOR_TYPES:
            diagnostics.append(GlobalInstructionDiagnostic(
                level="error",
                message=(
                    f"Invalid detector_type '{detector_type}'. "
                    f"Expected one of: {', '.join(self.VALID_DETECTOR_TYPES)}."
                ),
                path="detector_type",
            ))

        # Валидация совместимости с GlobalCheckConfig
        if not any(d.level == "error" for d in diagnostics):
            try:
                # Убеждаемся что GlobalCheckConfig принимает этот payload
                _check_cfg = GlobalCheckConfig(**raw)
            except Exception as exc:
                diagnostics.append(GlobalInstructionDiagnostic(
                    level="error",
                    message=f"GlobalCheckConfig validation failed: {exc}",
                    path=None,
                ))

        # Предупреждение: нет description
        if not raw.get("description"):
            diagnostics.append(GlobalInstructionDiagnostic(
                level="warning",
                message="Field 'description' is empty or missing.",
                path="description",
            ))

        # Предупреждение: нет group
        if not raw.get("group"):
            diagnostics.append(GlobalInstructionDiagnostic(
                level="warning",
                message="Field 'group' is empty or missing. "
                        "This instruction will appear ungrouped in the catalog.",
                path="group",
            ))

        is_valid = not any(d.level == "error" for d in diagnostics)
        compiled_payload = raw  # normalized parsed dict
        compiled_payload_sha256 = self._compute_payload_sha256(compiled_payload)

        name = str(raw.get("name") or "").strip() or None
        group = str(raw.get("group") or "").strip() or None

        validation_report = {
            "is_valid": is_valid,
            "instruction_code": instruction_code,
            "diagnostics": [
                {
                    "level": d.level,
                    "message": d.message,
                    "path": d.path,
                }
                for d in diagnostics
            ],
        }

        return CompiledGlobalInstruction(
            instruction_code=instruction_code,
            name=name,
            group=group,
            source_yaml=canonical_yaml,
            source_sha256=source_sha256,
            compiled_payload=compiled_payload,
            compiled_payload_sha256=compiled_payload_sha256,
            diagnostics=diagnostics,
            validation_report=validation_report,
            is_valid=is_valid,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_source(self, source: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(source, dict):
            return source

        if not isinstance(source, str) or not source.strip():
            raise GlobalInstructionCompilationError(
                "Global instruction source must be a non-empty YAML string or dict."
            )

        try:
            parsed = yaml.safe_load(source)
        except Exception as exc:
            raise GlobalInstructionCompilationError(
                f"YAML parse error: {exc}"
            ) from exc

        if parsed is None:
            return {}

        if not isinstance(parsed, dict):
            raise GlobalInstructionCompilationError(
                "Global instruction YAML must deserialize to a dict at top level."
            )

        return parsed

    def _dump_canonical(self, raw: dict[str, Any]) -> str:
        return DocumentTypeConfig._dump_canonical_yaml(raw)

    def _compute_payload_sha256(self, payload: dict[str, Any]) -> str:
        canonical_json = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return DocumentTypeConfig._compute_sha256(canonical_json)


        