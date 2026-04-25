// =============================================================
// src/components/documents/pipeline/StageRepresentationBanner.tsx
// =============================================================

import React from "react";
import type {
  StageMetaDTO,
  StageRepresentationDTO,
} from "../../../types";

interface Props {
  representation: StageRepresentationDTO;
  meta: StageMetaDTO | null;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
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

  const modeToneClasses = isCanonical
    ? "border-slate-300 bg-slate-100 text-slate-700"
    : "border-blue-300 bg-blue-50 text-blue-700";

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
    <div className="border-b bg-gray-50 px-5 py-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-600">
        <span
          className={cx(
            "inline-flex items-center rounded-full border px-2 py-0.5 font-medium",
            modeToneClasses
          )}
          title={modeHint}
        >
          {modeLabel}
        </span>

        <span className="font-medium text-gray-800">
          {localizedRepresentationLabel}
        </span>

        {localizedPreviewSource && (
          <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-amber-700">
            {localizedPreviewSource}
          </span>
        )}

        {localizedEnrichment && (
          <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-emerald-700">
            {localizedEnrichment}
          </span>
        )}
      </div>

      {localizedDescription && (
        <p className="mt-1 text-[11px] leading-4 text-gray-500">
          {localizedDescription}
        </p>
      )}
    </div>
  );
};

export default StageRepresentationBanner;




