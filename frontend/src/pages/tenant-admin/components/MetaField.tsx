// =============================================================
// src/pages/tenant-admin/components/MetaField.tsx
//
// Labeled field для отображения метаданных (например, Deal ID, Run ID,
// Worker hostname). Опционально имеет action button справа от label
// (используется для correlation actions в LogDetailsPane).
//
// Design contract:
// - Rounded bordered card
// - Label uppercase mini (LABEL_XS)
// - Value с break-all для длинных ID
// - "—" fallback для пустых значений
// - Optional action button (например, "Все логи run" в LogDetailsPane)
// =============================================================

import React from "react";
import { LABEL_XS, FOCUS_RING } from "../constants";

export interface MetaFieldProps {
  /** Label над значением */
  label: string;
  /** Значение (может быть null/undefined — тогда показывается "—") */
  value: string | null | undefined;
  /** Опциональный callback для action button */
  onClick?: () => void;
  /** Кастомный текст action button (default: "Показать всё") */
  actionLabel?: string;
}

const MetaField: React.FC<MetaFieldProps> = ({
  label,
  value,
  onClick,
  actionLabel,
}) => (
  <div className="rounded-xl border border-[var(--border)] px-3 py-2">
    <div className="flex items-start justify-between gap-2">
      <p className={LABEL_XS}>{label}</p>
      {value && onClick && (
        <button
          type="button"
          onClick={onClick}
          className={`text-[10px] font-medium text-[var(--accent-primary)] hover:underline ${FOCUS_RING}`}
        >
          {actionLabel ?? "Показать всё"}
        </button>
      )}
    </div>
    <p className="mt-0.5 break-all text-sm text-[var(--text-primary)]">
      {value || "—"}
    </p>
  </div>
);

export default MetaField;


