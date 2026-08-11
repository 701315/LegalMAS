// =============================================================
// src/pages/tenant-admin/components/ModeSwitch.tsx
//
// Двухпозиционный переключатель между "operational" и "debug" модами
// для отображения логов.
//
// Design contract:
// - Два button-элемента внутри одного pill-контейнера
// - Активный button имеет accent background
// - Разделитель (border-l) между buttons
// - FOCUS_RING для keyboard accessibility
//
// Business meaning:
// - operational: показать только warnings + errors (обычный режим)
// - debug: показать все логи включая info (для troubleshooting)
// =============================================================

import React from "react";
import type { LogsMode } from "../../../api/tenantAdmin";
import { FOCUS_RING } from "../constants";

export interface ModeSwitchProps {
  /** Текущий выбранный режим */
  value: LogsMode;
  /** Callback при переключении режима */
  onChange: (v: LogsMode) => void;
}

const ModeSwitch: React.FC<ModeSwitchProps> = ({ value, onChange }) => (
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
      События платформы
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
      Debug (все логи)
    </button>
  </div>
);

export default ModeSwitch;


