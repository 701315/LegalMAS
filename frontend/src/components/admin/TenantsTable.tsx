// =============================================================
// src/components/admin/TenantsTable.tsx
// Табличное представление списка клиентов.
// =============================================================

import React from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUp,
  ArrowDown,
  Copy,
  Check,
  Settings2,
  Ban,
  PlayCircle,
} from "lucide-react";
import type { Tenant } from "../../api/admin";

export type SortKey = "name" | "created_at" | "deals_count" | "users_count";
export type SortDir = "asc" | "desc";

function formatDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

const CopyableShortId: React.FC<{ id: string }> = ({ id }) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // silent fail
    }
  };

  return (
    <span className="inline-flex items-center gap-1" title={`Полный ID: ${id}`}>
      <code className="font-mono text-[11px] text-[var(--text-secondary)]">
        {id.slice(0, 8)}…
      </code>
      <button
        type="button"
        onClick={handleCopy}
        aria-label={copied ? "Скопировано" : "Скопировать ID"}
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35"
      >
        {copied ? (
          <Check className="h-3 w-3 text-[var(--color-success-text)]" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </button>
    </span>
  );
};

interface SortableHeaderProps {
  label: string;
  sortableKey?: SortKey;
  currentSortKey: SortKey;
  currentSortDir: SortDir;
  onSortChange: (key: SortKey, dir: SortDir) => void;
  align?: "left" | "center" | "right";
  className?: string;
}

const SortableHeader: React.FC<SortableHeaderProps> = ({
  label,
  sortableKey,
  currentSortKey,
  currentSortDir,
  onSortChange,
  align = "left",
  className = "",
}) => {
  const isActive = sortableKey === currentSortKey;
  const isSortable = Boolean(sortableKey);

  const handleClick = () => {
    if (!sortableKey) return;
    if (sortableKey === currentSortKey) {
      onSortChange(sortableKey, currentSortDir === "asc" ? "desc" : "asc");
    } else {
      const defaultDir: SortDir = sortableKey === "name" ? "asc" : "desc";
      onSortChange(sortableKey, defaultDir);
    }
  };

  const alignClass =
    align === "center"
      ? "text-center"
      : align === "right"
        ? "text-right"
        : "text-left";

  const inner = (
    <span
      className={[
        "inline-flex items-center gap-1",
        align === "center" && "justify-center",
        align === "right" && "justify-end",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {label}
      {isActive &&
        (currentSortDir === "asc" ? (
          <ArrowUp className="h-3 w-3 text-[var(--accent-primary)]" />
        ) : (
          <ArrowDown className="h-3 w-3 text-[var(--accent-primary)]" />
        ))}
    </span>
  );

  return (
    <th
      scope="col"
      className={[
        "border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]",
        "px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.08em]",
        "text-[var(--text-muted)]",
        alignClass,
        className,
      ].join(" ")}
    >
      {isSortable ? (
        <button
          type="button"
          onClick={handleClick}
          className={[
            "inline-flex w-full items-center gap-1 transition-colors",
            "hover:text-[var(--text-primary)]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35",
            align === "center" && "justify-center",
            align === "right" && "justify-end",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {inner}
        </button>
      ) : (
        inner
      )}
    </th>
  );
};

interface TenantsTableProps {
  tenants: Tenant[];
  sortKey: SortKey;
  sortDir: SortDir;
  onSortChange: (key: SortKey, dir: SortDir) => void;
  onDeactivate: (tenant: Tenant) => void;
  onActivate: (tenant: Tenant) => void;
}

const TenantsTable: React.FC<TenantsTableProps> = ({
  tenants,
  sortKey,
  sortDir,
  onSortChange,
  onDeactivate,
  onActivate,
}) => {
  const navigate = useNavigate();

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[880px] border-collapse">
          <thead>
            <tr>
              <SortableHeader
                label="№"
                currentSortKey={sortKey}
                currentSortDir={sortDir}
                onSortChange={onSortChange}
                align="center"
                className="w-12"
              />
              <SortableHeader
                label="Клиент"
                sortableKey="name"
                currentSortKey={sortKey}
                currentSortDir={sortDir}
                onSortChange={onSortChange}
              />
              <SortableHeader
                label="Создан"
                sortableKey="created_at"
                currentSortKey={sortKey}
                currentSortDir={sortDir}
                onSortChange={onSortChange}
                className="w-28"
              />
              <SortableHeader
                label="Slug"
                currentSortKey={sortKey}
                currentSortDir={sortDir}
                onSortChange={onSortChange}
              />
              <SortableHeader
                label="ID"
                currentSortKey={sortKey}
                currentSortDir={sortDir}
                onSortChange={onSortChange}
              />
              <SortableHeader
                label="Пользователи"
                sortableKey="users_count"
                currentSortKey={sortKey}
                currentSortDir={sortDir}
                onSortChange={onSortChange}
                align="center"
                className="w-32"
              />
              <SortableHeader
                label="Проекты"
                sortableKey="deals_count"
                currentSortKey={sortKey}
                currentSortDir={sortDir}
                onSortChange={onSortChange}
                align="center"
                className="w-28"
              />
              <SortableHeader
                label=""
                currentSortKey={sortKey}
                currentSortDir={sortDir}
                onSortChange={onSortChange}
                align="right"
                className="w-32"
              />
            </tr>
          </thead>

          <tbody>
            {tenants.map((tenant, index) => (
              <tr
                key={tenant.id}
                onClick={() => navigate(`/admin/tenants/${tenant.id}`)}
                className={[
                  "cursor-pointer border-b border-[var(--border-subtle)] transition-colors",
                  "hover:bg-[var(--bg-elevated-soft)]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-inset",
                  !tenant.is_active && "opacity-60",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {/* № */}
                <td className="px-3 py-3 text-center text-xs text-[var(--text-muted)]">
                  {index + 1}
                </td>

                {/* Клиент */}
                <td className="px-3 py-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {tenant.name}
                    </span>
                    {!tenant.is_active && (
                      <span className="rounded-full bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
                        Деактивирован
                      </span>
                    )}
                  </div>
                </td>

                {/* Создан */}
                <td className="px-3 py-3 text-xs text-[var(--text-muted)]">
                  {formatDate(tenant.created_at)}
                </td>

                {/* Slug */}
                <td className="px-3 py-3">
                  <code className="font-mono text-xs text-[var(--text-secondary)]">
                    {tenant.slug}
                  </code>
                </td>

                {/* ID */}
                <td
                  className="px-3 py-3"
                  onClick={(e) => e.stopPropagation()}
                >
                  <CopyableShortId id={tenant.id} />
                </td>

                {/* Пользователи */}
                <td
                  className="px-3 py-3 text-center"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Link
                    to={`/admin/tenants/${tenant.id}`}
                    className="inline-block rounded px-2 py-0.5 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--accent-muted)] hover:text-[var(--accent-primary)]"
                  >
                    {tenant.users_count}
                  </Link>
                </td>

                {/* Проекты */}
                <td
                  className="px-3 py-3 text-center"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Link
                    to={`/admin/tenants/${tenant.id}/projects`}
                    className="inline-block rounded px-2 py-0.5 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--accent-muted)] hover:text-[var(--accent-primary)]"
                  >
                    {tenant.deals_count}
                  </Link>
                </td>

                {/* Действия */}
                <td
                  className="px-3 py-3 text-right"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center justify-end gap-1">
                    <button
                      type="button"
                      onClick={() => navigate(`/admin/tenants/${tenant.id}`)}
                      title="Управление"
                      className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
                    >
                      <Settings2 className="h-3.5 w-3.5" />
                    </button>

                    {tenant.is_active ? (
                      <button
                        type="button"
                        onClick={() => onDeactivate(tenant)}
                        title="Деактивировать"
                        className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--color-error-bg)] hover:text-[var(--color-error-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-error-border)]"
                      >
                        <Ban className="h-3.5 w-3.5" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onActivate(tenant)}
                        title="Активировать"
                        className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--color-success-bg)] hover:text-[var(--color-success-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-success-border)]"
                      >
                        <PlayCircle className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TenantsTable;


