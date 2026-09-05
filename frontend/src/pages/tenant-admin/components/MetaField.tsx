// =============================================================
// src/pages/tenant-admin/components/MetaField.tsx
//
// Labeled field for displaying metadata (e.g. Deal ID, Run ID,
// Worker hostname). Optionally has an action button to the right
// of the label (used for correlation actions in LogDetailsPane).
//
// Design contract:
// - Rounded bordered card
// - Uppercase mini label (LABEL_XS)
// - Value with break-all for long IDs
// - "—" fallback for empty values
// - Optional action button (e.g. "All run logs" in LogDetailsPane)
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { LABEL_XS, FOCUS_RING } from "../constants";

export interface MetaFieldProps {
  /** Label above the value */
  label: string;
  /** Value (may be null/undefined — shows "—" in that case) */
  value: string | null | undefined;
  /** Optional callback for action button */
  onClick?: () => void;
  /** Custom action button text (default: t("meta.showAll")) */
  actionLabel?: string;
}

const MetaField: React.FC<MetaFieldProps> = ({
  label,
  value,
  onClick,
  actionLabel,
}) => {
  const { t } = useTranslation("tenantAdmin");
  const resolvedActionLabel = actionLabel ?? t("meta.showAll");

  return (
    <div className="rounded-xl border border-[var(--border)] px-3 py-2">
      <div className="flex items-start justify-between gap-2">
        <p className={LABEL_XS}>{label}</p>
        {value && onClick && (
          <button
            type="button"
            onClick={onClick}
            className={`text-[10px] font-medium text-[var(--accent-primary)] hover:underline ${FOCUS_RING}`}
          >
            {resolvedActionLabel}
          </button>
        )}
      </div>
      <p className="mt-0.5 break-all text-sm text-[var(--text-primary)]">
        {value || "—"}
      </p>
    </div>
  );
};

export default MetaField;


