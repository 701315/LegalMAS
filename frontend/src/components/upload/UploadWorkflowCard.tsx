// src/components/upload/UploadWorkflowCard.tsx

import React from "react";

const steps = [
  "После выбора файлов и загрузки далее перейдём к блоку запуска анализа документов.",
  "Перед запуском анализа документов необходимо будет выбрать набор рисков для анализа документов.",
  "После запуска программа выполнит extraction, chunking, classification и анализ рисков.",
  "По результатам анализа на выбранные риски программа построит DD Grid рисков документов.",
];

const UploadWorkflowCard: React.FC = () => {
  return (
    <aside className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <div className="flex h-full min-h-[220px] flex-col">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          Workflow
        </div>

        <div className="mt-4 space-y-3">
          {steps.map((step, index) => (
            <div
              key={index}
              className="rounded-[18px] border border-[var(--border-soft)] bg-[var(--bg-base)] px-3 py-3"
            >
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-primary)] text-[11px] font-semibold text-white">
                  {index + 1}
                </div>
                <p className="text-xs leading-5 text-[var(--text-secondary)]">
                  {step}
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


