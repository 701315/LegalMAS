// =============================================================
// src/pages/tenant-admin/components/ModeSwitch.tsx
//
// Two-position toggle between "operational" and "debug" modes
// for log display.
//
// Design contract:
// - Two button elements inside a single pill container
// - Active button has accent background
// - Divider (border-l) between buttons
// - FOCUS_RING for keyboard accessibility
//
// Business meaning:
// - operational: show only warnings + errors (normal mode)
// - debug: show all logs including info (for troubleshooting)
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { LogsMode } from "../../../api/tenantAdmin";
import { FOCUS_RING } from "../constants";

export interface ModeSwitchProps {
  /** Currently selected mode */
  value: LogsMode;
  /** Callback when mode changes */
  onChange: (v: LogsMode) => void;
}

const ModeSwitch: React.FC<ModeSwitchProps> = ({ value, onChange }) => {
  const { t } = useTranslation("tenantAdmin");

  return (
    <div className="inline-flex overflow-hidden rounded-xl border border-[var(--border)] text-xs">
      <button
        type="button"
        onClick={() => onChange("operational")}
        className={`px-3 py-1.5 transition-colors ${FOCUS_RING} ${
          value === "operational"
            ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
            : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]"
        }`}
      >
        {t("logs.modeSwitch.operational")}
      </button>
      <button
        type="button"
        onClick={() => onChange("debug")}
        className={`border-l border-[var(--border)] px-3 py-1.5 transition-colors ${FOCUS_RING} ${
          value === "debug"
            ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
            : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]"
        }`}
      >
        {t("logs.modeSwitch.debug")}
      </button>
    </div>
  );
};

export default ModeSwitch;


