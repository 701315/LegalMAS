import re

from classifiers.yaml_registry import YAMLRegistry


class DummyConfig:
    def __init__(self, type_code: str, lexical_signals: dict):
        self.type_code = type_code
        self.lexical_signals = lexical_signals
        self.source_path = f"/fake/{type_code}.yaml"


def test_validate_cross_type_distinctive_patterns_detects_duplicates():
    registry = object.__new__(YAMLRegistry)
    registry._configs = {
        "type_a": DummyConfig(
            "type_a",
            {
                "high": [
                    {
                        "pattern": re.compile(r"exclusive marker", re.IGNORECASE),
                        "distinctiveness": "high",
                        "context": "header",
                        "weight": 0.7,
                        "description": "A marker",
                    }
                ],
                "medium": [],
                "low": [],
            },
        ),
        "type_b": DummyConfig(
            "type_b",
            {
                "high": [
                    {
                        "pattern": re.compile(r"exclusive marker", re.IGNORECASE),
                        "distinctiveness": "high",
                        "context": "any",
                        "weight": 0.8,
                        "description": "Same marker in another type",
                    }
                ],
                "medium": [],
                "low": [],
            },
        ),
    }

    warnings = registry.validate_cross_type_distinctive_patterns()

    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["pattern"] == "exclusive marker"
    assert sorted(warning["types"]) == ["type_a", "type_b"]
    assert len(warning["occurrences"]) == 2


def test_validate_cross_type_distinctive_patterns_ignores_non_high_distinctive():
    registry = object.__new__(YAMLRegistry)
    registry._configs = {
        "type_a": DummyConfig(
            "type_a",
            {
                "high": [
                    {
                        "pattern": re.compile(r"shared marker", re.IGNORECASE),
                        "distinctiveness": "medium",
                        "context": "header",
                        "weight": 0.5,
                    }
                ],
                "medium": [],
                "low": [],
            },
        ),
        "type_b": DummyConfig(
            "type_b",
            {
                "high": [
                    {
                        "pattern": re.compile(r"shared marker", re.IGNORECASE),
                        "distinctiveness": "medium",
                        "context": "any",
                        "weight": 0.5,
                    }
                ],
                "medium": [],
                "low": [],
            },
        ),
    }

    warnings = registry.validate_cross_type_distinctive_patterns()

    assert warnings == []


    