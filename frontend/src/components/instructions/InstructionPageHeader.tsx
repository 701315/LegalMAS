// src/components/instructions/InstructionPageHeader.tsx
// Переиспользуемый header для instruction pages.
// Breadcrumb + title + subtitle + right slot.

import React from "react";
import { NavLink } from "react-router-dom";
import { ChevronRight } from "lucide-react";

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

const InstructionPageHeader: React.FC<InstructionPageHeaderProps> = ({
  breadcrumbs,
  title,
  subtitle,
  rightSlot,
}) => {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-1 min-w-0">
        {/* Breadcrumb */}
        <nav
          aria-label="Breadcrumb"
          className="flex items-center gap-1 flex-wrap"
        >
          {breadcrumbs.map((crumb, index) => (
            <React.Fragment key={index}>
              {index > 0 && (
                <ChevronRight
                  className="h-3 w-3 shrink-0 text-[var(--text-faint)]"
                  aria-hidden="true"
                />
              )}
              {crumb.to ? (
                <NavLink
                  to={crumb.to}
                  className="text-[11px] uppercase tracking-[0.16em] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
                >
                  {crumb.label}
                </NavLink>
              ) : (
                <span className="text-[11px] uppercase tracking-[0.16em] text-[var(--text-muted)]">
                  {crumb.label}
                </span>
              )}
            </React.Fragment>
          ))}
        </nav>

        {/* Title */}
        <h1 className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
          {title}
        </h1>

        {/* Subtitle */}
        {subtitle && (
          <p className="text-xs text-[var(--text-secondary)]">{subtitle}</p>
        )}
      </div>

      {/* Right slot: actions */}
      {rightSlot && (
        <div className="shrink-0 flex items-center gap-2">{rightSlot}</div>
      )}
    </div>
  );
};

export default InstructionPageHeader;


