// =============================================================
// shared.tsx
// Вспомогательные view-компоненты для DocumentDetails.
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { Document } from "../../../types";

interface SectionProps {
  title: string;
  children: React.ReactNode;
}

export const Section: React.FC<SectionProps> = ({ title, children }) => (
  <section className="space-y-2">
    <h4 className="text-sm font-semibold text-[var(--text-primary)]">
      {title}
    </h4>
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 shadow-xs">
      {children}
    </div>
  </section>
);

interface InfoRowProps {
  label: string;
  value: string;
}

export const InfoRow: React.FC<InfoRowProps> = ({ label, value }) => (
  <div className="flex justify-between py-0.5 text-[11px]">
    <span className="font-medium text-[var(--text-primary)]">{label}</span>
    <span className="max-w-[60%] break-words text-right font-medium text-[var(--text-primary)]">
      {value}
    </span>
  </div>
);

interface FamilyRowProps {
  icon: string;
  label: string;
  doc: Document;
}

export const FamilyRow: React.FC<FamilyRowProps> = ({ icon, label, doc }) => {
  const { t } = useTranslation("documents");

  return (
    <div className="flex items-center justify-between border-b border-[var(--border-subtle)] py-1 text-xs last:border-0">
      <div className="flex min-w-0 items-center gap-2">
        <span className="text-base">{icon}</span>
        <div className="min-w-0">
          <p className="truncate font-medium text-[var(--text-primary)]">
            {doc.filename}
          </p>
          <p className="truncate text-[11px] text-[var(--text-primary)]">
            {label} · {doc.doc_type || t("shared.docTypeNotSpecified")}
          </p>
        </div>
      </div>
    </div>
  );
};



