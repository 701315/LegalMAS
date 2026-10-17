#!/usr/bin/env python3
"""Fix P2+P3+L4 в amount_minimum_compliance_check:
1) Восстанавливает fields (10 полей: presence + 9 содержательных).
2) Дописывает финальную строку output_expectations.
3) Возвращает store_payload: true.
"""
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import LiteralScalarString

FILE = "playbooks/document_types/group_9_special/contract_9.4_alimony_agreement.yaml"
CHECK_ID = "amount_minimum_compliance_check"


def F(**kwargs):
    m = CommentedMap()
    for k, v in kwargs.items():
        m[k] = v
    return m


def build_fields():
    fields = CommentedSeq()
    fields.append(F(
        name="amount_minimum_compliance_check_presence",
        type="string",
        presentation="signal",
        risk_weight="info",
        allowed_values=["present", "missing", "unclear"],
        display_in_grid=False,
        description="Наличие регулирования по размеру алиментов и соответствию минимуму. Внутреннее агрегатное signal-поле.",
        required=True,
    ))
    fields.append(F(
        name="amount_type",
        type="string",
        presentation="signal",
        risk_weight="high",
        allowed_values=["proportional", "fixed", "mixed", "property_transfer", "not_defined"],
        display_in_grid=False,
        description="Способ определения размера алиментов (raw enum). Внутреннее enum-поле.",
        required=True,
    ))
    fields.append(F(
        name="amount_value_status",
        type="string",
        presentation="signal",
        risk_weight="high",
        allowed_values=["defined", "not_defined"],
        display_in_grid=False,
        description="Статус указания конкретного размера алиментов. Внутреннее enum-поле.",
        required=True,
    ))
    fields.append(F(
        name="amount_value_details",
        type="string",
        presentation="fact",
        display_in_grid=True,
        display_priority=1,
        label="Размер алиментов",
        description=LiteralScalarString(
            "Конкретный размер (сумма или доля).\n"
            'Fallback: "Данные не определены" / "Не удалось определить".\n'
        ),
        required=True,
    ))
    fields.append(F(
        name="minimum_compliance_status",
        type="string",
        presentation="signal",
        risk_weight="high",
        allowed_values=["compliant", "below_minimum", "not_evaluable", "not_applicable", "not_defined"],
        display_in_grid=False,
        description="Оценка соответствия минимуму по ст. 81 СК РФ. Внутреннее enum-поле.",
        required=True,
    ))
    fields.append(F(
        name="minimum_compliance_note",
        type="string",
        presentation="fact",
        display_in_grid=True,
        display_priority=2,
        label="Соответствие минимуму (ст. 81 СК РФ)",
        description=LiteralScalarString(
            "Обоснование оценки соответствия минимуму.\n"
            'Fallback: "Данные не определены" / "Не удалось определить".\n'
        ),
        required=True,
    ))
    fields.append(F(
        name="payment_frequency_status",
        type="string",
        presentation="signal",
        risk_weight="medium",
        allowed_values=["defined", "not_defined"],
        display_in_grid=False,
        description="Статус указания периодичности выплаты. Внутреннее enum-поле.",
        required=True,
    ))
    fields.append(F(
        name="payment_frequency_details",
        type="string",
        presentation="fact",
        display_in_grid=True,
        display_priority=3,
        label="Периодичность выплаты",
        description=LiteralScalarString(
            "Периодичность выплаты алиментов.\n"
            'Fallback: "Данные не определены" / "Не удалось определить".\n'
        ),
        required=True,
    ))
    fields.append(F(
        name="number_of_children_status",
        type="string",
        presentation="signal",
        risk_weight="medium",
        allowed_values=["defined", "not_defined", "not_applicable"],
        display_in_grid=False,
        description="Статус указания числа детей. Внутреннее enum-поле.",
        required=True,
    ))
    fields.append(F(
        name="number_of_children_value",
        type="string",
        presentation="fact",
        display_in_grid=True,
        display_priority=4,
        label="Число детей",
        description=LiteralScalarString(
            "Число несовершеннолетних детей арабской цифрой.\n"
            'Fallback: "Данные не определены" / "Не удалось определить".\n'
        ),
        required=True,
    ))
    return fields


def fix_output_expectations(prompt):
    """Закрывает обрезанный блок output_expectations."""
    broken = "Технический формат JSON (value / confidence / location) задан отдельным контрактом —"
    fixed = (
        "Технический формат JSON (value / confidence / location) задан отдельным контрактом "
        "— соблюдай его, но не описывай здесь.\n"
        "</output_expectations>"
    )
    if broken in prompt and "</output_expectations>" not in prompt[prompt.find(broken):]:
        return prompt.replace(broken, fixed, 1)
    return prompt


yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096
yaml.indent(mapping=2, sequence=4, offset=2)

path = Path(FILE)
doc = yaml.load(path)

for c in (doc.get("checks_v8") or doc.get("checks") or []):
    if c.get("id") == CHECK_ID:
        ext = c["extraction"]
        old_prompt = ext.get("llm_prompt_extraction") or ""
        new_prompt = fix_output_expectations(old_prompt)
        if new_prompt != old_prompt:
            ext["llm_prompt_extraction"] = LiteralScalarString(new_prompt)
            print(f"  ✓ {CHECK_ID}: output_expectations исправлен")

        # Пересобираем extraction в правильном порядке ключей
        new_ext = CommentedMap()
        new_ext["enabled"] = True
        new_ext["mode"] = "hybrid"
        new_ext["llm_max_tokens"] = 900
        new_ext["compact_output"] = False
        new_ext["presence_signal"] = CommentedMap([
            ("field", "amount_minimum_compliance_check_presence"),
            ("present_values", ["present"]),
            ("missing_values", ["missing"]),
            ("unclear_values", ["unclear"]),
        ])
        new_ext["llm_prompt_extraction"] = LiteralScalarString(new_prompt)
        new_ext["fields"] = build_fields()
        new_ext["store_payload"] = True
        c["extraction"] = new_ext
        print(f"  ✓ {CHECK_ID}: fields восстановлены ({len(new_ext['fields'])} полей)")
        break
else:
    print(f"  ✗ {CHECK_ID} не найден")
    raise SystemExit(1)

yaml.dump(doc, path)
print(f"✓ Сохранено: {FILE}")
