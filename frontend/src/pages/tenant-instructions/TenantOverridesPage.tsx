// src/pages/tenant-instructions/TenantOverridesPage.tsx

import React from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Plus } from "lucide-react";

import { useTenantOverrides } from "../../hooks/instructions/useInstructionOverrides";
import { useAuth } from "../../hooks/useAuth";
import OverrideStatusBadge from "../../components/instructions/OverrideStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type { InstructionOverrideItem } from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// OverrideCard
// ─────────────────────────────────────────────────────────────

const OverrideCard: React.FC<{
  override: InstructionOverrideItem;
  onClick: () => void;
}> = ({ override, onClick }) => {
  const updatedAt = override.updated_at
    ? new Date(override.updated_at).toLocaleDateString("ru-RU")
    : null;

  const baseLabel = override.global_instruction_version_id
    ? "Global Override"
    : "Doc-Type Override";

  const baseId =
    override.global_instruction_version_id ??
    override.instruction_version_id ??
    "";

  return (
    <button
      type="button"
      onClick={onClick}
      className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-[var(--text-primary)]">
              {baseLabel}
            </span>
            {baseId && (
              <span className="font-mono text-[10px] text-[var(--text-muted)]">
                {baseId.slice(0, 8)}…
              </span>
            )}
          </div>

          {override.change_summary && (
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              {override.change_summary}
            </p>
          )}

          <p className="mt-2 text-[10px] text-[var(--text-muted)]">
            <span className="font-mono">id: {override.id.slice(0, 8)}…</span>
            <span className="mx-1.5">·</span>
            {override.patch_ops.length} ops
            {updatedAt && (
              <>
                <span className="mx-1.5">·</span>
                Обновлён: {updatedAt}
              </>
            )}
          </p>
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
// TenantOverridesPage
// ─────────────────────────────────────────────────────────────

const TenantOverridesPage: React.FC = () => {
  const navigate = useNavigate();
  const { tenantId: authTenantId } = useAuth();
  const tenantId = authTenantId ?? "";

  const { data, isLoading, isError } = useTenantOverrides(tenantId || null);

  const overrides = data?.items ?? [];
  const activeCount = overrides.filter((o) => o.status === "active").length;
  const draftCount = overrides.filter((o) => o.status === "draft").length;
  const staleCount = overrides.filter((o) => o.is_stale).length;

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Шапка ───────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <button
                type="button"
                onClick={() => navigate("/tenant-admin/instructions")}
                className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Инструкции
              </button>

              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Instruction Overrides
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Переопределения инструкций на уровне tenant. Применяются поверх
                базовых published-версий.
              </p>

              {!isLoading && !isError && overrides.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 text-[12px]">
                  <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[var(--text-secondary)]">
                    Всего: {overrides.length}
                  </span>
                  {activeCount > 0 && (
                    <span className="rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-3 py-1 text-[var(--color-success-text)]">
                      Active: {activeCount}
                    </span>
                  )}
                  {draftCount > 0 && (
                    <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[var(--text-secondary)]">
                      Draft: {draftCount}
                    </span>
                  )}
                  {staleCount > 0 && (
                    <span className="rounded-full border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-1 text-[var(--color-warning-text)]">
                      Stale: {staleCount}
                    </span>
                  )}
                </div>
              )}
            </div>

            <Button
              variant="primary"
              size="sm"
              onClick={() =>
                navigate("/tenant-admin/instructions/overrides/new")
              }
              leftIcon={<Plus className="h-3.5 w-3.5" />}
            >
              Новый override
            </Button>
          </div>
        </header>

        {/* ── Stale warning ────────────────────────────────────── */}
        {staleCount > 0 && (
          <div className="rounded-2xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-5 py-4 text-sm text-[var(--color-warning-text)]">
            {staleCount}{" "}
            {staleCount === 1 ? "override устарел" : "overrides устарели"} —
            базовая версия инструкции была обновлена. Создайте новые overrides
            на актуальной версии.
          </div>
        )}

        {/* ── Loading ──────────────────────────────────────────── */}
        {isLoading && <LoadingBlock text="Загружаем overrides…" rows={4} />}

        {/* ── Error ────────────────────────────────────────────── */}
        {isError && (
          <InlineAlert
            tone="error"
            message="Не удалось загрузить overrides. Проверьте подключение."
          />
        )}

        {/* ── Empty ────────────────────────────────────────────── */}
        {!isLoading && !isError && overrides.length === 0 && (
          <EmptyState
            title="Overrides не созданы"
            description="Создайте первый override, чтобы переопределить базовую инструкцию для вашего tenant."
            action={
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  navigate("/tenant-admin/instructions/overrides/new")
                }
              >
                Создать override
              </Button>
            }
          />
        )}

        {/* ── Список ───────────────────────────────────────────── */}
        {!isLoading && !isError && overrides.length > 0 && (
          <div className="space-y-3">
            {overrides.map((override) => (
              <OverrideCard
                key={override.id}
                override={override}
                onClick={() =>
                  navigate(
                    `/tenant-admin/instructions/overrides/${override.id}`,
                  )
                }
              />
            ))}
          </div>
        )}

      </div>
    </div>
  );
};

export default TenantOverridesPage;



