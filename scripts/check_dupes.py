import yaml
from pathlib import Path

FILES_TO_CHECK = [
    "playbooks/document_types/group_1_ownership/contract_1.6_real_estate.yaml",
    "playbooks/document_types/group_1_ownership/contract_1.7_barter.yaml",
    "playbooks/document_types/group_1_ownership/contract_1.5_energy_supply.yaml",
    "playbooks/document_types/group_1_ownership/contract_1.8_donation.yaml",
    "playbooks/document_types/group_3_works/contract_3.4_design_survey.yaml",
]

ROOT = Path("/home/vladi/projects/LegalMAS")
RESERVED_SUFFIXES = ("_status", "_details", "_value", "_code")

def collect_checks(node):
    found = []
    def _walk(v):
        if isinstance(v, dict):
            if "id" in v and "extraction" in v:
                found.append(v)
            for child in v.values():
                _walk(child)
        elif isinstance(v, list):
            for child in v:
                _walk(child)
    _walk(node)
    return found

found_any = False

for rel_path in FILES_TO_CHECK:
    path = ROOT / rel_path
    if not path.exists():
        continue
    docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    short = rel_path.replace("playbooks/", "")

    for doc in docs:
        for check in collect_checks(doc):
            ext = check.get("extraction", {})
            if not isinstance(ext, dict):
                continue
            fields = ext.get("fields", [])
            if not isinstance(fields, list):
                continue

            names = [f.get("name", "") for f in fields if isinstance(f, dict)]
            name_set = set(names)

            duplicates = []
            for name in names:
                if not isinstance(name, str) or not name:
                    continue
                for suffix in RESERVED_SUFFIXES:
                    new_name = name + suffix
                    if new_name in name_set:
                        duplicates.append((name, new_name))

            if duplicates:
                found_any = True
                print(f"\nFILE: {short}")
                print(f"  CHECK: {check.get('id')}")
                print("  ДУБЛИРУЮЩИЕСЯ ПАРЫ В fields:")
                for old, new in sorted(set(duplicates)):
                    print(f"    '{old}' + '{new}'")

if not found_any:
    print("Дубликатов не найдено.")

    