// src/pages/deal-instructions/DealOverridesPage.tsx

import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Plus, RefreshCw } from "lucide-react";

import { useDealOverrides } from "../../hooks/instructions/useInstructionOverrides";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import OverrideStatusBadge from "../../components/instructions/OverrideStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import PageSection from "../../components/ui/PageSection";
import type { InstructionOverrideItem } from "../../types/instructions";

interface OverrideCardProps {
  override: InstructionOverrideItem;
  onClick: () => void;
}

const OverrideCard: React.FC<OverrideCardProps> = ({ override, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-left text-xs transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
  >
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-[var(--text-primary)]">
            {override.global_instruction_version_id
              ? "Deal Global Override"
              : "Deal Override"}
          </span>
          <span className="font-mono text-[10px] text-[var(--text-muted)]">
            {override.id.slice(0, 8)}…
          </span>
        </div>
        {override.change_summary && (
          <div className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            {override.change_summary}
          </div>
        )}
        <div className="mt-1 text-[10px] text-[var(--text-muted)]">
          {override.patch_ops.length} patch ops ·{" "}
          base:{" "}
          {override.global_instruction_version_id
            ? `global ${override.global_instruction_version_id.slice(0, 8)}…`
            : override.instruction_version_id
              ? `${override.instruction_version_id.slice(0, 8)}…`
              : "—"}
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

const DealOverridesPage: React.FC = () => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useDealOverrides(
    dealId ?? null,
  );
  const overrides = data?.items ?? [];
  const staleCount = overrides.filter((o) => o.is_stale).length;

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Проект", to: `/projects/${dealId}` },
            {
              label: "Инструкции",
              to: `/projects/${dealId}/instructions`,
            },
            { label: "Overrides" },
          ]}
          title="Deal Overrides"
          subtitle="Переопределения инструкций на уровне проекта."
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
                onClick={() =>
                  navigate(
                    `/projects/${dealId}/instructions/overrides/new`,
                  )
                }
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                Новый override
              </Button>
            </div>
          }
        />

        {staleCount > 0 && (
          <div className="rounded-xl border border-[color:var(--color-warning-border,#fbbf24)] bg-[color:var(--color-warning-bg,#fef9c3)] px-4 py-2.5">
            <span className="text-[11px] text-[color:var(--color-warning-text,#92400e)]">
              {staleCount}{" "}
              {staleCount === 1 ? "override устарел" : "overrides устарели"}.
              Выполните rebase для каждого stale override.
            </span>
          </div>
        )}

        <PageSection title="Overrides">
          {isLoading && (
            <LoadingBlock text="Загружаем overrides..." rows={3} />
          )}
          {isError && (
            <InlineAlert
              tone="error"
              message="Не удалось загрузить overrides проекта."
            />
          )}
          {!isLoading && !isError && overrides.length === 0 && (
            <EmptyState
              title="Overrides не созданы"
              description="Создайте override чтобы переопределить инструкцию для этого проекта."
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    navigate(
                      `/projects/${dealId}/instructions/overrides/new`,
                    )
                  }
                >
                  Создать override
                </Button>
              }
            />
          )}
          {!isLoading && !isError && overrides.length > 0 && (
            <ul className="space-y-2">
              {overrides.map((o) => (
                <li key={o.id}>
                  <OverrideCard
                    override={o}
                    onClick={() =>
                      navigate(
                        `/projects/${dealId}/instructions/overrides/${o.id}`,
                      )
                    }
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

export default DealOverridesPage;


