// src/components/instructions/InstructionPageHeader.tsx
// Унифицированный header для instruction pages.
//
// Визуальный паттерн полностью совпадает с AdminPage / AdminMonitoringPage:
// заголовок на фоне страницы (без карточки-обёртки), breadcrumbs встроены
// в inline-подзаголовок через "·" разделители, right slot для actions.

import React from "react";
import { NavLink } from "react-router-dom";

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

interface InstructionPageHeaderProps {
  breadcrumbs: BreadcrumbItem[];
  title: string;
  subtitle?: string;
  rightSlot?: React.ReactNode;
}

// ─────────────────────────────────────────────────────────────
// Breadcrumbs как inline-подзаголовок
// ─────────────────────────────────────────────────────────────

const BreadcrumbTrail: React.FC<{ items: BreadcrumbItem[] }> = ({ items }) => (
  <nav
    aria-label="Breadcrumb"
    className="text-sm text-[var(--text-muted)]"
  >
    {items.map((crumb, index) => {
      const isLast = index === items.length - 1;
      return (
        <React.Fragment key={index}>
          {index > 0 && <span className="mx-1.5">·</span>}
          {crumb.to && !isLast ? (
            <NavLink
              to={crumb.to}
              className="transition-colors hover:text-[var(--text-secondary)]"
            >
              {crumb.label}
            </NavLink>
          ) : (
            <span className={isLast ? "text-[var(--text-secondary)]" : ""}>
              {crumb.label}
            </span>
          )}
        </React.Fragment>
      );
    })}
  </nav>
);

// ─────────────────────────────────────────────────────────────
// InstructionPageHeader
// ─────────────────────────────────────────────────────────────

const InstructionPageHeader: React.FC<InstructionPageHeaderProps> = ({
  breadcrumbs,
  title,
  subtitle,
  rightSlot,
}) => (
  <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
    <div className="min-w-0">
      <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
        {title}
      </h1>

      {/* Breadcrumb-строка */}
      {breadcrumbs.length > 0 && (
        <div className="mt-1">
          <BreadcrumbTrail items={breadcrumbs} />
        </div>
      )}

      {/* Опциональный subtitle — отдельным абзацем */}
      {subtitle && (
        <p className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]">
          {subtitle}
        </p>
      )}
    </div>

    {rightSlot && (
      <div className="flex shrink-0 items-center gap-2">{rightSlot}</div>
    )}
  </header>
);

export default InstructionPageHeader;


