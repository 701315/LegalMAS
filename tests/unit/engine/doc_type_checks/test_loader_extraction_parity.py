"""Parity tests: DocTypeCheckLoader должен пробрасывать в runtime все поля
Pydantic-моделей, у которых есть активные потребители.

Покрытие:
1. ExtractionConfig.presence_signal — gate в CheckExecutor.
2. ExtractionFieldConfig.risk_weight — DD Grid cell_risk_level.
3. ExtractionFieldConfig.label_en — DD Grid EN-locale.
4. Backward compat: без новых ключей поведение идентично текущему.
5. Contract fail: presence_signal.field не объявлен в fields → ValueError.

NOT covered (by design):
- CheckDefinition.group — doc-type checks не используют глобальную иерархию
  групп; группировка идёт через doc_type class. Зафиксировано тестом
  test_doc_type_loader_dd_grid_v1.py::TestBuildCheckFromV8DisplayOrder::
  test_group_is_not_set_for_doc_type_checks.
"""
import pytest

from engine.doc_type_checks.loader import DocTypeCheckLoader


def _loader() -> DocTypeCheckLoader:
    return DocTypeCheckLoader(provider=None)


class TestPresenceSignalParity:

    def test_presence_signal_propagates_to_extraction_config(self):
        raw = {
            "enabled": True,
            "mode": "hybrid",
            "fields": [
                {
                    "name": "x_presence",
                    "type": "string",
                    "presentation": "signal",
                    "risk_weight": "info",
                    "allowed_values": ["present", "missing", "unclear"],
                    "display_in_grid": False,
                    "required": True,
                }
            ],
            "presence_signal": {
                "field": "x_presence",
                "present_values": ["present"],
                "missing_values": ["missing"],
                "unclear_values": ["unclear"],
            },
        }
        cfg = _loader()._parse_extraction(raw)
        assert cfg is not None
        assert cfg.presence_signal is not None
        assert cfg.presence_signal.field == "x_presence"
        assert cfg.presence_signal.present_values == ["present"]
        assert cfg.presence_signal.missing_values == ["missing"]
        assert cfg.presence_signal.unclear_values == ["unclear"]

    def test_presence_signal_absent_is_none(self):
        raw = {
            "enabled": True,
            "mode": "hybrid",
            "fields": [{"name": "x", "type": "string"}],
        }
        cfg = _loader()._parse_extraction(raw)
        assert cfg is not None
        assert cfg.presence_signal is None

    def test_presence_signal_contract_failure(self):
        """field не объявлен в fields → Pydantic validation error."""
        raw = {
            "enabled": True,
            "mode": "hybrid",
            "fields": [
                {
                    "name": "x",
                    "type": "string",
                    "allowed_values": ["a", "b"],
                }
            ],
            "presence_signal": {
                "field": "nonexistent",
                "present_values": ["a"],
                "missing_values": ["b"],
            },
        }
        with pytest.raises(ValueError, match="not declared"):
            _loader()._parse_extraction(raw)


class TestRiskWeightParity:

    def test_risk_weight_propagates_to_field(self):
        raw = {
            "enabled": True,
            "mode": "hybrid",
            "fields": [
                {
                    "name": "x_status",
                    "type": "string",
                    "presentation": "signal",
                    "risk_weight": "high",
                    "allowed_values": ["defined", "not_defined"],
                }
            ],
        }
        cfg = _loader()._parse_extraction(raw)
        assert cfg is not None
        assert cfg.fields[0].risk_weight is not None
        # RiskWeight — enum, значение может быть RiskWeight.HIGH или строкой
        assert str(cfg.fields[0].risk_weight).lower().endswith("high")

    def test_risk_weight_absent_is_none(self):
        raw = {
            "enabled": True,
            "mode": "hybrid",
            "fields": [{"name": "x", "type": "string"}],
        }
        cfg = _loader()._parse_extraction(raw)
        assert cfg.fields[0].risk_weight is None


class TestLabelEnParity:

    def test_label_en_propagates(self):
        raw = {
            "enabled": True,
            "mode": "hybrid",
            "fields": [
                {
                    "name": "buyer",
                    "type": "string",
                    "label": "Покупатель",
                    "label_en": "Buyer",
                }
            ],
        }
        cfg = _loader()._parse_extraction(raw)
        assert cfg.fields[0].label == "Покупатель"
        assert cfg.fields[0].label_en == "Buyer"

    def test_label_en_absent_is_none(self):
        raw = {
            "enabled": True,
            "mode": "hybrid",
            "fields": [{"name": "buyer", "type": "string", "label": "Покупатель"}],
        }
        cfg = _loader()._parse_extraction(raw)
        assert cfg.fields[0].label_en is None



class TestBackwardCompatibility:

    def test_minimal_yaml_unchanged(self):
        """YAML без новых ключей должен парситься идентично прежнему."""
        raw = {
            "enabled": True,
            "mode": "hybrid",
            "fields": [{"name": "x", "type": "string", "label": "X"}],
        }
        cfg = _loader()._parse_extraction(raw)
        assert cfg is not None
        assert cfg.presence_signal is None
        assert cfg.fields[0].risk_weight is None
        assert cfg.fields[0].label_en is None


