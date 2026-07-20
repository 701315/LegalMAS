# src/services/instruction_compiler.py

"""
Instruction compiler for document-type instructions.

Задача:
- принять YAML/parsed dict инструкции;
- стабильно нормализовать source;
- посчитать source hash и payload hash;
- проверить, что loader способен построить checks;
- собрать validation report для draft/publish lifecycle.

Важно:
- это не финальный "компилятор всего instruction domain",
  а первый production-ready шаг для backend lifecycle;
- compiled_payload на текущем этапе = нормализованный parsed dict,
  потому что runtime loader исполняет именно такую структуру;
- publish service будет использовать этот compiler как единую точку
  parse/validate/hash.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

import yaml

from classifiers.yaml_registry import DocumentTypeConfig
from engine.doc_type_checks.loader import DatabaseInstructionProvider, DocTypeCheckLoader


class InstructionCompilationError(Exception):
    """Ошибка parse/validation/compilation instruction source."""


@dataclass(slots=True)
class CompilationDiagnostic:
    level: str  # "error" | "warning" | "info"
    message: str
    path: str | None = None


@dataclass(slots=True)
class CompiledDocTypeInstruction:
    doc_type_code: str
    source_yaml: str
    source_sha256: str
    compiled_payload: dict[str, Any]
    compiled_payload_sha256: str
    checks_count: int
    triggers_used_for_validation: list[str]
    diagnostics: list[CompilationDiagnostic]
    validation_report: dict[str, Any]
    is_valid: bool


class InstructionCompiler:
    """
    Единая точка parse/validate/hash для doc-type instructions.

    На этом этапе:
    - валидирует YAML как object/dict;
    - собирает все trigger names из source;
    - прогоняет DocTypeCheckLoader поверх DatabaseInstructionProvider;
    - детектит duplicate check IDs;
    - считает deterministic hashes.
    """

    def compile_doc_type_instruction(
        self,
        *,
        doc_type_code: str,
        source: str | dict[str, Any],
    ) -> CompiledDocTypeInstruction:
        doc_type_code = str(doc_type_code or "").strip()
        if not doc_type_code:
            raise InstructionCompilationError("doc_type_code is required")

        raw = self._parse_source_to_dict(source)
        canonical_yaml = DocumentTypeConfig._dump_canonical_yaml(raw)
        source_sha256 = DocumentTypeConfig._compute_sha256(canonical_yaml)

        validation_triggers = self._collect_all_triggers(raw)

        # ВАЖНО:
        # current runtime path исполняет structured YAML dict через loader.
        # Поэтому compiled_payload на текущем этапе = нормализованный parsed dict.
        compiled_payload: dict[str, Any] = raw
        compiled_payload_sha256 = self._compute_payload_sha256(compiled_payload)

        diagnostics: list[CompilationDiagnostic] = []

        checks = self._load_all_checks_for_validation(
            doc_type_code=doc_type_code,
            compiled_payload=compiled_payload,
            validation_triggers=validation_triggers,
        )

        duplicate_ids = self._find_duplicate_check_ids(checks)
        if duplicate_ids:
            diagnostics.append(
                CompilationDiagnostic(
                    level="error",
                    message=(
                        "Duplicate check IDs found: "
                        + ", ".join(sorted(duplicate_ids))
                    ),
                    path="checks",
                )
            )

        if len(checks) == 0:
            diagnostics.append(
                CompilationDiagnostic(
                    level="warning",
                    message=(
                        "Instruction compiled successfully but no checks were produced "
                        "for validation trigger set."
                    ),
                    path="checks",
                )
            )

        is_valid = not any(d.level == "error" for d in diagnostics)

        validation_report = {
            "is_valid": is_valid,
            "checks_count": len(checks),
            "validation_triggers": validation_triggers,
            "diagnostics": [
                {
                    "level": d.level,
                    "message": d.message,
                    "path": d.path,
                }
                for d in diagnostics
            ],
        }

        return CompiledDocTypeInstruction(
            doc_type_code=doc_type_code,
            source_yaml=canonical_yaml,
            source_sha256=source_sha256,
            compiled_payload=compiled_payload,
            compiled_payload_sha256=compiled_payload_sha256,
            checks_count=len(checks),
            triggers_used_for_validation=validation_triggers,
            diagnostics=diagnostics,
            validation_report=validation_report,
            is_valid=is_valid,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_source_to_dict(
        self,
        source: str | dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(source, dict):
            return source

        if not isinstance(source, str) or not source.strip():
            raise InstructionCompilationError("instruction source must be non-empty YAML string or dict")

        try:
            parsed = yaml.safe_load(source)
        except Exception as e:
            raise InstructionCompilationError(f"YAML parse error: {e}") from e

        if parsed is None:
            return {}

        if not isinstance(parsed, dict):
            raise InstructionCompilationError(
                "instruction YAML must deserialize to an object/dict at top level"
            )

        return parsed

    def _collect_all_triggers(
        self,
        raw: dict[str, Any],
    ) -> list[str]:
        """
        Собрать объединение всех triggers из checks_v8/doc_type_checks/compliance_rules,
        чтобы validation loader прошёл по максимально широкому пути.
        """
        trigger_names: set[str] = set()

        for item in raw.get("checks_v8") or []:
            if not isinstance(item, dict):
                continue
            triggers_cfg = item.get("triggers") or {}
            trigger_names.update(str(x) for x in (triggers_cfg.get("any") or []) if x)
            trigger_names.update(str(x) for x in (triggers_cfg.get("all") or []) if x)

        for item in raw.get("doc_type_checks") or []:
            if not isinstance(item, dict):
                continue
            triggers_cfg = item.get("triggers") or {}
            trigger_names.update(str(x) for x in (triggers_cfg.get("any") or []) if x)
            trigger_names.update(str(x) for x in (triggers_cfg.get("all") or []) if x)

        for item in raw.get("compliance_rules") or []:
            if not isinstance(item, dict):
                continue
            trigger_names.update(str(x) for x in (item.get("required_triggers") or []) if x)

        return sorted(trigger_names)

    def _load_all_checks_for_validation(
        self,
        *,
        doc_type_code: str,
        compiled_payload: dict[str, Any],
        validation_triggers: list[str],
    ):
        provider = DatabaseInstructionProvider(
            {doc_type_code: compiled_payload}
        )
        loader = DocTypeCheckLoader(provider=provider)

        try:
            return loader.load_checks_for_doc(
                doc_type=doc_type_code,
                applicable_triggers=validation_triggers,
            )
        except Exception as e:
            raise InstructionCompilationError(
                f"DocTypeCheckLoader validation failed: {e}"
            ) from e

    def _find_duplicate_check_ids(self, checks: list[Any]) -> set[str]:
        ids = [
            str(getattr(check, "id", "") or "").strip()
            for check in checks
            if str(getattr(check, "id", "") or "").strip()
        ]
        counter = Counter(ids)
        return {check_id for check_id, count in counter.items() if count > 1}

    def _compute_payload_sha256(
        self,
        payload: dict[str, Any],
    ) -> str:
        canonical_json = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return DocumentTypeConfig._compute_sha256(canonical_json)
    

    