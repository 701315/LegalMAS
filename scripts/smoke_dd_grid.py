"""
Smoke-тест DD Grid вывода для реформированной doc-type инструкции.

Симулирует полный extraction pipeline:
  1. Загружает YAML-инструкцию через DocTypeCheckLoader
  2. Для каждого check запускает ExtractionLLMDetector на тестовом тексте
  3. Строит result_semantics (display_text, presentation, label)
  4. Выводит DD Grid-подобную таблицу как увидит юрист

Запуск:
  cd /home/vladi/projects/LegalMAS
  python3 scripts/smoke_dd_grid.py --doc-type contract_1.1_general_sale
  python3 scripts/smoke_dd_grid.py --doc-type contract_1.1_general_sale --dry-run
  python3 scripts/smoke_dd_grid.py --doc-type contract_1.1_general_sale --checks parties_and_authority
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

# ── Пути проекта ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

# ── Импорты из проекта ────────────────────────────────────────────────────────
from engine.doc_type_checks.loader import DocTypeCheckLoader
from engine.detectors.extraction_llm_detector import ExtractionLLMDetector
from engine.llm.client import LLMClient
from engine.checks.result_semantics import (
    _get_field_presentation,
    _get_field_label,
    _is_not_found_value,
    _extract_scalar_value,
    _build_factual_display_text,
)
from engine.extraction_normalization import normalize_to_allowed_values


# ─────────────────────────────────────────────────────────────────────────────
# КОНСТАНТЫ
# ─────────────────────────────────────────────────────────────────────────────

SEPARATOR  = "─" * 80
DOUBLE_SEP = "═" * 80

PRESENTATION_EMOJI = {
    "fact":       "📋",
    "signal":     "🔵",
    "diagnostic": "🔧",
    "summary":    "⭐",
}

STATUS_EMOJI = {
    "defined":     "✅",
    "not_defined": "❌",
    "yes":         "✅",
    "no":          "❌",
    "unclear":     "⚠️",
}


# ─────────────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────────────────────────────────────

def build_mock_structured_data(
    check: Any,
    llm_fields: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Собрать structured_data из LLM-ответа по контракту extraction.fields.
    Гарантирует запись для каждого поля из schema.
    """
    extraction = getattr(check, "extraction", None)
    if not extraction:
        return {}

    structured: dict[str, Any] = {}

    for field_cfg in extraction.fields or []:
        name = field_cfg.name
        llm_payload = llm_fields.get(name)

        if llm_payload:
            value = llm_payload.get("value")
            confidence = float(llm_payload.get("confidence", 0.0))

            # Нормализуем allowed_values
            if field_cfg.allowed_values and value is not None:
                normalized = normalize_to_allowed_values(value, field_cfg.allowed_values)
                value = normalized if normalized is not None else value

            structured[name] = {
                "value":      value,
                "source":     "llm",
                "confidence": confidence,
                "found":      not _is_not_found_value(value),
            }
        else:
            structured[name] = {
                "value":      None,
                "source":     "none",
                "confidence": 0.0,
                "found":      False,
            }

    return structured


def render_dd_grid_cell(
    check: Any,
    structured_data: dict[str, Any],
) -> str:
    """Primary display_text как в DD Grid."""
    return _build_factual_display_text(
        check=check,
        ui_mode=None,
        structured_data=structured_data,
    ) or "(нет данных для отображения)"


def render_field_table(
    check: Any,
    structured_data: dict[str, Any],
) -> list[str]:
    """Полная таблица всех полей extraction."""
    extraction = getattr(check, "extraction", None)
    if not extraction:
        return []

    lines = []
    for field_cfg in extraction.fields or []:
        name         = field_cfg.name
        presentation = _get_field_presentation(check, name)
        label        = _get_field_label(check, name)
        emoji        = PRESENTATION_EMOJI.get(presentation, "❓")

        payload    = structured_data.get(name, {})
        raw_value  = _extract_scalar_value(payload)
        confidence = payload.get("confidence", 0.0)
        source     = payload.get("source", "none")

        is_null    = _is_not_found_value(raw_value)
        value_str  = str(raw_value) if not is_null else "—"

        # Добавляем emoji для signal-полей
        if presentation == "signal" and not is_null:
            status_emoji = STATUS_EMOJI.get(str(raw_value).lower(), "")
            value_str = f"{status_emoji} {value_str}" if status_emoji else value_str

        conf_str = f"{confidence:.0%}" if confidence else "—"

        lines.append(
            f"  {emoji} [{presentation:10s}] "
            f"{label:<35s} │ "
            f"{value_str:<35s} │ "
            f"conf={conf_str} src={source}"
        )

    return lines


