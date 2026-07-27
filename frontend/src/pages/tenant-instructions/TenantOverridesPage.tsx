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

/* ── Override card ─────────────────────────────────────────── */

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
      className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md"
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

/* ── Page ───────────────────────────────────────────────────── */

const TenantOverridesPage: React.FC = () => {
  const navigate = useNavigate();
  const { tenantId: authTenantId } = useAuth();
  const tenantId = authTenantId ?? "";

  const { data, isLoading, isError } = useTenantOverrides(
    tenantId || null,
  );

  const overrides = data?.items ?? [];
  const activeCount = overrides.filter((o) => o.status === "active").length;
  const draftCount = overrides.filter((o) => o.status === "draft").length;
  const staleCount = overrides.filter((o) => o.is_stale).length;

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">
        {/* Back-link */}
        <button
          type="button"
          onClick={() => navigate("/tenant-admin/instructions")}
          className="flex shrink-0 items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Инструкции
        </button>

        {/* Header */}
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              Instruction Overrides
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Переопределения инструкций на уровне tenant. Применяются поверх
              базовых published-версий.
            </p>
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
        </header>

        {/* Inline stats */}
        {!isLoading && !isError && overrides.length > 0 && (
          <p className="text-sm text-[var(--text-muted)]">
            Всего:{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {overrides.length}
            </span>
            <span className="mx-1.5">·</span>
            Active:{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {activeCount}
            </span>
            <span className="mx-1.5">·</span>
            Draft:{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {draftCount}
            </span>
            {staleCount > 0 && (
              <>
                <span className="mx-1.5">·</span>
                Stale:{" "}
                <span className="font-semibold text-rose-600">
                  {staleCount}
                </span>
              </>
            )}
          </p>
        )}

        {/* Stale warning */}
        {staleCount > 0 && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            {staleCount}{" "}
            {staleCount === 1 ? "override устарел" : "overrides устарели"} —
            базовая версия инструкции была обновлена. Создайте новые overrides
            на актуальной версии.
          </div>
        )}

        {/* Content */}
        {isLoading && <LoadingBlock text="Загружаем overrides…" rows={4} />}

        {isError && (
          <InlineAlert
            tone="error"
            message="Не удалось загрузить overrides. Проверьте подключение."
          />
        )}

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


