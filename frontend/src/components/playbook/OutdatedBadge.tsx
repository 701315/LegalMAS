// =============================================================
// src/components/playbook/OutdatedBadge.tsx
// Красный pill-бейдж: "N/M global-инструкций устарели".
// Tooltip: пояснение о том, что инструкции изменились после
// создания playbook'а.
//
// Namespace i18n: "playbooks" — компонент сам подтягивает его
// через useTranslation, независимо от того, из какого
// namespace рендерится родитель.
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";

import type { StalePlaybookItem } from "../../types/playbooks";

interface OutdatedBadgeProps {
  item: StalePlaybookItem;
  /** sm — компактный (для списков), md — чуть больше. */
  size?: "sm" | "md";
  /** Показывать ли tooltip со списком кодов (default: true). */
  withTooltip?: boolean;
}

const OutdatedBadge: React.FC<OutdatedBadgeProps> = ({
  item,
  size = "sm",
  withTooltip = true,
}) => {
  const { t } = useTranslation("playbooks");

  const sizeCls =
    size === "md"
      ? "gap-1 px-2 py-0.5 text-[10px]"
      : "gap-1 px-1.5 py-0.5 text-[9px]";

  const label = t("staleness.badge.label", {
    outdated: item.outdated_count,
    total: item.total_refs,
  });

  const tooltip = withTooltip
    ? t("staleness.badge.tooltip", {
        outdated: item.outdated_count,
        total: item.total_refs,
        createdAt: item.created_at ?? "—",
      })
    : undefined;

  return (
    <span
      title={tooltip}
      className={[
        "inline-flex items-center rounded-full border font-semibold whitespace-nowrap",
        "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]",
        sizeCls,
      ].join(" ")}
    >
      <span aria-hidden="true">⚠</span>
      <span>{label}</span>
    </span>
  );
};

export default OutdatedBadge;