def print_check_result(
    check: Any,
    structured_data: dict[str, Any],
    llm_raw_response: str | None,
) -> None:
    """Вывести полный результат одного check."""
    check_id   = getattr(check, "id", "?")
    check_name = getattr(check, "name", "?")
    severity   = getattr(check, "severity", "?")

    # ── Заголовок check ───────────────────────────────────────────────────────
    print(f"\n{SEPARATOR}")
    print(f"  CHECK: {check_name}")
    print(f"  id={check_id}  severity={severity}")
    print(SEPARATOR)

    # ── DD Grid cell ──────────────────────────────────────────────────────────
    cell_text = render_dd_grid_cell(check, structured_data)
    print(f"\n  📌 DD Grid (primary display):")
    print(f"  ┌{'─' * 62}┐")
    for line in textwrap.wrap(cell_text, width=60):
        print(f"  │ {line:<60s} │")
    print(f"  └{'─' * 62}┘")

    # ── Полная таблица полей ──────────────────────────────────────────────────
    print(f"\n  📊 Все поля extraction:")
    print(f"  {'─' * 100}")
    print(
        f"  {'':2s} {'Роль':<12s} "
        f"{'Label':<35s} │ "
        f"{'Значение':<35s} │ "
        f"conf/src"
    )
    print(f"  {'─' * 100}")
    for field_line in render_field_table(check, structured_data):
        print(field_line)

    # ── Статистика ────────────────────────────────────────────────────────────
    extraction   = getattr(check, "extraction", None)
    total_fields = len(extraction.fields) if extraction else 0

    found_facts = sum(
        1 for f in (extraction.fields or [])
        if _get_field_presentation(check, f.name) == "fact"
        and not _is_not_found_value(
            _extract_scalar_value(structured_data.get(f.name, {}))
        )
    )
    found_signals = sum(
        1 for f in (extraction.fields or [])
        if _get_field_presentation(check, f.name) == "signal"
        and not _is_not_found_value(
            _extract_scalar_value(structured_data.get(f.name, {}))
        )
    )
    null_facts = sum(
        1 for f in (extraction.fields or [])
        if _get_field_presentation(check, f.name) == "fact"
        and _is_not_found_value(
            _extract_scalar_value(structured_data.get(f.name, {}))
        )
    )

    print(
        f"\n  📈 Статистика: "
        f"полей всего={total_fields} │ "
        f"facts найдено={found_facts} │ "
        f"facts пусто={null_facts} │ "
        f"signals найдено={found_signals}"
    )

    # ── Предупреждения ────────────────────────────────────────────────────────
    if null_facts > 0:
        print(f"\n  ⚠️  Пустые fact-поля (не попадут в DD Grid):")
        for f in (extraction.fields or []):
            if _get_field_presentation(check, f.name) == "fact":
                val = _extract_scalar_value(structured_data.get(f.name, {}))
                if _is_not_found_value(val):
                    label = _get_field_label(check, f.name)
                    print(f"       — {label} ({f.name})")

    # ── Проверка extraction prompt ────────────────────────────────────────────
    ext = getattr(check, "extraction", None)
    has_custom_prompt = bool(
        ext
        and getattr(ext, "llm_prompt_extraction", None)
        and ext.llm_prompt_extraction.strip()
    )
    prompt_status = "✅ custom llm_prompt_extraction" if has_custom_prompt else "⚠️  fallback (нет llm_prompt_extraction)"
    print(f"\n  🤖 Extraction prompt: {prompt_status}")

    # ── Raw LLM response ──────────────────────────────────────────────────────
    if llm_raw_response and llm_raw_response != "(dry_run — LLM не вызывался)":
        print(f"\n  🤖 Raw LLM response (первые 600 символов):")
        preview = llm_raw_response[:600]
        for line in preview.split("\n"):
            print(f"    {line}")
    elif llm_raw_response:
        print(f"\n  🤖 {llm_raw_response}")


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA AUDIT (без LLM)
# ─────────────────────────────────────────────────────────────────────────────

