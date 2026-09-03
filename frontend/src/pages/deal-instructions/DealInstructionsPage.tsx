// src/pages/deal-instructions/DealInstructionsPage.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { GitBranch } from "lucide-react";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";

const DealInstructionsPage: React.FC = () => {
  const { t } = useTranslation("instructions");
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <InstructionPageHeader
          breadcrumbs={[
            { label: t("deal.breadcrumbs.project"), to: `/projects/${dealId}` },
            { label: t("deal.breadcrumbs.instructions") },
          ]}
          title={t("deal.instructionsPage.title")}
          subtitle={t("deal.instructionsPage.subtitle")}
        />

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() =>
              navigate(`/projects/${dealId}/instructions/overrides`)
            }
            className="block rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 text-left transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                <GitBranch
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              </div>
              <div>
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("deal.instructionsPage.overridesCard.title")}
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  {t("deal.instructionsPage.overridesCard.description")}
                </div>
              </div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
};

export default DealInstructionsPage;


