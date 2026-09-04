// src/components/documents/pipeline/StageRepresentationBanner.tsx

import React from "react";
import { useTranslation } from "react-i18next";
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
      ? "border-[var(--accent-primary)]/25 bg-[var(--accent-subtle)] text-[var(--accent-primary)]"
      : tone === "warning"
        ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]"
        : tone === "success"
          ? "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]"
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
  const { t } = useTranslation("pipeline");

  const isCanonical = representation.is_canonical;
  const previewSourceLabel = representation.provenance?.preview_source_label;
  const textEnriched = meta?.text_enriched === true;

  const modeLabel = isCanonical
    ? t("stageBanner.modeLabelCanonical")
    : t("stageBanner.modeLabelFriendly");

  const modeHint = isCanonical
    ? t("stageBanner.modeHintCanonical")
    : t("stageBanner.modeHintFriendly");

  const localizedRepresentationLabel =
    representation.label ||
    (isCanonical
      ? t("stageBanner.defaultCanonicalLabel")
      : t("stageBanner.defaultFriendlyLabel"));

  const localizedDescription =
    representation.description ||
    (isCanonical
      ? t("stageBanner.defaultCanonicalDesc")
      : t("stageBanner.defaultFriendlyDesc"));

  const localizedPreviewSource = previewSourceLabel
    ? t("stageBanner.previewSource", { source: previewSourceLabel })
    : null;

  const localizedEnrichment = textEnriched
    ? t("stageBanner.textEnriched")
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
      aria-label={t("stageBanner.ariaLabel")}
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
            title={t("stageBanner.previewSourceTitle")}
          >
            {localizedPreviewSource}
          </MetaPill>
        )}

        {localizedEnrichment && (
          <MetaPill
            tone="success"
            icon={<FileText size={12} aria-hidden="true" />}
            title={t("stageBanner.textEnrichmentTitle")}
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