def run_schema_audit(checks: list[Any]) -> None:
    """
    Аудит schema без LLM.
    Проверяет presentation, label, allowed_values.
    """
    print(f"\n{DOUBLE_SEP}")
    print(f"  🔍 SCHEMA AUDIT (без LLM)")
    print(DOUBLE_SEP)

    total_issues = 0

    for check in checks:
        extraction = getattr(check, "extraction", None)
        if not extraction or not extraction.enabled:
            continue

        check_issues = []

        # Проверяем llm_prompt_extraction
        has_custom = bool(
            getattr(extraction, "llm_prompt_extraction", None)
            and extraction.llm_prompt_extraction.strip()
        )
        if not has_custom:
            check_issues.append("❌ нет llm_prompt_extraction (fallback режим)")

        # Проверяем поля
        for field_cfg in extraction.fields or []:
            presentation = getattr(field_cfg, "presentation", None)
            label        = getattr(field_cfg, "label", None)
            name         = field_cfg.name

            if not presentation:
                check_issues.append(f"❌ нет presentation: {name}")

            if presentation == "fact" and not label:
                check_issues.append(f"❌ fact без label: {name}")

            if presentation == "summary":
                check_issues.append(f"⚠️  presentation=summary (нежелательно): {name}")

        if check_issues:
            print(f"\n  [{check.id}]")
            for issue in check_issues:
                print(f"    {issue}")
            total_issues += len(check_issues)
        else:
            print(f"  ✅ [{check.id}] — schema OK")

    print(f"\n  Итого проблем: {total_issues}")
    print(DOUBLE_SEP)


# ─────────────────────────────────────────────────────────────────────────────
# ОСНОВНОЙ RUNNER
# ─────────────────────────────────────────────────────────────────────────────

class DDGridSmokeRunner:

    def __init__(
        self,
        doc_type: str,
        text: str,
        checks_filter: list[str] | None = None,
        dry_run: bool = False,
    ) -> None:
        self.doc_type       = doc_type
        self.text           = text
        self.checks_filter  = checks_filter
        self.dry_run        = dry_run

        self.loader    = DocTypeCheckLoader()
        self.llm_client = LLMClient()
        self.extractor  = ExtractionLLMDetector(self.llm_client)

    def run(self) -> dict[str, Any]:
        print(f"\n{DOUBLE_SEP}")
        print(f"  🔍 DD GRID SMOKE TEST")
        print(f"  doc_type    : {self.doc_type}")
        print(f"  text length : {len(self.text)} chars")
        print(f"  llm available: {self.llm_client.is_available()}")
        print(f"  dry_run     : {self.dry_run}")
        print(DOUBLE_SEP)

        # 1. Загружаем checks
        checks = self.loader.load_checks_for_doc(
            doc_type=self.doc_type,
            applicable_triggers=[],
        )

        if not checks:
            print(f"\n❌ Checks не загружены для doc_type={self.doc_type}")
            print("   Проверь путь к YAML и наличие checks_v8.")
            return {"status": "no_checks"}

        extraction_checks = [
            c for c in checks
            if getattr(c, "extraction", None)
            and getattr(c.extraction, "enabled", False)
        ]

        if self.checks_filter:
            extraction_checks = [
                c for c in extraction_checks
                if c.id in self.checks_filter
            ]

        print(f"\n  Загружено checks      : {len(checks)}")
        print(f"  С extraction enabled  : {len(extraction_checks)}")
        if self.checks_filter:
            print(f"  После фильтра         : {[c.id for c in extraction_checks]}")

        # 2. Schema audit всегда
        run_schema_audit(extraction_checks)

        if self.dry_run:
            print("\n  ℹ️  dry-run режим — LLM не вызывается.")
            return {"status": "dry_run", "checks": [c.id for c in extraction_checks]}

        # 3. Extraction для каждого check
        summary: dict[str, Any] = {
            "doc_type":                self.doc_type,
            "checks_total":            len(checks),
            "checks_with_extraction":  len(extraction_checks),
            "results":                 {},
        }

        for check in extraction_checks:
            print(f"\n  ⏳ Запуск extraction: {check.id}...")

            if not self.llm_client.is_available():
                print(f"  ⚠️  LLM недоступен — пропускаем {check.id}")
                continue

            try:
                llm_fields   = self.extractor.extract(check, self.text)
                raw_response = json.dumps(
                    {"fields": llm_fields},
                    ensure_ascii=False,
                    indent=2,
                )
            except Exception as e:
                print(f"  ❌ Ошибка extraction для {check.id}: {e}")
                llm_fields   = {}
                raw_response = f"ERROR: {e}"

            structured_data = build_mock_structured_data(check, llm_fields)

            print_check_result(
                check=check,
                structured_data=structured_data,
                llm_raw_response=raw_response,
            )

            summary["results"][check.id] = {
                "fields_total": len(check.extraction.fields),
                "fields_found": sum(
                    1 for f in check.extraction.fields
                    if not _is_not_found_value(
                        _extract_scalar_value(structured_data.get(f.name, {}))
                    )
                ),
                "display_text": render_dd_grid_cell(check, structured_data),
            }

        self._print_summary(summary)
        return summary

    def _print_summary(self, summary: dict[str, Any]) -> None:
        print(f"\n{DOUBLE_SEP}")
        print(f"  📊 ИТОГОВЫЙ SUMMARY")
        print(DOUBLE_SEP)
        print(f"\n  doc_type: {summary['doc_type']}")
        print(f"  checks всего           : {summary['checks_total']}")
        print(f"  checks с extraction    : {summary['checks_with_extraction']}")

        if not summary.get("results"):
            print("\n  (нет результатов)")
            return

        print(f"\n  {'Check ID':<45s} │ {'Полей':<6s} │ {'Найдено':<8s} │ DD Grid display")
        print(f"  {'─' * 115}")

        for check_id, result in summary["results"].items():
            total   = result["fields_total"]
            found   = result["fields_found"]
            display = result["display_text"]
            display = display[:50] + "…" if len(display) > 50 else display
            fill    = "🟢" if found > 0 else "🔴"
            print(
                f"  {fill} {check_id:<43s} │ "
                f"{total:<6d} │ "
                f"{found:<8d} │ "
                f"{display}"
            )

        print(f"\n{DOUBLE_SEP}\n")


