// =============================================================
// src/pages/tenant-admin/components/KpiCard.tsx
//
// Compact KPI card для отображения метрики (label + value + optional sub).
// Используется во всех табах admin panel: Monitoring, Overview, Logs.
//
// Design contract:
// - Ограниченная высота — все карточки в grid имеют одинаковую высоту
// - truncate для value и sub — предотвращает overflow при длинных значениях
// - tone параметр для семантической окраски value (default | ok | warn | error)
// =============================================================

import React from "react";
import { LABEL_XS } from "../constants";
import { toneClass } from "../utils";

export interface KpiCardProps {
  /** Uppercase label над значением (например, "ВСЕГО", "ОШИБКИ") */
  label: string;
  /** Основное значение (число, строка, JSX) */
  value: React.ReactNode;
  /** Опциональная подпись под значением (мелким шрифтом) */
  sub?: React.ReactNode;
  /**
   * Семантическая окраска value:
   * - default: обычный text-primary цвет
   * - ok: зелёный (success)
   * - warn: оранжевый (warning)
   * - error: красный (error)
   */
  tone?: "default" | "ok" | "warn" | "error";
}

const KpiCard: React.FC<KpiCardProps> = ({
  label,
  value,
  sub,
  tone = "default",
}) => (
  <div className="flex min-w-0 flex-col gap-0.5 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 shadow-sm">
    <p className={LABEL_XS}>{label}</p>
    <p
      className={`truncate text-sm font-semibold tabular-nums leading-5 ${toneClass(tone)}`}
    >
      {value}
    </p>
    {sub && (
      <p className="truncate text-[10px] leading-4 text-[var(--text-muted)]">
        {sub}
      </p>
    )}
  </div>
);

export default KpiCard;


