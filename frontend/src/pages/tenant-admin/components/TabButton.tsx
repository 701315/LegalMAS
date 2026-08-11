// =============================================================
// src/pages/tenant-admin/components/TabButton.tsx
//
// Tab button с опциональным numeric/string badge справа.
// Используется в:
// - Main admin panel (переключение между табами: Проекты, Пользователи, ...)
// - ProjectDrillDown (переключение sub-tabs: Обзор, Участники, Логи)
//
// Design contract:
// - Active state: accent background + accent text + subtle shadow
// - Inactive state: muted text, hover effect на elevated-soft
// - Badge: rounded pill с tabular-nums для чисел
// - FOCUS_RING для keyboard accessibility
// =============================================================

import React from "react";
import { FOCUS_RING } from "../constants";

export interface TabButtonProps {
  /** Активен ли этот tab */
  active: boolean;
  /** Callback при клике */
  onClick: () => void;
  /** Содержимое tab button (обычно текст, но может быть JSX) */
  children: React.ReactNode;
  /** Опциональный badge справа (число или строка) */
  badge?: number | string;
}

const TabButton: React.FC<TabButtonProps> = ({
  active,
  onClick,
  children,
  badge,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-1.5 text-xs font-medium transition-colors ${FOCUS_RING} ${
      active
        ? "bg-[var(--accent-muted)] text-[var(--accent-primary)] shadow-sm"
        : "text-[var(--text-muted)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
    }`}
  >
    {children}
    {badge != null && (
      <span className="rounded-full bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] tabular-nums">
        {badge}
      </span>
    )}
  </button>
);

export default TabButton;