# ─────────────────────────────────────────────────────────────────────────────
# ТЕСТОВЫЙ ТЕКСТ
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_TEST_TEXT = """
ДОГОВОР КУПЛИ-ПРОДАЖИ № 12/2025

г. Москва                                                    «15» января 2025 г.

ООО «Технолайн», ИНН 7712345678, ОГРН 1027700123456, юридический адрес:
125009, г. Москва, ул. Тверская, д. 1, именуемое в дальнейшем «Продавец»,
в лице Генерального директора Иванова Александра Петровича,
действующего на основании Устава,

и

ИП Петров Сергей Николаевич, ИНН 771234567890, адрес регистрации:
115093, г. Москва, ул. Садовая, д. 5, кв. 12, именуемый в дальнейшем
«Покупатель», действующий на основании свидетельства ОГРНИП 312774600123456,

заключили настоящий договор о нижеследующем:

1. ПРЕДМЕТ ДОГОВОРА

1.1. Продавец обязуется передать в собственность Покупателю промышленный
холодильник марки «АрктикПро 500», заводской номер ХП-2025-0012 (далее —
Товар), в количестве 2 (двух) единиц, а Покупатель обязуется принять и
оплатить Товар на условиях настоящего Договора.

1.2. Качество Товара должно соответствовать ГОСТ 26678-2020.

2. ЦЕНА И ПОРЯДОК РАСЧЕТОВ

2.1. Цена одной единицы Товара составляет 450 000 (четыреста пятьдесят тысяч)
рублей, НДС не облагается. Общая стоимость Товара — 900 000 (девятьсот тысяч)
рублей.

2.2. Покупатель производит оплату в следующем порядке:
— 50% от общей стоимости (450 000 рублей) — не позднее 3 (трёх) рабочих дней
  с даты подписания настоящего Договора (предоплата);
— оставшиеся 50% (450 000 рублей) — не позднее 5 (пяти) рабочих дней с даты
  подписания акта приёма-передачи.

2.3. В случае просрочки оплаты Покупатель уплачивает пени в размере 0,1% от
суммы задолженности за каждый день просрочки.

3. ПЕРЕДАЧА ТОВАРА

3.1. Продавец обязуется передать Товар Покупателю не позднее 20 (двадцати)
рабочих дней с момента получения предоплаты.

3.2. Передача Товара осуществляется на складе Продавца по адресу: г. Москва,
Промышленный проезд, д. 8. Доставка до склада Покупателя возможна за
дополнительную плату.

3.3. При передаче Товара стороны подписывают акт приёма-передачи. Одновременно
Продавец передаёт Покупателю: технический паспорт, инструкцию по эксплуатации,
сертификат соответствия ГОСТ 26678-2020.

4. ПЕРЕХОД ПРАВА СОБСТВЕННОСТИ И РИСКА

4.1. Право собственности на Товар переходит к Покупателю с момента подписания
акта приёма-передачи.

4.2. Риск случайной гибели и случайного повреждения Товара переходит к
Покупателю с момента передачи Товара.

4.3. До полной оплаты Товара право собственности на Товар сохраняется за
Продавцом.

5. ГАРАНТИЯ И КАЧЕСТВО

5.1. Продавец гарантирует, что Товар соответствует ГОСТ 26678-2020 и свободен
от дефектов производства.

5.2. Гарантийный срок на Товар составляет 12 (двенадцать) месяцев с даты
подписания акта приёма-передачи.

5.3. Покупатель обязан осмотреть Товар в течение 3 (трёх) рабочих дней с
даты получения. Претензии по явным недостаткам предъявляются в течение
указанного срока в письменной форме.

5.4. Претензии по скрытым недостаткам предъявляются в течение гарантийного
срока.

6. ЗАВЕРЕНИЯ ПРОДАВЦА

6.1. Продавец гарантирует, что Товар принадлежит ему на праве собственности,
свободен от прав третьих лиц, не заложен, не находится под арестом и иными
обременениями.

7. ОТВЕТСТВЕННОСТЬ И РАСТОРЖЕНИЕ

7.1. В случае просрочки передачи Товара Продавец уплачивает пени в размере
0,1% от стоимости непереданного Товара за каждый день просрочки.

7.2. В случае существенного нарушения условий Договора любая из сторон вправе
расторгнуть его в одностороннем порядке, направив письменное уведомление за
10 (десять) рабочих дней.

7.3. При расторжении Договора по инициативе Продавца он возвращает Покупателю
уплаченные денежные средства в полном объёме в течение 5 (пяти) рабочих дней.

7.4. Стороны освобождаются от ответственности в случае форс-мажорных
обстоятельств: стихийных бедствий, военных действий, решений органов
государственной власти и иных обстоятельств непреодолимой силы.

8. РАЗРЕШЕНИЕ СПОРОВ

8.1. Все споры разрешаются путём переговоров. В случае недостижения соглашения
сторона направляет претензию, срок ответа на которую составляет 15 (пятнадцать)
рабочих дней.

8.2. Неурегулированные споры передаются на рассмотрение Арбитражного суда
г. Москвы.

8.3. К настоящему Договору применяется право Российской Федерации.

9. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ

9.1. Договор вступает в силу с момента подписания и действует до полного
исполнения сторонами своих обязательств.

Подписи сторон:

Продавец:                              Покупатель:
ООО «Технолайн»                        ИП Петров С.Н.
/Иванов А.П./                          /Петров С.Н./
"""


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-тест DD Grid вывода для doc-type инструкции."
    )
    parser.add_argument(
        "--doc-type",
        default="contract_1.1_general_sale",
        help="Тип документа (имя YAML-файла без .yaml)",
    )
    parser.add_argument(
        "--text-file",
        help="Путь к текстовому файлу договора",
    )
    parser.add_argument(
        "--inline-text",
        help="Текст договора прямо в аргументе",
    )
    parser.add_argument(
        "--checks",
        nargs="*",
        help="Фильтр по check id",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только schema-аудит без LLM",
    )
    parser.add_argument(
        "--save-json",
        help="Путь для сохранения JSON-результата",
    )

    args = parser.parse_args()

    # Определяем текст
    if args.text_file:
        text_path = Path(args.text_file)
        if not text_path.exists():
            print(f"❌ Файл не найден: {text_path}")
            sys.exit(1)
        text = text_path.read_text(encoding="utf-8")
    elif args.inline_text:
        text = args.inline_text
    else:
        print("ℹ️  Текст не передан — используется встроенный тестовый договор.")
        text = DEFAULT_TEST_TEXT

    runner = DDGridSmokeRunner(
        doc_type=args.doc_type,
        text=text,
        checks_filter=args.checks,
        dry_run=args.dry_run,
    )

    result = runner.run()

    if args.save_json:
        output_path = Path(args.save_json)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  💾 JSON сохранён: {output_path}")


if __name__ == "__main__":
    main()
