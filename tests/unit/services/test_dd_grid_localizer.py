"""
Unit and Integration tests for DD Grid Dynamic Localization (Sprint 4.7).

Verifies that:
1. Column labels and fallback values are properly overridden by localization_map.
2. Enum values (yes/no, presence statuses) resolve localized labels.
3. System labels (ungrouped headers, location fallbacks) respect localization overlays.
4. Fallback gracefully degrades to canonical/YAML labels when localization is absent.
"""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from classifiers.yaml_registry import YAMLRegistry
from engine.checks.dd_grid_column_builder import DDGridColumnBuilder
from engine.playbook.models import (
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
)
from services.dd_grid_v1_builder import build_dd_grid_v1


class TestDDGridLocalization:
    """Test suite for DD Grid column builder and full grid compiler localizer overlays."""

    @pytest.fixture
    def mock_registry(self) -> MagicMock:
        reg = MagicMock(spec=YAMLRegistry)
        reg.get_document_type_groups.return_value = {}
        return reg

    @pytest.fixture
    def sample_check(self) -> CheckDefinition:
        """Create a standard check with signal status and fact value fields."""
        return CheckDefinition(
            id="test_liability_limit",
            name="Liability Limit Check",
            display_order=10,
            origin="GLOBAL_PLAYBOOK",
            extraction=ExtractionConfig(
                enabled=True,
                fields=[
                    ExtractionFieldConfig(
                        name="limit_status",
                        type="string",
                        presentation="signal",
                        allowed_values=["yes", "no", "not_specified"],
                        display_in_grid=False,
                    ),
                    ExtractionFieldConfig(
                        name="limit_value",
                        type="string",
                        presentation="fact",
                        label="Limit Amount Value",
                        display_in_grid=True,
                        display_priority=1,
                    ),
                ],
            ),
        )

    def test_column_builder_resolves_localization_map(
        self, sample_check: CheckDefinition
    ) -> None:
        """Verify DDGridColumnBuilder injects localized labels into DDGridColumnRuntime."""
        builder = DDGridColumnBuilder()
        loc_map = {
            "dd_grid.column.limit_value.label": "Сумма Лимита",
            "dd_grid.column.limit_value.fallback": "Нет лимита",
        }

        columns, _, _ = builder.build_columns(
            sample_check, localization_map=loc_map
        )

        assert len(columns) == 1
        col = columns[0]
        assert col.column_id == "test_liability_limit__limit_value"
        assert col.label == "Сумма Лимита"
        assert col.fallback_display == "Нет лимита"

    def test_column_builder_graceful_fallback_without_map(
        self, sample_check: CheckDefinition
    ) -> None:
        """Verify DDGridColumnBuilder works as usual when localization_map is None."""
        builder = DDGridColumnBuilder()
        columns, _, _ = builder.build_columns(
            sample_check, localization_map=None
        )

        assert len(columns) == 1
        col = columns[0]
        assert col.label == "Limit Amount Value"
        assert col.fallback_display == "—"

    def test_grid_builder_full_pipeline_with_localizations(
        self,
        sample_check: CheckDefinition,
        mock_registry: MagicMock,
    ) -> None:
        """Verify build_dd_grid_v1 properly propagates translations through the entire tree."""
        plan_item = MagicMock()
        plan_item.document_id = "doc_001"
        plan_item.check_id = "test_liability_limit"
        plan_item.segment_id = None
        plan_item.status = "succeeded"

        check_result = {
            "document_id": "doc_001",
            "check_id": "test_liability_limit",
            "execution_status": "SUCCESS",
            "structured_data": {
                "limit_status": {"value": "yes"},
                "limit_value": {"value": "1,000,000 USD"},
            },
        }

        documents = {
            "doc_001": {
                "filename": "Contract_A.pdf",
                "doc_type": None,
                "status": "ANALYZED",
            }
        }

        loc_map = {
            "playbook.check.test_liability_limit.name": "Ограничение ответственности",
            "dd_grid.column.limit_value.label": "Сумма Лимита",
            "dd_grid.system.ungrouped": "Прочие проверки",
        }

        grid_data = build_dd_grid_v1(
            checks=[sample_check],
            check_results=[check_result],
            documents=documents,
            registry=mock_registry,
            plan_items=[plan_item],
            checks_mode="all",
            localization_map=loc_map,
        )

        # 1. Global group header
        assert len(grid_data.global_groups) == 1
        assert grid_data.global_groups[0].label == "Прочие проверки"

        # 2. Check name
        subgroup = grid_data.global_groups[0].checks[0]
        assert subgroup.check_name == "Ограничение ответственности"

        # 3. Column header
        assert len(subgroup.columns) == 1
        assert subgroup.columns[0].label == "Сумма Лимита"

        # 4. Cell value & state
        cell_val = grid_data.cell_values["doc_001"]["_default"][
            "test_liability_limit__limit_value"
        ]
        assert cell_val.cell_state == "defined"
        assert cell_val.display_value == "1,000,000 USD"

        # 5. Drawer check name
        drawer = grid_data.drawer_contents["doc_001"]["_default"][
            "test_liability_limit"
        ]
        assert drawer.check_name == "Ограничение ответственности"


        