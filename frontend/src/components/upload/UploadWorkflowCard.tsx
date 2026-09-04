// src/components/upload/UploadWorkflowCard.tsx

import React from "react";
import { useTranslation } from "react-i18next";

const STEP_KEYS = [
  "upload.workflow.step1",
  "upload.workflow.step2",
  "upload.workflow.step3",
  "upload.workflow.step4",
] as const;

const UploadWorkflowCard: React.FC = () => {
  const { t } = useTranslation("documents");

  return (
    <aside className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <div className="flex h-full min-h-[220px] flex-col">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          {t("upload.workflow.title")}
        </div>

        <div className="mt-4 space-y-3">
          {STEP_KEYS.map((key, index) => (
            <div
              key={key}
              className="rounded-[18px] border border-[var(--border-soft)] bg-[var(--bg-base)] px-3 py-3"
            >
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-primary)] text-[11px] font-semibold text-white">
                  {index + 1}
                </div>
                <p className="text-xs leading-5 text-[var(--text-secondary)]">
                  {t(key)}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
};

export default UploadWorkflowCard;



