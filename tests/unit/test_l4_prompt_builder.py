# tests/unit/test_l4_prompt_builder.py
"""
Unit-тесты для _build_prompt, _wrap_chatml, _render_available_types,
_build_document_fragment, _estimate_token_count.
"""
from unittest.mock import MagicMock, patch
import pytest

from src.classifiers.stage8._l4_llm import L4LLMClassifier, _CHATML_IM_START, _CHATML_IM_END


def _make_classifier(prompt_template: str = None) -> L4LLMClassifier:
    llm_client = MagicMock()
    llm_client.is_available.return_value = True
    registry = MagicMock()
    registry.get_config.return_value = None  # tolerant mode — нет метаданных
    clf = L4LLMClassifier(llm_client=llm_client, registry=registry)
    if prompt_template:
        clf._prompt_template_cache = prompt_template
    return clf


MINIMAL_TEMPLATE = (
    "TYPES:\n{available_types}\n\nDOC:\n{document_fragment}\n\nReturn JSON."
)


class TestWrapChatML:

    def test_contains_system_block(self):
        prompt = L4LLMClassifier._wrap_chatml(
            system_instruction="Be precise.",
            user_content="Classify this.",
        )
        assert f"{_CHATML_IM_START}system\n" in prompt
        assert "Be precise." in prompt
        assert _CHATML_IM_END in prompt

    def test_contains_user_block(self):
        prompt = L4LLMClassifier._wrap_chatml(
            system_instruction="S",
            user_content="U",
        )
        assert f"{_CHATML_IM_START}user\n" in prompt
        assert "U" in prompt

    def test_ends_with_assistant_tag(self):
        """Открытый assistant-тег — стандартный способ начать генерацию."""
        prompt = L4LLMClassifier._wrap_chatml(
            system_instruction="S",
            user_content="U",
        )
        assert prompt.endswith(f"{_CHATML_IM_START}assistant\n")

    def test_no_closing_assistant_im_end(self):
        """assistant-блок НЕ закрывается — модель сама генерирует до <|im_end|>."""
        prompt = L4LLMClassifier._wrap_chatml(
            system_instruction="S",
            user_content="U",
        )
        parts = prompt.split(f"{_CHATML_IM_START}assistant\n")
        assert len(parts) == 2
        assert parts[1] == ""  # после открытого assistant-тега ничего нет


class TestRenderAvailableTypes:

    def test_returns_valid_json(self):
        clf = _make_classifier()
        result = clf._render_available_types(["contract_1.1_general_sale"])
        import json
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert parsed[0]["type_code"] == "contract_1.1_general_sale"  # [0] ← фикс

    def test_compact_fields_only(self):
        """Рендер должен содержать только type_code, name, short_desc."""
        clf = _make_classifier()
        result = clf._render_available_types(["t1"])
        import json
        item = json.loads(result)[0]  # [0] ← фикс
        assert set(item.keys()) == {"type_code", "name", "short_desc"}

    def test_no_aliases_no_doc_types_supported(self):
        """aliases и doc_types_supported не должны попасть в компактный рендер."""
        registry = MagicMock()
        cfg = MagicMock()
        cfg.type_code = "contract_1.6_real_estate"
        cfg.name = "Договор купли-продажи недвижимости"
        cfg.raw = {
            "description": "Переход права собственности.",
            "metadata": {"aliases": ["SPA", "ДКП"], "doc_types_supported": ["pdf"]},
        }
        registry.get_config.return_value = cfg
        clf = L4LLMClassifier(llm_client=MagicMock(), registry=registry)
        result = clf._render_available_types(["contract_1.6_real_estate"])
        import json
        item = json.loads(result)
        assert "aliases" not in item
        assert "doc_types_supported" not in item


class TestBuildDocumentFragment:

    def test_respects_max_chars(self):
        clf = _make_classifier()
        long_text = "А" * 10_000
        fragment = clf._build_document_fragment(
            text=long_text,
            filename="test.pdf",
            folder_path="/docs",
            max_chars=1000,
        )
        assert len(fragment) <= 1100  # с небольшим запасом на prefix

    def test_truncated_marker_present(self):
        clf = _make_classifier()
        long_text = "Б" * 10_000
        fragment = clf._build_document_fragment(
            text=long_text, filename="f", folder_path="p", max_chars=500
        )
        assert "[TRUNCATED]" in fragment

    def test_short_text_not_truncated(self):
        clf = _make_classifier()
        text = "Короткий текст."
        fragment = clf._build_document_fragment(
            text=text, filename="f", folder_path="p", max_chars=6000
        )
        assert "[TRUNCATED]" not in fragment
        assert "Короткий текст." in fragment

    def test_fallback_when_max_chars_none(self):
        """Если max_chars=None, используется CLASSIFICATION_L4_MAX_INPUT_CHARS."""
        clf = _make_classifier()
        text = "Текст"
        fragment = clf._build_document_fragment(
            text=text, filename="f", folder_path="p", max_chars=None
        )
        assert "Текст" in fragment


class TestEstimateTokenCount:

    def test_empty_string(self):
        assert L4LLMClassifier._estimate_token_count("") == 0

    def test_basic_estimate(self):
        text = "А" * 300
        assert L4LLMClassifier._estimate_token_count(text) == 100

    def test_minimum_one(self):
        assert L4LLMClassifier._estimate_token_count("А") == 1


class TestBuildPromptIntegration:

    def test_prompt_contains_chatml_tags(self):
        clf = _make_classifier(prompt_template=MINIMAL_TEMPLATE)
        with patch("src.classifiers.stage8._l4_llm.settings") as mock_settings:
            mock_settings.LLM_CONTEXT_LIMIT = 8192
            mock_settings.LLM_MAX_TOKENS = 256
            mock_settings.LLM_SAFETY_MARGIN_TOKENS = 512
            mock_settings.CLASSIFICATION_L4_MAX_INPUT_CHARS = 6000
            mock_settings.CLASSIFICATION_L4_REASONING_MAX_CHARS = 1000
            prompt = clf._build_prompt(
                text="Договор купли-продажи недвижимости.",
                filename="test.pdf",
                folder_path="/docs",
                allowed_types=["contract_1.6_real_estate"],
            )
        assert _CHATML_IM_START in prompt
        assert "assistant" in prompt

    def test_prompt_fits_in_budget(self):
        clf = _make_classifier(prompt_template=MINIMAL_TEMPLATE)
        with patch("src.classifiers.stage8._l4_llm.settings") as mock_settings:
            mock_settings.LLM_CONTEXT_LIMIT = 8192
            mock_settings.LLM_MAX_TOKENS = 256
            mock_settings.LLM_SAFETY_MARGIN_TOKENS = 512
            mock_settings.CLASSIFICATION_L4_MAX_INPUT_CHARS = 6000
            mock_settings.CLASSIFICATION_L4_REASONING_MAX_CHARS = 1000
            long_text = "Текст договора. " * 3000  # ~48k символов
            prompt = clf._build_prompt(
                text=long_text,
                filename="long.pdf",
                folder_path="/docs",
                allowed_types=["contract_1.6_real_estate"],
            )
        max_budget = (8192 - 256 - 512) * 3  # символов
        assert len(prompt) <= max_budget * 1.05  # 5% допуск на эвристику


