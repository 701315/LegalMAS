#!/usr/bin/env python3
"""
Fix A1: невалидные retrieval_profile в playbooks/document_types/ (группы 1–5).

42 замены (на живые/частичные профили) + 27 удалений (fallback).

READ-WRITE. Dry-run по умолчанию, --apply для применения.

Usage:
    python scripts/fix_a1_profiles.py            # dry-run
    python scripts/fix_a1_profiles.py --apply    # применить
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

BASE = Path("playbooks/document_types")

# Целевые профили — проверим, что они валидны
sys.path.insert(0, "src")
try:
    from engine.playbook.retrieval_profiles import ALL_PROFILES  # noqa: E402
    VALID_PROFILES = set(ALL_PROFILES.keys())
except Exception as e:
    print(f"❌ не удалось импортировать ALL_PROFILES: {e}")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════
# PER-CHECK FIX MAP
# ═══════════════════════════════════════════════════════════════════════
#
# Ключ:   (relative_path_from_BASE, check_id)
# Значение: (old_profile_value, new_profile_value_or_None)
#
# None → удалить ключ retrieval_profile целиком.

FIXES: dict[tuple[str, str], tuple[str, str | None]] = {
    # ─────────── generic_check: 25 замен ───────────
    ("group_1_ownership/contract_1.11_shares_sale.yaml", "closing_conditions_and_payment_mechanics_check"): ("generic_check", "title_transfer_check"),
    ("group_1_ownership/contract_1.11_shares_sale.yaml", "sanctions_and_beneficial_ownership_check"): ("generic_check", "sanctions_compliance_check"),
    ("group_1_ownership/contract_1.11_shares_sale.yaml", "post_closing_obligations_check"): ("generic_check", "non_compete_check"),
    ("group_1_ownership/contract_1.11_shares_sale.yaml", "termination_and_disputes_check"): ("generic_check", "termination_check"),
    ("group_1_ownership/contract_1.3_goods_supply.yaml", "payment_transfer_of_risk_cluster"): ("generic_check", "payment_terms_check"),
    ("group_1_ownership/contract_1.3_goods_supply.yaml", "incoterms_extraction"): ("generic_check", "title_transfer_check"),
    ("group_1_ownership/contract_1.3_goods_supply.yaml", "liability_termination_cluster"): ("generic_check", "liability_cap_check"),
    ("group_1_ownership/contract_1.4_contract_farming.yaml", "risk_title_storage_cluster"): ("generic_check", "title_transfer_check"),
    ("group_1_ownership/contract_1.4_contract_farming.yaml", "liability_termination_cluster"): ("generic_check", "liability_cap_check"),
    ("group_1_ownership/contract_1.4_contract_farming.yaml", "general_provisions_cluster"): ("generic_check", "term_and_renewal_check"),
    ("group_1_ownership/contract_1.5_energy_supply.yaml", "general_provisions_cluster"): ("generic_check", "term_and_renewal_check"),
    ("group_1_ownership/contract_1.5_energy_supply.yaml", "unauthorized_consumption_check"): ("generic_check", "liability_cap_check"),
    ("group_1_ownership/contract_1.6_real_estate.yaml", "public_law_restrictions_check"): ("generic_check", "registration_check"),
    ("group_1_ownership/contract_1.6_real_estate.yaml", "asset_protection_taxes_check"): ("generic_check", "insurance_check"),
    ("group_1_ownership/contract_1.7_barter.yaml", "delivery_logistics_and_insurance"): ("generic_check", "insurance_check"),
    ("group_1_ownership/contract_1.7_barter.yaml", "termination_and_force_majeure"): ("generic_check", "force_majeure_check"),
    ("group_1_ownership/contract_1.8_donation.yaml", "encumbrances_bankruptcy_and_sham_risk"): ("generic_check", "security_check"),
    ("group_2_use/contract_2.1_lease.yaml", "lease_subject_extraction"): ("generic_check", "rent_check"),
    ("group_2_use/contract_2.2_rental.yaml", "rental_subject_and_consumer_purpose_extraction"): ("generic_check", "rent_check"),
    ("group_2_use/contract_2.3_vehicle_lease.yaml", "vehicle_lease_type_and_subject"): ("generic_check", "rent_check"),
    ("group_2_use/contract_2.3_vehicle_lease.yaml", "vehicle_usage_restrictions_check"): ("generic_check", "subletting_check"),
    ("group_2_use/contract_2.3_vehicle_lease.yaml", "vehicle_theft_and_hijacking_check"): ("generic_check", "insurance_check"),
    ("group_2_use/contract_2.3_vehicle_lease.yaml", "vehicle_warranty_and_hidden_defects_check"): ("generic_check", "warranties_check"),
    ("group_2_use/contract_2.3_vehicle_lease.yaml", "vehicle_maintenance_and_seasonal_check"): ("generic_check", "repair_maintenance_check"),
    ("group_3_works/contract_3.1_works_contract.yaml", "risk_allocation_before_acceptance"): ("generic_check", "acceptance_check"),
    
    # ─────────── generic_check: 12 удалений ───────────
    ("group_1_ownership/contract_1.4_contract_farming.yaml", "perennial_crops_risk_allocation"): ("generic_check", None),
    ("group_1_ownership/contract_1.5_energy_supply.yaml", "metering_cluster"): ("generic_check", None),
    ("group_1_ownership/contract_1.5_energy_supply.yaml", "industrial_consumer_protection_check"): ("generic_check", None),
    ("group_1_ownership/contract_1.5_energy_supply.yaml", "mcd_obligations_check"): ("generic_check", None),
    ("group_1_ownership/contract_1.7_barter.yaml", "sham_transaction_and_business_purpose"): ("generic_check", None),
    ("group_1_ownership/contract_1.7_barter.yaml", "vehicle_barter_specifics_check"): ("generic_check", None),
    ("group_1_ownership/contract_1.7_barter.yaml", "cross_border_barter_check"): ("generic_check", None),
    ("group_1_ownership/contract_1.9_annuity.yaml", "unconscionability_and_capacity_check"): ("generic_check", None),
    ("group_2_use/contract_2.2_rental.yaml", "public_contract_status_check"): ("generic_check", None),
    ("group_2_use/contract_2.3_vehicle_lease.yaml", "vehicle_downtime_and_replacement_check"): ("generic_check", None),
    ("group_2_use/contract_2.3_vehicle_lease.yaml", "vehicle_evacuation_and_impound_check"): ("generic_check", None),
    ("group_2_use/contract_2.3_vehicle_lease.yaml", "vehicle_driver_medical_check"): ("generic_check", None),
    
    # ─────────── compliance_check ───────────
    ("group_3_works/contract_3.1_works_contract.yaml", "hse_compliance_obligations"): ("compliance_check", None),
    ("group_4_services/contract_4.3_freight_forwarding.yaml", "dangerous_cargo_duties_check"): ("compliance_check", None),
    ("group_4_services/contract_4.3_freight_forwarding.yaml", "cmr_incoterms_reference"): ("compliance_check", None),
    ("group_5_financial/contract_5.3_factoring.yaml", "tax_risk_allocation"): ("compliance_check", "tax_check"),
    
    # ─────────── одиночные (28 невалидных) ───────────
    ("group_1_ownership/contract_1.12_accord.yaml", "creditor_refusal_and_default_remedy_check"): ("default_remedy_check", "event_of_default_check"),
    ("group_1_ownership/contract_1.12_accord.yaml", "no_pending_litigation_over_subject_check"): ("litigation_warranty_check", "warranties_check"),
    ("group_1_ownership/contract_1.12_accord.yaml", "agreement_form_and_notarization_check"): ("form_requirement_check", None),
    ("group_2_use/contract_2.1_lease.yaml", "risk_of_accidental_loss_check"): ("risk_allocation_check", "insurance_check"),
    ("group_2_use/contract_2.1_lease.yaml", "lease_reinstatement_obligations_check"): ("reinstatement_check", "repair_maintenance_check"),
    ("group_2_use/contract_2.1_lease.yaml", "lease_rent_free_period_check"): ("rent_free_check", "rent_check"),
    ("group_2_use/contract_2.2_rental.yaml", "consumer_rights_notification_check"): ("consumer_rights_check", None),
    ("group_2_use/contract_2.4_leasing.yaml", "leasing_early_buyout"): ("buyout_check", None),
    ("group_2_use/contract_2.4_leasing.yaml", "leasing_reporting_and_audit"): ("reporting_check", None),
    ("group_3_works/contract_3.1_works_contract.yaml", "permit_obligations_allocation"): ("regulatory_check", "registration_check"),
    ("group_3_works/contract_3.3_construction_contract.yaml", "environmental_obligations_check"): ("environmental_check", None),
    ("group_3_works/contract_3.3_construction_contract.yaml", "construction_site_safety"): ("safety_check", None),
    ("group_3_works/contract_3.3_construction_contract.yaml", "site_security_and_preservation"): ("site_security_check", "security_check"),
    ("group_3_works/contract_3.3_construction_contract.yaml", "temporary_facilities_and_site_prep"): ("site_prep_check", None),
    ("group_3_works/contract_3.3_construction_contract.yaml", "engineering_surveys_and_connections"): ("surveys_check", None),
    ("group_3_works/contract_3.3_construction_contract.yaml", "financial_security_and_guarantees"): ("financial_security_check", "security_check"),
    ("group_3_works/contract_3.4_design_survey.yaml", "additional_works_procedure"): ("additional_works_check", "scope_of_work_check"),
    ("group_3_works/contract_3.4_design_survey.yaml", "site_access_and_survey_conditions"): ("site_access_check", None),
    ("group_3_works/contract_3.4_design_survey.yaml", "design_coordination_and_clashes"): ("coordination_check", None),
    ("group_4_services/contract_4.3_freight_forwarding.yaml", "sla_kpi_terms"): ("quality_check", None),
    ("group_5_financial/contract_5.4_bank_deposit_account.yaml", "bank_deposit_account_subject_extraction"): ("deposit_subject_check", "payment_terms_check"),
    ("group_5_financial/contract_5.4_bank_deposit_account.yaml", "aml_blocking_check"): ("aml_compliance_check", "sanctions_compliance_check"),
    ("group_5_financial/contract_5.4_bank_deposit_account.yaml", "unauthorized_debit_check"): ("unauthorized_debit_check", None),
    ("group_5_financial/contract_5.4_bank_deposit_account.yaml", "dbs_security_check"): ("dbs_security_check", "cybersecurity_check"),
    ("group_5_financial/contract_5.4_bank_deposit_account.yaml", "overdraft_terms_check"): ("overdraft_check", "credit_facility_check"),
    ("group_5_financial/contract_5.4_bank_deposit_account.yaml", "deposit_insurance_coverage_check"): ("deposit_insurance_check", "insurance_check"),
    ("group_5_financial/contract_5.4_bank_deposit_account.yaml", "account_closure_and_termination_check"): ("account_closure_check", "termination_check"),
    ("group_5_financial/contract_5.4_bank_deposit_account.yaml", "payment_allocation_priority_check"): ("payment_allocation_check", "payment_terms_check"),
}


def find_check_bounds(text: str, check_id: str) -> tuple[int, int] | None:
    m = re.search(rf"^  - id: {re.escape(check_id)}\s*$", text, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    m2 = re.search(r"^  - id: ", text[m.end():], re.MULTILINE)
    end = m.end() + m2.start() if m2 else len(text)
    return start, end


def process_check_block(block: str, old_val: str, new_val: str | None) -> tuple[str, int]:
    """
    Заменяет/удаляет строку `retrieval_profile: <old_val>` внутри block.
    Возвращает (new_block, count).
    """
    # Паттерн для строки с retrieval_profile и старым значением
    value_pat = rf'(?:"{re.escape(old_val)}"|\'{re.escape(old_val)}\'|{re.escape(old_val)})'
    
    if new_val is None:
        # Удалить строку целиком (с завершающим \n)
        pat = re.compile(
            rf"^[ \t]+retrieval_profile:[ \t]*{value_pat}[ \t]*(?:#.*)?\n",
            re.MULTILINE,
        )
        new_block, n = pat.subn("", block)
    else:
        # Заменить значение на new_val (в двойных кавычках)
        pat = re.compile(
            rf"^([ \t]+)retrieval_profile:[ \t]*{value_pat}",
            re.MULTILINE,
        )
        new_block, n = pat.subn(rf'\1retrieval_profile: "{new_val}"', block)
    
    return new_block, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    # Группировка по файлу
    by_file: dict[Path, list[tuple[str, str, str | None]]] = {}
    for (rel, cid), (old, new) in FIXES.items():
        p = BASE / rel
        by_file.setdefault(p, []).append((cid, old, new))

    # Pre-flight: проверить, что все new_val ∈ VALID_PROFILES
    bad_targets = [
        (rel, cid, new) for (rel, cid), (_, new) in FIXES.items()
        if new is not None and new not in VALID_PROFILES
    ]
    if bad_targets:
        print("❌ Невалидные целевые профили:")
        for rel, cid, new in bad_targets:
            print(f"   {rel}::{cid} → {new}")
        sys.exit(1)
    print(f"✅ Все {sum(1 for _, n in FIXES.values() if n is not None)} целевых профилей валидны")

    total_replace = 0
    total_remove = 0
    total_warnings = 0
    changes: dict[Path, str] = {}

    for p, items in sorted(by_file.items()):
        if not p.exists():
            print(f"\n❌ файл не найден: {p}")
            total_warnings += 1
            continue

        print(f"\n{'='*100}")
        print(f"{p.relative_to(BASE)}   ({len(items)} правок)")
        print(f"{'='*100}")

        raw = p.read_text(encoding="utf-8")
        original = raw

        for cid, old, new in items:
            bounds = find_check_bounds(raw, cid)
            if not bounds:
                print(f"   ⚠️  {cid}: check не найден")
                total_warnings += 1
                continue
            start, end = bounds
            block = raw[start:end]

            new_block, n = process_check_block(block, old, new)
            if n == 0:
                print(f"   ⚠️  {cid}: retrieval_profile: {old!r} не найден")
                total_warnings += 1
                continue

            raw = raw[:start] + new_block + raw[end:]

            if new is None:
                print(f"   ✅ {cid}: удалено {old!r}")
                total_remove += n
            else:
                print(f"   ✅ {cid}: {old!r} → {new!r}")
                total_replace += n

        # Pre-flight: YAML парсится
        try:
            d = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            print(f"   ❌ YAML не парсится: {e}")
            total_warnings += 1
            continue

        # Проверить, что checks не потеряны (число не изменилось)
        orig_d = yaml.safe_load(original)
        orig_n = len(orig_d.get("checks_v8") or [])
        new_n = len(d.get("checks_v8") or [])
        if new_n != orig_n:
            print(f"   ❌ число checks изменилось: {orig_n} → {new_n}")
            total_warnings += 1
            continue

        changes[p] = raw
        print(f"   ✅ pre-flight OK ({new_n} checks)")

    print(f"\n{'='*100}")
    if args.apply:
        for p, text in changes.items():
            backup = p.with_suffix(p.suffix + ".bak_fix_a1")
            if not backup.exists():
                shutil.copy(p, backup)
            p.write_text(text, encoding="utf-8")
        print(f"✅ APPLIED: {total_replace} замен, {total_remove} удалений, {total_warnings} warnings")
    else:
        print(f"🔵 DRY-RUN: {total_replace} замен, {total_remove} удалений, {total_warnings} warnings")
        print("   Если warnings = 0 — запусти с --apply")


if __name__ == "__main__":
    main()

    