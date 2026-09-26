"""Тесты fallback-фильтра в _build_factual_display_text."""
import pytest

from engine.checks.result_semantics import (
    _build_factual_display_text,
    _is_field_fallback_value,
)
from engine.playbook.models import (
    CheckDefinition, ExtractionConfig, ExtractionFieldConfig,
)


def _make_check(check_id: str, fields: list[ExtractionFieldConfig]) -> CheckDefinition:
    return CheckDefinition(
        id=check_id, name="test", ui_mode="field_extraction",
        extraction=ExtractionConfig(enabled=True, fields=fields),
    )


def _field(name: str, **kwargs) -> ExtractionFieldConfig:
    # CheckDefinition требует explicit label для presentation=fact полей.
    base = {
        "name": name,
        "type": "string",
        "presentation": "fact",
        "label": name,
    }
    base.update(kwargs)
    return ExtractionFieldConfig(**base)


class TestIsFieldFallbackValue:
    def test_match_by_declared_text(self):
        f = _field("x", fallback_texts=["Не установлено"])
        check = _make_check("c", [f])
        assert _is_field_fallback_value(check, "x", "Не установлено") is True
        assert _is_field_fallback_value(check, "x", "  Не установлено  ") is True

    def test_no_match_meaningful(self):
        f = _field("x", fallback_texts=["Не установлено"])
        check = _make_check("c", [f])
        assert _is_field_fallback_value(check, "x", "Самовывоз") is False

    def test_empty_fallback_texts(self):
        f = _field("x")
        check = _make_check("c", [f])
        assert _is_field_fallback_value(check, "x", "Не установлено") is False


class TestDisplayPriorityAfterFallbackFilter:
    """Priority 2 (display_in_grid) — детерминированная сводка."""

    def test_summary_skips_fallback_uses_meaningful(self):
        check = _make_check("c", [
            _field("delivery_term_details", display_in_grid=True,
                   display_priority=1, fallback_texts=["Не установлен"]),
            _field("transfer_documents_details", display_in_grid=True,
                   display_priority=4, fallback_texts=["Не установлены"]),
            _field("product_documents_details", display_in_grid=True,
                   display_priority=6, fallback_texts=["Не установлены"]),
        ])
        sd = {
            "delivery_term_details": {"value": "Не установлен", "found": True},
            "transfer_documents_details": {"value": "Акт приема-передачи", "found": True},
            "product_documents_details": {"value": "Вся документация", "found": True},
        }
        result = _build_factual_display_text(
            check=check, ui_mode="field_extraction", structured_data=sd,
        )
        assert result is not None
        assert "Акт приема-передачи" in result
        assert "Вся документация" in result
        assert "Не установлен" not in result

    def test_summary_all_fallback_returns_none(self):
        """Если все поля fallback → нет сводки → падаем на следующие приоритеты."""
        check = _make_check("c", [
            _field("x_details", display_in_grid=True, display_priority=1,
                   fallback_texts=["Не установлено"]),
        ])
        sd = {"x_details": {"value": "Не установлено", "found": True}}
        result = _build_factual_display_text(
            check=check, ui_mode="field_extraction", structured_data=sd,
        )
        # Сводка пустая, legacy *_display не найден, primary fact — тоже fallback
        assert result is None


class TestPartyAuthorityDeterministic:
    """Priority 2 по display_priority, а не по порядку jsonb."""

    def test_uses_display_priority_not_jsonb_order(self):
        # Порядок полей в check конфиге — правильный (по priority).
        check = _make_check("parties_and_authority", [
            _field("buyer_details_value", display_in_grid=True,
                   display_priority=1, fallback_texts=["Данные не определены"]),
            _field("seller_details_value", display_in_grid=True,
                   display_priority=2, fallback_texts=["Данные не определены"]),
            _field("buyer_signatory", display_in_grid=True,
                   display_priority=3, fallback_texts=["Данные не определены"]),
            _field("buyer_signatory_basis_display", display_in_grid=True,
                   display_priority=4, fallback_texts=["Данные не определены"]),
        ])
        # Порядок в structured_data — рандомный (jsonb).
        sd = {
            "buyer_signatory_basis_display": {"value": "Устав", "found": True},
            "buyer_signatory": {"value": "Иванов И.И.", "found": True},
            "buyer_details_value": {"value": "ООО Ромашка", "found": True},
            "seller_details_value": {"value": "ООО Лютик", "found": True},
        }
        result = _build_factual_display_text(
            check=check, ui_mode="field_extraction", structured_data=sd,
        )
        assert result is not None
        # Должны быть первые 3 по priority (MAX_FACT_FIELDS_IN_DISPLAY=3)
        assert "ООО Ромашка" in result
        assert "ООО Лютик" in result
        assert "Иванов И.И." in result

