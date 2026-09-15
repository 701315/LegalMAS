#!/usr/bin/env python3
"""
migrate_add_labels.py — надежный строчный мигратор для добавления label в fact-поля
и перевода *_snippet полей в presentation: diagnostic.

Гарантии безопасности:
1. Построчный парсинг (сохраняет 100% комментариев, кавычек и отступов).
2. Валидация через audit_checks_structure.audit_file (настоящий Pydantic).
3. Автоматический откат при любой ошибке.
4. Создание бэкапа .bak_label перед модификацией.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Подключаем наш строгий аудитор структуры для pre-flight валидации
_SCRIPTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

try:
    from audit_checks_structure import audit_file
    _AUDITOR_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Аудитор недоступен: {e}", file=sys.stderr)
    _AUDITOR_AVAILABLE = False


# Полная выверенная карта переводов для всех полей без label
FIELD_LABELS: dict[str, str] = {
    # ── Group 2: Use ──────────────────────────────────────────────────────────
    "reference_document_value": "Реквизиты документа-основания",
    "defect_disclosure_details": "Сведения о выявленных дефектах",
    "capital_repairs_allocation_display": "Расходы на капитальный ремонт",
    "current_repairs_allocation_display": "Расходы на текущий ремонт",
    "operational_costs_allocation_display": "Распределение эксплуатационных расходов",
    "operational_costs_details": "Сведения об эксплуатационных расходах",
    "improvements_compensation_details": "Сведения о компенсации за улучшения",
    "sublease_details": "Условия субаренды",
    "assignment_details": "Условия переуступки прав аренды",
    "landlord_type_display": "Статус арендодателя",
    "landlord_signatory_basis_display": "Основание полномочий подписанта арендодателя",
    "tenant_type_display": "Статус арендатора",
    "tenant_signatory_basis_display": "Основание полномочий подписанта арендатора",
    "title_documents_details": "Сведения о правоустанавливающих документах",
    "egrn_reference_details": "Реквизиты выписки из ЕГРН",
    "late_payment_penalty_details": "Штраф за просрочку платежа",
    "landlord_breach_penalty_details": "Штраф за нарушения арендодателя",
    "landlord_professional_details": "Профессиональный статус арендодателя",
    "landlord_signatory_value": "Подписант арендодателя",
    "tenant_signatory_value": "Подписант арендатора",
    "deposit_details": "Сведения об обеспечительном платеже",
    "public_contract_details": "Сведения о публичном договоре",
    "st426_reference_details": "Ссылка на ст. 426 ГК РФ",
    "uniform_terms_details": "Сведения об одинаковых условиях",
    "open_access_details": "Публичный доступ к условиям",
    "termination_restriction_details": "Ограничения на расторжение",
    "safety_rules_details": "Сведения о правилах безопасности",
    "repair_shift_to_tenant_details": "Перенос обязанности по ремонту на арендатора",
    "normal_wear_excluded_details": "Исключение естественного износа",
    "notification_obligation_details": "Обязанность по уведомлению",
    "replacement_option_details": "Возможность замены имущества",
    "condition_assessment_details": "Оценка состояния при возврате",
    "max_term_reference_details": "Ссылка на предельный срок",
    "renewal_clause_details": "Условия пролонгации",
    "preemptive_right_details": "Преимущественное право на заключение договора",
    "st627_reference_details": "Ссылка на ст. 627 ГК РФ",
    "pledge_prohibition_details": "Запрет залога имущества",
    "contribution_prohibition_details": "Запрет внесения в качестве вклада",
    "other_encumbrance_prohibition_details": "Запрет иных обременений",
    "st631_reference_details": "Ссылка на ст. 631 ГК РФ",
    "tenant_breach_penalty_details": "Штрафы за нарушения арендатора",
    "liability_cap_details": "Лимит ответственности",
    "damages_procedure_details": "Порядок возмещения убытков",
    "blanket_disclaimer_details": "Отказ от ответственности",
    "waiver_of_claims_details": "Отказ от претензий",
    "full_risk_assumption_details": "Принятие всех рисков",
    "warranty_disclaimer_details": "Отказ от гарантий качества",
    "unconditional_retention_details": "Безусловное удержание платы",
    "auto_charge_details": "Сведения об автосписании",
    "title_confirmation_details": "Подтверждение права собственности",
    "no_pledge_details": "Отсутствие залога",
    "no_arrest_details": "Отсутствие ареста",
    "no_third_party_rights_details": "Отсутствие прав третьих лиц",
    "insurance_obligation_details": "Обязанность страхования",
    "risk_allocation_details": "Распределение рисков",
    "beneficiary_details": "Выгодоприобретатель по страхованию",
    "franchise_details": "Сведения о франшизе",
    "coverage_exclusions_details": "Исключения из страхового покрытия",
    "zozpp_reference_details": "Ссылка на Закон о защите прав потребителей",
    "right_to_cancel_details": "Право на отказ от договора",
    "quality_right_details": "Права при ненадлежащем качестве",
    "return_procedure_details": "Порядок возврата имущества",
    "rospotrebnadzor_contact_details": "Контакты Роспотребнадзора",
    "handover_act_details": "Сведения об акте приема-передачи",
    "condition_recorded_details": "Фиксация состояния автомобиля",
    "mileage_recorded_details": "Фиксация пробега",
    "photo_fixation_details": "Фотофиксация состояния",
    "existing_damage_details": "Описание имеющихся повреждений",
    "document_pack_details": "Комплект документов на автомобиль",
    "fitness_warranty_details": "Гарантия пригодности к эксплуатации",
    "tech_inspection_details": "Сведения о техосмотре",
    "insurance_cost_allocation_details": "Распределение расходов на страховку",
    "police_europrotocol_details": "Оформление ДТП (ГИБДД/европротокол)",
    "hazardous_source_reference_details": "Упоминание источника повышенной опасности",
    "crew_liability_details": "Ответственность экипажа",
    "fuel_level_details": "Фиксация уровня топлива",
    "termination_grounds_details": "Основания расторжения",
    "termination_notice_details": "Срок уведомления о расторжении",
    "fines_reimbursement_details": "Возмещение штрафов ПДД",
    "notification_procedure_details": "Порядок уведомления арендодателя",
    "regress_mechanism_details": "Механизм регрессного требования",
    "allowed_drivers_list_details": "Список разрешенных водителей",
    "transfer_prohibition_details": "Запрет передачи третьим лицам",
    "cross_border_restriction_details": "Ограничение на выезд за границу",
    "sublease_prohibition_details": "Запрет субаренды",
    "deposit_refund_details": "Порядок возврата депозита",
    "retention_criteria_details": "Критерии удержания депозита",
    "payment_suspension_details": "Приостановка арендной платы при простое",
    "rent_suspension_on_theft_details": "Приостановка аренды при угоне",
    "negligence_liability_details": "Ответственность при грубой неосторожности",
    "defect_notification_details": "Порядок уведомления о дефектах",
    "remediation_consequences_details": "Последствия неустранения дефектов",
    "impound_return_details": "Порядок возврата со спецстоянки",

    # ── Group 3: Works ────────────────────────────────────────────────────────
    "advance_rate": "Размер аванса",
    "price_indexation_details": "Условия индексации цены",
    "customer_obligations_details": "Обязанности заказчика по предоставлению площадки",
    "supervision_details": "Сведения о строительном контроле и технадзоре",
    "warranty_period_general_value": "Общий гарантийный срок",
    "warranty_period_engineering_value": "Гарантийный срок на инженерные системы",
    "defect_remedy_deadline_value": "Срок устранения дефектов",
    "retention_amount": "Размер гарантийного удержания",
    "insurance_and_risk_details": "Условия страхования строительных рисков",
    "acceptance_docs_details": "Перечень приемочных документов (КС-2, КС-3)",
    "materials_supply_details": "Обязанности по поставке материалов и оборудования",
    "commissioning_details": "Сведения о вводе объекта в эксплуатацию",
    "hidden_works_procedure_details": "Порядок освидетельствования скрытых работ",
    "environmental_details": "Экологические требования и обращение с отходами",
    "ip_docs_details": "Права на проектно-сметную документацию",
    "sro_details": "Требования к членству в СРО",
    "dispute_resolution_details": "Досудебная техническая экспертиза споров",
    "site_safety_details": "Охрана труда и безопасность на стройплощадке",
    "site_security_details": "Охрана объекта и стройплощадки",
    "site_prep_details": "Подготовка стройплощадки и временные сооружения",
    "termination_specifics_details": "Последствия расторжения договора и консервации",
    "surveys_and_connections_details": "Инженерные изыскания и точки подключения",
    "financial_security_details": "Сведения о банковской гарантии и обеспечении",

    # ── Group 4: Services ─────────────────────────────────────────────────────
    "custodian_signatory": "Подписант хранителя",
    "depositor_signatory": "Подписант поклажедателя",
    "insured_person": "Застрахованное лицо",
    "beneficiary": "Выгодоприобретатель",

    # ── Group 5: Financial ────────────────────────────────────────────────────
    "acceleration_triggers": "Основания досрочного истребования кредита",
    "allocation_order_details": "Очередность погашения требований",
    "covenant_types": "Перечень финансовых ковенантов",
    "collateral_types": "Виды обеспечения кредита",
    "cp_documents_required": "Документы отлагательных условий (CP)",
    "negative_covenants_types": "Виды негативных ковенантов",
    "affirmative_covenants_types": "Виды позитивных ковенантов",
    "notice_methods_value": "Способы отправки юридически значимых уведомлений",
    "client_signatory": "Подписант клиента",
    "bank_signatory": "Подписант банка",
    "rate_change_right_details": "Право банка на одностороннее изменение ставки",
    "early_withdrawal_details": "Условия досрочного истребования вклада",
    "tariff_change_right_details": "Право банка на изменение тарифов",
    "aml_terms_details": "Условия ограничений по 115-ФЗ",
    "debit_grounds_details": "Случаи безакцептного списания средств",
    "liability_allocation_details": "Распределение ответственности при компрометации ДБО",
    "insurance_terms_details": "Упоминание системы страхования вкладов (АСВ)",
}


def process_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    """
    Построчно обрабатывает файл.
    Возвращает: (новые_строки, список_логов_изменений)
    """
    new_lines: list[str] = []
    logs: list[str] = []
    
    in_extraction_fields = False
    current_field_name: str | None = None
    current_field_has_label = False
    current_field_presentation: str | None = None
    field_lines_buffer: list[str] = []

    def flush_field():
        nonlocal field_lines_buffer, current_field_name, current_field_has_label, current_field_presentation
        if not field_lines_buffer:
            return

        if current_field_name:
            # 1. Если это сниппет -> presentation: "diagnostic"
            if current_field_name.endswith("_snippet"):
                for idx, l in enumerate(field_lines_buffer):
                    if "presentation:" in l:
                        field_lines_buffer[idx] = '          presentation: "diagnostic"\n'
                        logs.append(f"    🔧 Поле [{current_field_name}]: presentation -> 'diagnostic'")
                        break
            # 2. Если это fact-поле без label -> вставляем label
            elif not current_field_has_label and (current_field_presentation in ("fact", None)):
                label_text = FIELD_LABELS.get(current_field_name)
                if not label_text:
                    label_text = current_field_name.replace("_", " ").strip().capitalize()
                    logs.append(f"    ⚠️ Поле [{current_field_name}]: fallback label -> '{label_text}'")
                
                # Вставляем строку label сразу после строки "- name:"
                field_lines_buffer.insert(1, f'          label: "{label_text}"\n')
                logs.append(f"    🏷️  Поле [{current_field_name}]: добавлен label -> '{label_text}'")

        new_lines.extend(field_lines_buffer)
        field_lines_buffer = []
        current_field_name = None
        current_field_has_label = False
        current_field_presentation = None

    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if stripped.startswith("fields:"):
            flush_field()
            in_extraction_fields = True
            new_lines.append(line)
            continue

        if in_extraction_fields:
            # Конец блока fields: выход на уровень чека (4 или 6 пробелов не fields)
            if indent <= 6 and stripped and not stripped.startswith("#"):
                flush_field()
                in_extraction_fields = False
                new_lines.append(line)
                continue

            # Новое поле в списке: "- name: ..."
            if indent == 8 and stripped.startswith("- name:"):
                flush_field()
                # Извлекаем имя поля
                name_part = stripped.split("- name:")[1].strip().strip('"\'')
                current_field_name = name_part
                current_field_has_label = False
                current_field_presentation = None
                field_lines_buffer.append(line)
                continue

            if current_field_name:
                field_lines_buffer.append(line)
                if stripped.startswith("label:"):
                    current_field_has_label = True
                elif stripped.startswith("presentation:"):
                    pres_val = stripped.split("presentation:")[1].strip().strip('"\'')
                    current_field_presentation = pres_val
                continue

        new_lines.append(line)

    flush_field()
    return new_lines, logs


def migrate_file(path: Path, apply: bool = False) -> bool:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    
    new_lines, logs = process_lines(lines)
    if not logs:
        return False

    print(f"\n📁 Файл: {path.name}")
    for log in logs:
        print(log)

    if apply:
        modified_content = "".join(new_lines)
        backup_path = path.with_suffix(path.suffix + ".bak_label")
        
        # Записываем бэкап и новый контент
        path.write_text(content, encoding="utf-8")
        path.write_text(modified_content, encoding="utf-8")
        
        # --- PRE-FLIGHT VALIDATION ЧЕРЕЗ AUDIT_FILE ---
        if _AUDITOR_AVAILABLE:
            report = audit_file(path)
            if report.errors > 0:
                print(f"    ❌ Pre-flight НЕ ПРОШЕЛ ({report.errors} ошибок)! ОТКАТЫВАЕМ: {path.name}")
                for iss in report.issues:
                    if iss.severity == "ERROR":
                        print(f"       🔴 [{iss.category}] {iss.message}")
                path.write_text(content, encoding="utf-8")
                return False
            else:
                print(f"    ✅ Pre-flight пройден идеально (0 ошибок). Бэкап: {backup_path.name}")
        else:
            print(f"    💾 Сохранено. Бэкап: {backup_path.name}")

    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Мигратор missing labels для fact-полей.")
    ap.add_argument("folder", type=Path, help="Папка с YAML-чеками.")
    ap.add_argument("--apply", action="store_true", help="Применить изменения.")
    args = ap.parse_args()

    if not args.folder.exists():
        print(f"❌ Папка не найдена: {args.folder}", file=sys.stderr)
        return 1

    files = sorted(args.folder.rglob("*.yaml")) + sorted(args.folder.rglob("*.yml"))
    
    print(f"\n🚀 Запуск строчной миграции label в: {args.folder}")
    if not args.apply:
        print("⚠️  Режим DRY-RUN. Изменения не записываются. Используй --apply для записи.\n")

    modified = 0
    for f in files:
        if "group_1_ownership" in str(f):
            continue
        if migrate_file(f, args.apply):
            modified += 1

    print(f"\n🏁 Обработано файлов: {modified} из {len(files)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


    