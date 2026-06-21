"""
Tests for DocTypeCheckLoader retrieval config parsing.

Covers:
- checks_v8: full retrieval block is parsed into RetrievalConfig
- doc_type_checks: retrieval block overrides fallback boost_keywords logic
- compliance_rules: retrieval block is parsed into RetrievalConfig
- malformed retrieval config -> graceful fallback to defaults
"""

from engine.doc_type_checks.loader import DocTypeCheckLoader
from engine.playbook.models import RetrievalConfig


def _make_loader() -> DocTypeCheckLoader:
    return DocTypeCheckLoader(registry_dir="playbooks/document_types")


class TestParseRetrievalConfig:
    def test_empty_retrieval_returns_defaults(self) -> None:
        loader = _make_loader()
        cfg = loader._parse_retrieval_config(None)

        assert isinstance(cfg, RetrievalConfig)
        assert cfg.context_k == 5
        assert cfg.retrieval_query is None
        assert cfg.boost_keywords == []
        assert cfg.negative_keywords == []
        assert cfg.preferred_unit_types == []
        assert cfg.excluded_unit_types == []
        assert cfg.preferred_clause_functions == []
        assert cfg.levels == ["legal_unit", "section"]

    def test_full_retrieval_block_is_parsed(self) -> None:
        loader = _make_loader()

        raw = {
            "context_k": 7,
            "max_chunks": 11,
            "retrieval_query": "продавец покупатель полномочия подписант",
            "boost_keywords": ["продавец", "покупатель"],
            "negative_keywords": ["означает", "термин"],
            "preferred_unit_types": ["obligation", "general_provision"],
            "excluded_unit_types": ["definition", "technical_fragment"],
            "preferred_clause_functions": ["representations", "boilerplate"],
            "position_bias": {
                "preferred_range": [0.0, 0.25],
                "boost": 0.4,
                "scope": "auto",
            },
            "rerank": False,
            "filters": {"country": "RU"},
            "levels": ["legal_unit", "section"],
            "required_kind": "legal_unit",
            "retrieval_profile": "party_identification_check",
        }

        cfg = loader._parse_retrieval_config(raw)

        assert cfg.context_k == 7
        assert cfg.max_chunks == 11
        assert cfg.retrieval_query == "продавец покупатель полномочия подписант"
        assert cfg.boost_keywords == ["продавец", "покупатель"]
        assert cfg.negative_keywords == ["означает", "термин"]
        assert cfg.preferred_unit_types == ["obligation", "general_provision"]
        assert cfg.excluded_unit_types == ["definition", "technical_fragment"]
        assert cfg.preferred_clause_functions == ["representations", "boilerplate"]
        assert cfg.position_bias is not None
        assert cfg.position_bias.preferred_range == [0.0, 0.25]
        assert cfg.position_bias.boost == 0.4
        assert cfg.position_bias.scope == "auto"
        assert cfg.rerank is False
        assert cfg.filters == {"country": "RU"}
        assert cfg.levels == ["legal_unit", "section"]
        assert cfg.required_kind == "legal_unit"
        assert cfg.retrieval_profile == "party_identification_check"

    def test_malformed_position_bias_falls_back_to_defaults(self) -> None:
        loader = _make_loader()

        raw = {
            "context_k": 6,
            "position_bias": {
                "preferred_range": ["bad", "data"],  # invalid
                "boost": 0.5,
            },
        }

        cfg = loader._parse_retrieval_config(raw)

        # Whole retrieval config falls back to defaults on parse error
        assert cfg.context_k == 5
        assert cfg.position_bias is None
        assert cfg.levels == ["legal_unit", "section"]


