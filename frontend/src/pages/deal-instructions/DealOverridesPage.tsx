// src/pages/deal-instructions/DealOverridesPage.tsx

import React from "react";
import { useTranslation } from "react-i18next";
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

const OverrideCard: React.FC<OverrideCardProps> = ({ override, onClick }) => {
  const { t } = useTranslation("instructions");
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-left text-xs transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-[var(--text-primary)]">
              {override.global_instruction_version_id
                ? t("deal.overridesPage.card.globalOverride")
                : t("deal.overridesPage.card.dealOverride")}
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
            {t("deal.overridesPage.card.patchOpsCount", { count: override.patch_ops.length })} · {t("deal.overridesPage.card.patchOpsBase")}:{" "}
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
};

const DealOverridesPage: React.FC = () => {
  const { t } = useTranslation("instructions");
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
            { label: t("deal.breadcrumbs.project"), to: `/projects/${dealId}` },
            {
              label: t("deal.breadcrumbs.instructions"),
              to: `/projects/${dealId}/instructions`,
            },
            { label: t("deal.breadcrumbs.overrides") },
          ]}
          title={t("deal.overridesPage.title")}
          subtitle={t("deal.overridesPage.subtitle")}
          rightSlot={
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refetch()}
                aria-label={t("actions.refresh", { ns: "common" }) || "Refresh"}
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  navigate(`/projects/${dealId}/instructions/overrides/new`)
                }
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                {t("deal.overridesPage.newButton")}
              </Button>
            </div>
          }
        />

        {staleCount > 0 && (
          <div className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-2.5">
            <span className="text-[11px] text-[var(--color-warning-text)]">
              {t("deal.overridesPage.staleCount", { count: staleCount })}
            </span>
          </div>
        )}

        <PageSection title={t("deal.overridesPage.sectionTitle")}>
          {isLoading && (
            <LoadingBlock text={t("deal.overridesPage.loading")} rows={3} />
          )}
          {isError && (
            <InlineAlert
              tone="error"
              message={t("deal.overridesPage.loadError")}
            />
          )}
          {!isLoading && !isError && overrides.length === 0 && (
            <EmptyState
              title={t("deal.overridesPage.empty.title")}
              description={t("deal.overridesPage.empty.description")}
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    navigate(`/projects/${dealId}/instructions/overrides/new`)
                  }
                >
                  {t("deal.overridesPage.empty.action")}
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



