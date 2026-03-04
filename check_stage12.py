#!/usr/bin/env python
import os
from pathlib import Path

ROOT = Path("/mnt/c/LegalMAS")

# Список проверок по шагам этапа 12
CHECKS = [
    # 12.1–12.2: структура и зависимости
    ("12.1_components_grid_folder", (ROOT / "frontend" / "src" / "components" / "grid").is_dir()),
    ("12.1_components_grid_cells_folder", (ROOT / "frontend" / "src" / "components" / "grid" / "cells").is_dir()),
    ("12.2_components_evidence_folder", (ROOT / "frontend" / "src" / "components" / "evidence").is_dir()),

    # 12.3: list_runs_for_deal + include_classification_stats
    ("12.3_backend_list_runs_for_deal",
     (ROOT / "src" / "api" / "endpoints" / "runs.py").exists() or
     (ROOT / "src" / "api" / "endpoints" / "deals_runs.py").exists()),
    ("12.3_runresponse_has_classification_stats",
     any("RunResponse" in p.read_text(encoding="utf-8", errors="ignore") and "classification_stats" in p.read_text(encoding="utf-8", errors="ignore")
         for p in (ROOT / "src" / "api" / "schemas").rglob("*.py") if p.is_file()) if (ROOT / "src" / "api" / "schemas").exists() else False),

    # 12.4: frontend src/api/results.ts
    ("12.4_results_ts_exists", (ROOT / "frontend" / "src" / "api" / "results.ts").exists()),
    ("12.4_results_ts_has_listRuns",
     (ROOT / "frontend" / "src" / "api" / "results.ts").exists() and
     "listRuns" in (ROOT / "frontend" / "src" / "api" / "results.ts").read_text(encoding="utf-8", errors="ignore")),
    ("12.4_useAllResults_hook",
     (ROOT / "frontend" / "src" / "api" / "results.ts").exists() and
     "useAllResults" in (ROOT / "frontend" / "src" / "api" / "results.ts").read_text(encoding="utf-8", errors="ignore")),
    ("12.4_useLatestRun_hook",
     (ROOT / "frontend" / "src" / "api" / "results.ts").exists() and
     "useLatestRun" in (ROOT / "frontend" / "src" / "api" / "results.ts").read_text(encoding="utf-8", errors="ignore")),

    # 12.5: src/api/qc.ts
    ("12.5_qc_ts_exists", (ROOT / "frontend" / "src" / "api" / "qc.ts").exists()),
    ("12.5_qc_api_confirm",
     (ROOT / "frontend" / "src" / "api" / "qc.ts").exists() and
     "confirm(" in (ROOT / "frontend" / "src" / "api" / "qc.ts").read_text(encoding="utf-8", errors="ignore")),
    ("12.5_qc_hooks",
     (ROOT / "frontend" / "src" / "api" / "qc.ts").exists() and
     all(x in (ROOT / "frontend" / "src" / "api" / "qc.ts").read_text(encoding="utf-8", errors="ignore")
         for x in ["useConfirmResults", "useRejectResults", "useOverrideResults"])),

    # 12.6: src/api/evidence.ts
    ("12.6_evidence_ts_exists", (ROOT / "frontend" / "src" / "api" / "evidence.ts").exists()),
    ("12.6_evidence_api_get",
     (ROOT / "frontend" / "src" / "api" / "evidence.ts").exists() and
     "evidenceApi" in (ROOT / "frontend" / "src" / "api" / "evidence.ts").read_text(encoding="utf-8", errors="ignore")),
    ("12.6_useEvidence_hook",
     (ROOT / "frontend" / "src" / "api" / "evidence.ts").exists() and
     "useEvidence" in (ROOT / "frontend" / "src" / "api" / "evidence.ts").read_text(encoding="utf-8", errors="ignore")),

    # 12.7–12.9: DDGrid и GridTab
    ("12.7_DDGrid_exists", (ROOT / "frontend" / "src" / "components" / "grid" / "DDGrid.tsx").exists()),
    ("12.7_DDGrid_uses_table",
     (ROOT / "frontend" / "src" / "components" / "grid" / "DDGrid.tsx").exists() and
     "<table" in (ROOT / "frontend" / "src" / "components" / "grid" / "DDGrid.tsx").read_text(encoding="utf-8", errors="ignore")),
    ("12.8_GridTab_exists", (ROOT / "frontend" / "src" / "pages" / "tabs" / "GridTab.tsx").exists()),
    ("12.9_DDGrid_uses_AgGridReact",
     (ROOT / "frontend" / "src" / "components" / "grid" / "DDGrid.tsx").exists() and
     "AgGridReact" in (ROOT / "frontend" / "src" / "components" / "grid" / "DDGrid.tsx").read_text(encoding="utf-8", errors="ignore")),

    # 12.10–12.11: MagicZoom и EvidencePanel
    ("12.10_MagicZoom_exists", (ROOT / "frontend" / "src" / "components" / "evidence" / "MagicZoom.tsx").exists()),
    ("12.11_EvidencePanel_exists", (ROOT / "frontend" / "src" / "components" / "evidence" / "EvidencePanel.tsx").exists()),

    # 12.12–12.13: BulkQCBar и QC-рендереры
    ("12.12_BulkQCBar_exists", (ROOT / "frontend" / "src" / "components" / "grid" / "BulkQCBar.tsx").exists()),
    ("12.13_QC_renderers_exist",
     any("QualityFlagRenderer" in p.read_text(encoding="utf-8", errors="ignore") or
         "QCCellRenderer" in p.read_text(encoding="utf-8", errors="ignore")
         for p in (ROOT / "frontend" / "src" / "components" / "grid").rglob("*.tsx")
         ) if (ROOT / "frontend" / "src" / "components" / "grid").exists() else False),

    # 12.18: колонки классификации / триггера
    ("12.18_DDGrid_has_classification_columns",
     (ROOT / "frontend" / "src" / "components" / "grid" / "DDGrid.tsx").exists() and
     ("classification_level" in (ROOT / "frontend" / "src" / "components" / "grid" / "DDGrid.tsx").read_text(encoding="utf-8", errors="ignore") or
      "trigger_name" in (ROOT / "frontend" / "src" / "components" / "grid" / "DDGrid.tsx").read_text(encoding="utf-8", errors="ignore"))),

    # 12.20: DealPage таб DD Grid
    ("12.20_DealPage_has_DDGrid_tab",
     (ROOT / "frontend" / "src" / "pages" / "DealPage.tsx").exists() and
     "DD Grid" in (ROOT / "frontend" / "src" / "pages" / "DealPage.tsx").read_text(encoding="utf-8", errors="ignore")),
]

def main():
    print(f"Checking LegalMAS Stage 12 in: {ROOT}")
    if not ROOT.exists():
        print("ERROR: root path does not exist. Check ROOT variable.")
        return

    max_name_len = max(len(name) for name, _ in CHECKS)
    for name, ok in CHECKS:
        status = "OK " if ok else "MISS"
        print(f"{status}  {name.ljust(max_name_len)}")

if __name__ == "__main__":
    main()