class TestBuildCheckFromV8:
    def test_checks_v8_preserves_full_retrieval_config(self) -> None:
        loader = _make_loader()

        item = {
            "id": "parties_and_authority",
            "name": "Стороны договора",
            "description": "test",
            "origin": "DOCUMENT_TYPE",
            "severity": "critical",
            "detector_type": "hybrid",
            "rules": {
                "keywords": ["продавец", "покупатель"],
            },
            "llm": {
                "prompt_template": "test prompt",
            },
            "retrieval": {
                "retrieval_query": "продавец покупатель стороны договора",
                "negative_keywords": ["означает", "термин"],
                "preferred_unit_types": ["obligation"],
                "excluded_unit_types": ["definition"],
                "preferred_clause_functions": ["representations"],
                "position_bias": {
                    "preferred_range": [0.0, 0.25],
                    "boost": 0.4,
                    "scope": "auto",
                },
                "levels": ["legal_unit", "section"],
                "required_kind": "legal_unit",
            },
        }

        check = loader._build_check_from_v8(
            item=item,
            doc_type="contract_1.1_general_sale",
            shared_patterns={},
        )

        assert check is not None
        assert check.retrieval.retrieval_query == "продавец покупатель стороны договора"
        assert check.retrieval.negative_keywords == ["означает", "термин"]
        assert check.retrieval.preferred_unit_types == ["obligation"]
        assert check.retrieval.excluded_unit_types == ["definition"]
        assert check.retrieval.preferred_clause_functions == ["representations"]
        assert check.retrieval.position_bias is not None
        assert check.retrieval.position_bias.preferred_range == [0.0, 0.25]
        assert check.retrieval.required_kind == "legal_unit"
        assert check.retrieval.levels == ["legal_unit", "section"]


class TestBuildCheckFromDocType:
    def test_doc_type_check_uses_yaml_retrieval_if_present(self) -> None:
        loader = _make_loader()

        item = {
            "id": "force_majeure",
            "name": "Форс-мажор",
            "description": "test",
            "rules": {
                "keywords": ["форс-мажор", "непреодолимая сила"],
            },
            "retrieval": {
                "retrieval_query": "форс-мажор непреодолимая сила уведомление",
                "excluded_unit_types": ["definition"],
                "levels": ["legal_unit", "section"],
            },
        }

        check = loader._build_check_from_doc_type(
            item=item,
            doc_type="contract_4.1_services",
            shared_patterns={},
        )

        assert check is not None
        assert check.retrieval.retrieval_query == "форс-мажор непреодолимая сила уведомление"
        assert check.retrieval.excluded_unit_types == ["definition"]
        assert check.retrieval.levels == ["legal_unit", "section"]

    def test_doc_type_check_falls_back_to_boost_keywords_if_no_retrieval(self) -> None:
        loader = _make_loader()

        item = {
            "id": "force_majeure",
            "name": "Форс-мажор",
            "description": "test",
            "rules": {
                "keywords": ["форс-мажор", "непреодолимая сила", "уведомление"],
            },
        }

        check = loader._build_check_from_doc_type(
            item=item,
            doc_type="contract_4.1_services",
            shared_patterns={},
        )

        assert check is not None
        assert check.retrieval.boost_keywords == [
            "форс-мажор",
            "непреодолимая сила",
            "уведомление",
        ]
        assert check.retrieval.retrieval_query is None


class TestBuildComplianceCheck:
    def test_compliance_rule_uses_full_retrieval_block(self) -> None:
        loader = _make_loader()

        rule = {
            "id": "compliance_rule_1",
            "name": "Compliance rule",
            "description": "test",
            "severity": "critical",
            "rules": {
                "keywords": ["обязателен", "запрещено"],
            },
            "retrieval": {
                "retrieval_query": "обязателен запрещено согласование",
                "preferred_clause_functions": ["obligations"],
                "levels": ["legal_unit", "section"],
            },
        }

        check = loader._build_compliance_check(
            rule=rule,
            doc_type="contract_1.1_general_sale",
        )

        assert check is not None
        assert check.retrieval.retrieval_query == "обязателен запрещено согласование"
        assert check.retrieval.preferred_clause_functions == ["obligations"]
        assert check.retrieval.levels == ["legal_unit", "section"]


        