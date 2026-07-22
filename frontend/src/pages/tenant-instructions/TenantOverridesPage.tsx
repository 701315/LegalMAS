// src/pages/tenant-instructions/TenantOverridesPage.tsx
// Список tenant-level overrides.
// Доступен tenant_admin (свой tenant) и superadmin (любой tenant).

import React from "react";
import { useNavigate } from "react-router-dom";
import { Plus, RefreshCw } from "lucide-react";

import { useTenantOverrides } from "../../hooks/instructions/useInstructionOverrides";
import { useAuth } from "../../hooks/useAuth";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import OverrideStatusBadge from "../../components/instructions/OverrideStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import PageSection from "../../components/ui/PageSection";
import type { InstructionOverrideItem } from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Override list item
// ─────────────────────────────────────────────────────────────

interface OverrideListItemProps {
  override: InstructionOverrideItem;
  onClick: () => void;
}

const OverrideListItem: React.FC<OverrideListItemProps> = ({
  override,
  onClick,
}) => {
  const updatedAt = override.updated_at
    ? new Date(override.updated_at).toLocaleDateString("ru-RU")
    : null;

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-left text-xs transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* Version ID reference */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-[var(--text-primary)]">
              {override.global_instruction_version_id
                ? "Global Override"
                : "Override"}
            </span>
            <span className="font-mono text-[10px] text-[var(--text-muted)]">
              {override.global_instruction_version_id
                ? `global: ${override.global_instruction_version_id.slice(0, 8)}…`
                : override.instruction_version_id
                  ? `v_id: ${override.instruction_version_id.slice(0, 8)}…`
                  : ""}
            </span>
          </div>

          {override.change_summary && (
            <div className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
              {override.change_summary}
            </div>
          )}

          <div className="mt-1.5 flex items-center gap-3 text-[10px] text-[var(--text-muted)]">
            <span className="font-mono">
              id: {override.id.slice(0, 8)}…
            </span>
            <span>{override.patch_ops.length} ops</span>
            {updatedAt && <span>Updated: {updatedAt}</span>}
          </div>
        </div>

        <OverrideStatusBadge
          status={override.status}
          isStale={override.is_stale}
          size="xs"
        />
      </div>
    </button>
  );
};

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const TenantOverridesPage: React.FC = () => {
  const navigate = useNavigate();

  // tenantId: для tenant_admin берём из userId-контекста (через backend),
  // для superadmin — можно выбирать. Пока используем userId как tenantId-placeholder.
  // TODO: заменить на реальный tenantId из user profile когда будет доступен.
  const tenantId = useAuth().userId ?? "";

  // ... остальное без изменений

  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useTenantOverrides(tenantId || null);

  const overrides = data?.items ?? [];

  const activeCount = overrides.filter((o) => o.status === "active").length;
  const draftCount = overrides.filter((o) => o.status === "draft").length;
  const staleCount = overrides.filter((o) => o.is_stale).length;

  const handleOpenOverride = (overrideId: string) => {
    navigate(`/tenant-admin/instructions/overrides/${overrideId}`);
  };

  const handleCreateNew = () => {
    navigate("/tenant-admin/instructions/overrides/new");
  };

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        {/* Header */}
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Tenant Admin", to: "/tenant-admin" },
            {
              label: "Инструкции",
              to: "/tenant-admin/instructions",
            },
            { label: "Overrides" },
          ]}
          title="Instruction Overrides"
          subtitle="Переопределения инструкций на уровне tenant. Применяются поверх базовых версий."
          rightSlot={
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refetch()}
                aria-label="Обновить"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleCreateNew}
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                Новый override
              </Button>
            </div>
          }
        />

        {/* Stats */}
        {!isLoading && !isError && overrides.length > 0 && (
          <div className="flex items-center gap-4 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-2.5">
            <div className="text-[11px] text-[var(--text-muted)]">
              Active:{" "}
              <span className="font-semibold text-[color:var(--color-success-text)]">
                {activeCount}
              </span>
            </div>
            <div className="h-3 w-px bg-[var(--border)]" aria-hidden="true" />
            <div className="text-[11px] text-[var(--text-muted)]">
              Draft:{" "}
              <span className="font-semibold text-[var(--text-primary)]">
                {draftCount}
              </span>
            </div>
            {staleCount > 0 && (
              <>
                <div className="h-3 w-px bg-[var(--border)]" aria-hidden="true" />
                <div className="text-[11px] text-[var(--text-muted)]">
                  Stale:{" "}
                  <span className="font-semibold text-[#b91c1c]">
                    {staleCount}
                  </span>
                </div>
              </>
            )}
          </div>
        )}

        {/* Stale warning */}
        {staleCount > 0 && (
          <div className="flex items-center gap-2 rounded-xl border border-[color:var(--color-warning-border,#fbbf24)] bg-[color:var(--color-warning-bg,#fef9c3)] px-4 py-2.5">
            <span className="text-[11px] text-[color:var(--color-warning-text,#92400e)]">
              {staleCount}{" "}
              {staleCount === 1 ? "override устарел" : "overrides устарели"} —
              базовая версия инструкции была обновлена. Создайте новые overrides
              на актуальной версии.
            </span>
          </div>
        )}

        {/* List */}
        <PageSection title="Overrides">
          {isLoading && (
            <LoadingBlock text="Загружаем overrides..." rows={4} />
          )}

          {isError && (
            <InlineAlert
              tone="error"
              message="Не удалось загрузить overrides. Проверьте подключение."
            />
          )}

          {!isLoading && !isError && overrides.length === 0 && (
            <EmptyState
              title="Overrides не созданы"
              description="Создайте первый override чтобы переопределить базовую инструкцию для вашего tenant."
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCreateNew}
                >
                  Создать override
                </Button>
              }
            />
          )}

          {!isLoading && !isError && overrides.length > 0 && (
            <ul className="space-y-2">
              {overrides.map((override) => (
                <li key={override.id}>
                  <OverrideListItem
                    override={override}
                    onClick={() => handleOpenOverride(override.id)}
                  />
                </li>
              ))}
            </ul>
          )}
        </PageSection>
      </div>
    </div>
  );
};

export default TenantOverridesPage;


