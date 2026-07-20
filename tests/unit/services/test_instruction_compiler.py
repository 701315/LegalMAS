from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.instruction_compiler import (
    InstructionCompilationError,
    InstructionCompiler,
)


@pytest.fixture
def compiler() -> InstructionCompiler:
    return InstructionCompiler()


class TestInstructionCompiler:
    def test_compile_doc_type_instruction_from_yaml_success(self, compiler: InstructionCompiler) -> None:
        source_yaml = """
checks_v8:
  - id: check_1
    name: Check 1
    severity: high
    triggers:
      any: [t1]
"""

        fake_checks = [
            SimpleNamespace(id="check_1"),
            SimpleNamespace(id="check_2"),
        ]

        with patch(
            "services.instruction_compiler.DocTypeCheckLoader.load_checks_for_doc",
            return_value=fake_checks,
        ):
            result = compiler.compile_doc_type_instruction(
                doc_type_code="nda",
                source=source_yaml,
            )

        assert result.doc_type_code == "nda"
        assert result.source_yaml
        assert result.source_sha256
        assert result.compiled_payload_sha256
        assert result.checks_count == 2
        assert result.triggers_used_for_validation == ["t1"]
        assert result.is_valid is True
        assert result.validation_report["is_valid"] is True
        assert result.validation_report["checks_count"] == 2

    def test_compile_doc_type_instruction_from_dict_success(self, compiler: InstructionCompiler) -> None:
        source_dict = {
            "checks_v8": [
                {
                    "id": "check_1",
                    "name": "Check 1",
                }
            ]
        }

        fake_checks = [SimpleNamespace(id="check_1")]

        with patch(
            "services.instruction_compiler.DocTypeCheckLoader.load_checks_for_doc",
            return_value=fake_checks,
        ):
            result = compiler.compile_doc_type_instruction(
                doc_type_code="nda",
                source=source_dict,
            )

        assert result.doc_type_code == "nda"
        assert result.checks_count == 1
        assert result.is_valid is True

    def test_compile_rejects_empty_doc_type_code(self, compiler: InstructionCompiler) -> None:
        with pytest.raises(InstructionCompilationError, match="doc_type_code is required"):
            compiler.compile_doc_type_instruction(
                doc_type_code="",
                source={},
            )

    def test_compile_rejects_non_object_yaml(self, compiler: InstructionCompiler) -> None:
        with pytest.raises(
            InstructionCompilationError,
            match="top level",
        ):
            compiler.compile_doc_type_instruction(
                doc_type_code="nda",
                source="- item1\n- item2\n",
            )

    def test_compile_rejects_invalid_yaml(self, compiler: InstructionCompiler) -> None:
        with pytest.raises(InstructionCompilationError, match="YAML parse error"):
            compiler.compile_doc_type_instruction(
                doc_type_code="nda",
                source=":\n  bad",
            )

    def test_compile_detects_duplicate_check_ids(self, compiler: InstructionCompiler) -> None:
        source_dict = {"checks_v8": [{"id": "dup"}, {"id": "dup"}]}

        fake_checks = [
            SimpleNamespace(id="dup"),
            SimpleNamespace(id="dup"),
        ]

        with patch(
            "services.instruction_compiler.DocTypeCheckLoader.load_checks_for_doc",
            return_value=fake_checks,
        ):
            result = compiler.compile_doc_type_instruction(
                doc_type_code="nda",
                source=source_dict,
            )

        assert result.is_valid is False
        assert any("Duplicate check IDs" in d.message for d in result.diagnostics)

    def test_compile_warns_on_zero_checks(self, compiler: InstructionCompiler) -> None:
        with patch(
            "services.instruction_compiler.DocTypeCheckLoader.load_checks_for_doc",
            return_value=[],
        ):
            result = compiler.compile_doc_type_instruction(
                doc_type_code="nda",
                source={},
            )

        assert result.is_valid is True
        assert result.checks_count == 0
        assert any(d.level == "warning" for d in result.diagnostics)


        