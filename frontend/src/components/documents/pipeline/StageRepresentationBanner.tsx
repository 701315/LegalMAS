// =============================================================
// src/components/documents/pipeline/StageRepresentationBanner.tsx
// =============================================================

import React from "react";
import { Braces, Sparkles, Database, FileText } from "lucide-react";
import type {
  StageMetaDTO,
  StageRepresentationDTO,
} from "../../../types";

interface Props {
  representation: StageRepresentationDTO;
  meta: StageMetaDTO | null;
}

function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function MetaPill({
  children,
  tone = "neutral",
  icon,
  title,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "accent" | "warning" | "success";
  icon?: React.ReactNode;
  title?: string;
}) {
  const toneClasses =
    tone === "accent"
      ? "border-[color:color-mix(in_oklab,var(--color-primary)_25%,transparent)] bg-[var(--color-primary-highlight)] text-[var(--color-primary)]"
      : tone === "warning"
        ? "border-[color:color-mix(in_oklab,var(--color-warning)_30%,transparent)] bg-[var(--color-warning-highlight)] text-[var(--color-warning)]"
        : tone === "success"
          ? "border-[color:color-mix(in_oklab,var(--color-success)_28%,transparent)] bg-[var(--color-success-highlight)] text-[var(--color-success)]"
          : "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";

  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] leading-none",
        toneClasses,
      )}
    >
      {icon ? <span className="shrink-0">{icon}</span> : null}
      <span>{children}</span>
    </span>
  );
}

export const StageRepresentationBanner: React.FC<Props> = ({
  representation,
  meta,
}) => {
  const isCanonical = representation.is_canonical;
  const previewSourceLabel = representation.provenance?.preview_source_label;
  const textEnriched = meta?.text_enriched === true;

  const modeLabel = isCanonical ? "Canonical" : "Friendly";
  const modeHint = isCanonical
    ? "Каноническое представление стадии"
    : "Дружественное представление стадии";

  const localizedRepresentationLabel =
    representation.label ||
    (isCanonical ? "Каноническое представление" : "Дружественное представление");

  const localizedDescription =
    representation.description ||
    (isCanonical
      ? "Отображаются канонические данные стадии без дополнительного пользовательского обогащения."
      : "Отображаются данные стадии в пользовательском режиме просмотра.");

  const localizedPreviewSource =
    previewSourceLabel === "CHUNKS"
      ? "Источник preview: CHUNKS"
      : previewSourceLabel
        ? `Источник preview: ${previewSourceLabel}`
        : null;

  const localizedEnrichment = textEnriched
    ? "Текст обогащён из CHUNKS"
    : null;

  const shouldRender =
    Boolean(localizedRepresentationLabel) ||
    Boolean(localizedDescription) ||
    Boolean(localizedPreviewSource) ||
    Boolean(localizedEnrichment);

  if (!shouldRender) {
    return null;
  }

  return (
    <section
      aria-label="Режим представления стадии"
      className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-5 py-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <MetaPill
          tone={isCanonical ? "neutral" : "accent"}
          icon={
            isCanonical ? (
              <Braces size={12} aria-hidden="true" />
            ) : (
              <Sparkles size={12} aria-hidden="true" />
            )
          }
          title={modeHint}
        >
          {modeLabel}
        </MetaPill>

        <span className="text-sm font-medium text-[var(--text-primary)]">
          {localizedRepresentationLabel}
        </span>

        {localizedPreviewSource && (
          <MetaPill
            tone="warning"
            icon={<Database size={12} aria-hidden="true" />}
            title="Источник данных preview"
          >
            {localizedPreviewSource}
          </MetaPill>
        )}

        {localizedEnrichment && (
          <MetaPill
            tone="success"
            icon={<FileText size={12} aria-hidden="true" />}
            title="Текстовое обогащение"
          >
            {localizedEnrichment}
          </MetaPill>
        )}
      </div>

      {localizedDescription && (
        <p className="mt-2 max-w-5xl text-[12px] leading-5 text-[var(--text-muted)]">
          {localizedDescription}
        </p>
      )}
    </section>
  );
};

export default StageRepresentationBanner;



