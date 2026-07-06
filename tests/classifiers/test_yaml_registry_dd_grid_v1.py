# tests/classifiers/test_yaml_registry_dd_grid_v1.py

"""
Tests for DD Grid V1 extensions in YAMLRegistry:
- DocumentTypeGroupConfig dataclass
- registry.yaml `document_type_groups` section parsing
- get_document_type_groups / get_document_type_group public API
- Fallback semantics for missing / malformed entries
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from classifiers.yaml_registry import (
    DocumentTypeConfig,
    DocumentTypeGroupConfig,
    YAMLRegistry,
)


# ─── A. DocumentTypeGroupConfig dataclass ─────────────────────────────────────


class TestDocumentTypeGroupConfig:
    def test_minimal(self) -> None:
        cfg = DocumentTypeGroupConfig(group_id="group_x", label="Label X")
        assert cfg.group_id == "group_x"
        assert cfg.label == "Label X"
        assert cfg.display_order == 9999  # fallback default

    def test_full(self) -> None:
        cfg = DocumentTypeGroupConfig(
            group_id="group_1_ownership",
            label="Передача права собственности",
            display_order=10,
        )
        assert cfg.group_id == "group_1_ownership"
        assert cfg.label == "Передача права собственности"
        assert cfg.display_order == 10

    def test_is_frozen(self) -> None:
        cfg = DocumentTypeGroupConfig(group_id="g", label="L")
        with pytest.raises(Exception):
            cfg.label = "new"  # frozen dataclass


# ─── B. Registry.yaml loading (real fixture) ─────────────────────────────────


def _write_registry_fixture(tmp_path: Path, extra_yaml: str = "") -> Path:
    """
    Build a minimal registry fixture directory:
    - registry.yaml with two document_types
    - two per-type YAML files (empty, cause fallback config path)
    """
    registry_yaml = textwrap.dedent(
        """
        version: "1.0"

        document_types:
          - type: "contract_test_a"
            name: "Test Contract A"
            category: "contract"
            group: "group_alpha"

          - type: "contract_test_b"
            name: "Test Contract B"
            category: "contract"
            group: "group_beta"
        """
    ).lstrip()

    if extra_yaml:
        registry_yaml = registry_yaml + "\n" + textwrap.dedent(extra_yaml).lstrip()

    (tmp_path / "registry.yaml").write_text(registry_yaml, encoding="utf-8")
    (tmp_path / "contract_test_a.yaml").write_text(
        "type: contract_test_a\nname: Test Contract A\n",
        encoding="utf-8",
    )
    (tmp_path / "contract_test_b.yaml").write_text(
        "type: contract_test_b\nname: Test Contract B\n",
        encoding="utf-8",
    )
    return tmp_path


class TestLoadDocumentTypeGroups:
    def test_reads_declared_groups(self, tmp_path: Path) -> None:
        extra = """
        document_type_groups:
          group_alpha:
            label: "Alpha Group"
            display_order: 10
          group_beta:
            label: "Beta Group"
            display_order: 20
        """
        _write_registry_fixture(tmp_path, extra_yaml=extra)

        registry = YAMLRegistry(str(tmp_path))
        groups = registry.get_document_type_groups()

        assert set(groups.keys()) == {"group_alpha", "group_beta"}

        alpha = groups["group_alpha"]
        assert isinstance(alpha, DocumentTypeGroupConfig)
        assert alpha.label == "Alpha Group"
        assert alpha.display_order == 10

        beta = groups["group_beta"]
        assert beta.label == "Beta Group"
        assert beta.display_order == 20

    def test_get_document_type_group_single_lookup(self, tmp_path: Path) -> None:
        extra = """
        document_type_groups:
          group_alpha:
            label: "Alpha Group"
            display_order: 10
        """
        _write_registry_fixture(tmp_path, extra_yaml=extra)

        registry = YAMLRegistry(str(tmp_path))

        alpha = registry.get_document_type_group("group_alpha")
        assert alpha is not None
        assert alpha.label == "Alpha Group"

    def test_get_document_type_group_returns_none_for_unknown(
        self, tmp_path: Path
    ) -> None:
        _write_registry_fixture(tmp_path)
        registry = YAMLRegistry(str(tmp_path))
        assert registry.get_document_type_group("nonexistent") is None

    def test_get_document_type_group_returns_none_for_empty(
        self, tmp_path: Path
    ) -> None:
        _write_registry_fixture(tmp_path)
        registry = YAMLRegistry(str(tmp_path))
        assert registry.get_document_type_group("") is None
        assert registry.get_document_type_group("   ") is None
        assert registry.get_document_type_group(None) is None  # type: ignore[arg-type]

    def test_get_document_type_groups_returns_copy(self, tmp_path: Path) -> None:
        _write_registry_fixture(tmp_path)
        registry = YAMLRegistry(str(tmp_path))

        groups_1 = registry.get_document_type_groups()
        groups_1["injected"] = DocumentTypeGroupConfig(
            group_id="injected", label="Injected"
        )

        groups_2 = registry.get_document_type_groups()
        assert "injected" not in groups_2


# ─── C. Fallback behaviour ────────────────────────────────────────────────────


class TestFallbackWhenSectionMissing:
    def test_section_missing_produces_fallback_for_used_groups(
        self, tmp_path: Path
    ) -> None:
        _write_registry_fixture(tmp_path)  # no document_type_groups section

        registry = YAMLRegistry(str(tmp_path))
        groups = registry.get_document_type_groups()

        assert set(groups.keys()) == {"group_alpha", "group_beta"}
        for gid, cfg in groups.items():
            assert cfg.label == gid
            assert cfg.display_order == 9999

    def test_partial_declaration_fills_missing_with_fallback(
        self, tmp_path: Path
    ) -> None:
        # Declare only group_alpha, group_beta must get fallback.
        extra = """
        document_type_groups:
          group_alpha:
            label: "Alpha Group"
            display_order: 10
        """
        _write_registry_fixture(tmp_path, extra_yaml=extra)

        registry = YAMLRegistry(str(tmp_path))
        groups = registry.get_document_type_groups()

        assert groups["group_alpha"].label == "Alpha Group"
        assert groups["group_alpha"].display_order == 10

        assert groups["group_beta"].label == "group_beta"
        assert groups["group_beta"].display_order == 9999

    def test_declared_group_not_used_is_still_kept(self, tmp_path: Path) -> None:
        # group_extra is declared but no document_type uses it — should still be kept.
        extra = """
        document_type_groups:
          group_alpha:
            label: "Alpha Group"
            display_order: 10
          group_extra:
            label: "Extra Group"
            display_order: 999
        """
        _write_registry_fixture(tmp_path, extra_yaml=extra)

        registry = YAMLRegistry(str(tmp_path))
        groups = registry.get_document_type_groups()

        assert "group_extra" in groups
        assert groups["group_extra"].label == "Extra Group"


# ─── D. Malformed data — defensive parsing ────────────────────────────────────


class TestMalformedEntries:
    def test_non_mapping_section_produces_only_fallbacks(
        self, tmp_path: Path
    ) -> None:
        extra = """
        document_type_groups: "not a mapping"
        """
        _write_registry_fixture(tmp_path, extra_yaml=extra)

        registry = YAMLRegistry(str(tmp_path))
        groups = registry.get_document_type_groups()

        # Fallbacks for used group_ids.
        assert set(groups.keys()) == {"group_alpha", "group_beta"}
        assert all(cfg.display_order == 9999 for cfg in groups.values())

    def test_entry_not_a_dict_uses_fallback(self, tmp_path: Path) -> None:
        extra = """
        document_type_groups:
          group_alpha: "just a string"
          group_beta:
            label: "Beta Group"
            display_order: 20
        """
        _write_registry_fixture(tmp_path, extra_yaml=extra)

        registry = YAMLRegistry(str(tmp_path))
        groups = registry.get_document_type_groups()

        # group_alpha: fallback used because entry is a string.
        assert groups["group_alpha"].label == "group_alpha"
        assert groups["group_alpha"].display_order == 9999

        # group_beta: parsed normally.
        assert groups["group_beta"].label == "Beta Group"
        assert groups["group_beta"].display_order == 20

    def test_entry_with_empty_label_falls_back_to_group_id(
        self, tmp_path: Path
    ) -> None:
        extra = """
        document_type_groups:
          group_alpha:
            label: ""
            display_order: 10
        """
        _write_registry_fixture(tmp_path, extra_yaml=extra)

        registry = YAMLRegistry(str(tmp_path))
        cfg = registry.get_document_type_group("group_alpha")

        assert cfg is not None
        assert cfg.label == "group_alpha"
        # display_order preserved when it is a valid int.
        assert cfg.display_order == 10

    def test_entry_with_non_int_display_order_uses_fallback(
        self, tmp_path: Path
    ) -> None:
        extra = """
        document_type_groups:
          group_alpha:
            label: "Alpha Group"
            display_order: "high"
        """
        _write_registry_fixture(tmp_path, extra_yaml=extra)

        registry = YAMLRegistry(str(tmp_path))
        cfg = registry.get_document_type_group("group_alpha")

        assert cfg is not None
        assert cfg.label == "Alpha Group"
        assert cfg.display_order == 9999


# ─── E. Real production registry.yaml smoke test ──────────────────────────────


class TestProductionRegistryYaml:
    """
    Sanity check that the real registry.yaml loads correctly after V1.5.

    Verifies that our 9 known groups are present with expected labels
    and display_order values.
    """

    def test_real_registry_loads_all_nine_groups(self) -> None:
        registry = YAMLRegistry("playbooks/document_types")
        groups = registry.get_document_type_groups()

        expected_group_ids = {
            "group_1_ownership",
            "group_2_use",
            "group_3_works",
            "group_4_services",
            "group_5_financial",
            "group_6_intermediary",
            "group_7_ip",
            "group_8_partnership",
            "group_9_special",
        }

        assert expected_group_ids.issubset(set(groups.keys()))

    def test_real_registry_group_labels_are_populated(self) -> None:
        registry = YAMLRegistry("playbooks/document_types")

        # Spot-check several groups: labels are non-empty and NOT equal
        # to group_id (proves the declared section was used, not fallback).
        for gid in ("group_1_ownership", "group_5_financial", "group_9_special"):
            cfg = registry.get_document_type_group(gid)
            assert cfg is not None, f"Missing group {gid}"
            assert cfg.label.strip(), f"Empty label for {gid}"
            assert cfg.label != gid, f"Fallback used for {gid}, expected declared label"

    def test_real_registry_display_order_is_monotonic(self) -> None:
        registry = YAMLRegistry("playbooks/document_types")
        groups = registry.get_document_type_groups()

        # Filter to only our known 9 groups (ignore ad-hoc ones if any).
        known = [
            groups[gid]
            for gid in (
                "group_1_ownership",
                "group_2_use",
                "group_3_works",
                "group_4_services",
                "group_5_financial",
                "group_6_intermediary",
                "group_7_ip",
                "group_8_partnership",
                "group_9_special",
            )
            if gid in groups
        ]

        display_orders = [cfg.display_order for cfg in known]
        assert display_orders == sorted(display_orders), (
            f"Groups should be in monotonic display order, got {display_orders}"
        )


        