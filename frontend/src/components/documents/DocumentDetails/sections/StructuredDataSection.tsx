// =============================================================
// StructuredDataSection.tsx
// =============================================================

import React from "react";
import Button from "../../../ui/Button";
import type { ExtractedValue } from "../../../../types";

type StructuredSegmentGroup = {
  segmentKey: string;
  segmentId: string | null;
  segmentType: string | null;
  segmentTitle: string | null;
  segmentOrder: number | null;
  isPrimarySegment: boolean | null;
  values: ExtractedValue[];
};

interface StructuredDataSectionProps {
  structuredNotAvailable?: boolean;
  structuredData: {
    extracted_values: ExtractedValue[];
  } | null;
  structuredSegments: StructuredSegmentGroup[];
  resolvedActiveSegmentKey: string | null;
  onSetActiveSegmentKey: (segmentKey: string | null) => void;
  onOpenAtLocation?: (payload: {
    page?: number;
    clauseUid?: string;
    segmentId?: string;
    chunkId?: string;
    chunkIndex?: number;
  }) => void;
}

function getSegmentLabel(segment: StructuredSegmentGroup): string {
  if (segment.segmentTitle && segment.segmentTitle.trim()) {
    return segment.segmentTitle.trim();
  }

  if (segment.segmentType && segment.segmentType.trim()) {
    return segment.segmentType.trim();
  }

  return "Документ целиком";
}

function getSegmentMetaLabel(segment: StructuredSegmentGroup): string | null {
  const parts: string[] = [];

  if (segment.isPrimarySegment) {
    parts.push("Основной сегмент");
  }

  if (segment.segmentType && segment.segmentTitle) {
    parts.push(segment.segmentType);
  }

  if (segment.segmentOrder !== null && segment.segmentOrder !== undefined) {
    parts.push(`Порядок: ${segment.segmentOrder}`);
  }

  return parts.length ? parts.join(" · ") : null;
}

function getCompositionBannerText(segments: StructuredSegmentGroup[]): string {
  const actualSegments = segments.filter((s) => s.segmentId !== null);

  if (actualSegments.length <= 1) {
    return "Single-document";
  }

  return `Multi-document · ${actualSegments.length} segments`;
}

function getPrimarySegment(
  segments: StructuredSegmentGroup[],
): StructuredSegmentGroup | null {
  return (
    segments.find((segment) => segment.isPrimarySegment) ??
    segments.find((segment) => segment.segmentId !== null) ??
    null
  );
}

function getCompositionBannerDescription(
  segments: StructuredSegmentGroup[],
): string {
  const actualSegments = segments.filter((s) => s.segmentId !== null);

  if (actualSegments.length <= 1) {
    return "Файл анализируется как единый документ. Извлечённые значения показаны в одном общем контексте.";
  }

  return "Файл содержит несколько логических сегментов. Извлечённые значения сгруппированы по сегментам.";
}

function groupSegmentValuesByCheck(
  values: ExtractedValue[],
): Record<string, ExtractedValue[]> {
  const STRUCTURED_CHECK_TITLES: Record<string, string> = {
    overall_risk: "Общий уровень риска",
    confidentiality: "Конфиденциальность",
    governing_law: "Применимое право и подсудность",
    authority_and_approvals: "Полномочия и корпоративные одобрения",
    price_and_payment: "Цена и порядок оплаты",
    real_estate_core: "Основные параметры объекта недвижимости",
  };

  const getStructuredGroupTitle = (checkName: string): string => {
    const key = checkName.trim();
    if (STRUCTURED_CHECK_TITLES[key]) {
      return STRUCTURED_CHECK_TITLES[key];
    }
    return checkName || "Другие параметры";
  };

  return values.reduce<Record<string, ExtractedValue[]>>((acc, val) => {
    const rawKey = val.check_name || val.check_id || "other";
    const groupKey = getStructuredGroupTitle(rawKey);

    if (!acc[groupKey]) {
      acc[groupKey] = [];
    }

    acc[groupKey].push(val);
    return acc;
  }, {});
}

export const StructuredDataSection: React.FC<StructuredDataSectionProps> = ({
  structuredNotAvailable,
  structuredData,
  structuredSegments,
  resolvedActiveSegmentKey,
  onSetActiveSegmentKey,
  onOpenAtLocation,
}) => {
  const hasMultipleSegments = structuredSegments.length > 1;

  const primarySegment = getPrimarySegment(structuredSegments);
  const primarySegmentLabel = primarySegment
    ? getSegmentLabel(primarySegment)
    : null;
  const compositionText = getCompositionBannerText(structuredSegments);
  const compositionDescription =
    getCompositionBannerDescription(structuredSegments);

  const visibleSegments = resolvedActiveSegmentKey
    ? structuredSegments.filter(
        (s) => s.segmentKey === resolvedActiveSegmentKey,
      )
    : structuredSegments;

  const handleOpenExtractedValue = (
    val: ExtractedValue,
    segment: StructuredSegmentGroup,
  ) => {
    if (!onOpenAtLocation) return;

    onOpenAtLocation({
      page: val.page ?? undefined,
      clauseUid: val.clause_uid ?? undefined,
      segmentId: segment.segmentId ?? undefined,
      chunkId: val.chunk_id ?? undefined,
      chunkIndex: val.chunk_index ?? undefined,
    });
  };

  if (structuredNotAvailable) {
    return (
      <p className="text-xs text-[var(--text-primary)]">
        Для этого документа пока нет извлечённых значений. Запустите анализ
        или обновите страницу после завершения проверки.
      </p>
    );
  }

  if (!structuredData || structuredData.extracted_values.length === 0) {
    return (
      <p className="text-xs text-[var(--text-primary)]">
        Структурированные данные находятся в обработке. Обновите страницу
        через несколько минут после завершения анализа.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {/* Composition banner */}
      <div className="rounded-2xl border border-[var(--color-blue)]/20 bg-[var(--color-blue-highlight)] px-3 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs font-medium text-[var(--text-primary)]">
            Состав файла
          </span>
          <span className="text-xs text-[var(--text-primary)]">
            {compositionText}
          </span>
        </div>

        <p className="mt-1 text-xs leading-5 text-[var(--text-primary)]">
          {compositionDescription}
        </p>

        {primarySegmentLabel && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-xs text-[var(--text-primary)]">
              Основной сегмент:
            </span>
            <span className="inline-flex items-center rounded-full bg-[var(--bg-card)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-primary)] shadow-sm">
              {primarySegmentLabel}
            </span>
          </div>
        )}
      </div>

      {hasMultipleSegments && (
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-[var(--text-primary)]">
            Сегменты
          </div>

          <div
            className="flex flex-wrap gap-1.5"
            role="tablist"
            aria-label="Сегменты документа"
          >
            {structuredSegments.map((segment) => {
              const label = getSegmentLabel(segment);
              const isActive =
                resolvedActiveSegmentKey === segment.segmentKey;

              return (
                <button
                  key={segment.segmentKey}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => onSetActiveSegmentKey(segment.segmentKey)}
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] transition ${
                    isActive
                      ? "bg-[var(--accent-primary)] text-[var(--text-inverse)] shadow-sm"
                      : "border border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:bg-[var(--bg-elevated-soft)]"
                  }`}
                >
                  <span>{label}</span>
                  {segment.isPrimarySegment && (
                    <span
                      className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                        isActive
                          ? "bg-white/20 text-white"
                          : "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
                      }`}
                    >
                      Основной
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="max-h-72 space-y-3 overflow-y-auto pr-1">
        {visibleSegments.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3 py-4 text-center">
            <p className="text-xs font-medium text-[var(--text-primary)]">
              Для выбранного сегмента пока нет данных.
            </p>
            <p className="mt-1 text-xs text-[var(--text-primary)]">
              Попробуйте выбрать другой сегмент или обновите страницу
              после завершения анализа.
            </p>
          </div>
        ) : (
          visibleSegments.map((segment) => {
            const groups = groupSegmentValuesByCheck(segment.values);
            const groupEntries = Object.entries(groups);
            const segmentLabel = getSegmentLabel(segment);
            const segmentMeta = getSegmentMetaLabel(segment);

            return (
              <div
                key={segment.segmentKey}
                className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2.5"
              >
                <div className="mb-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs font-semibold text-[var(--text-primary)]">
                      {segmentLabel}
                    </p>
                    {segment.isPrimarySegment && (
                      <span className="inline-flex items-center rounded-full bg-[var(--accent-muted)] px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
                        Основной сегмент
                      </span>
                    )}
                  </div>

                  {segmentMeta && (
                    <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                      {segmentMeta}
                    </p>
                  )}

                  {segment.segmentId && (
                    <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                      segment_id: {segment.segmentId}
                    </p>
                  )}
                </div>

                {groupEntries.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-3 text-center">
                    <p className="text-xs text-[var(--text-primary)]">
                      В этом сегменте пока нет извлечённых значений.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {groupEntries.map(([groupTitle, values]) => (
                      <div
                        key={`${segment.segmentKey}-${groupTitle}`}
                        className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-2"
                      >
                        <p className="mb-1 text-xs font-semibold text-[var(--text-primary)]">
                          {groupTitle}
                        </p>

                        <div className="space-y-0.5">
                          {values.map((val, idx) => (
                            <div
                              key={`${val.check_id}-${val.field_name}-${idx}`}
                              className="flex justify-between gap-3 border-b border-[var(--border-subtle)] py-1 text-[11px] last:border-0"
                            >
                              <div className="min-w-0 flex-1">
                                <span className="text-[var(--text-primary)]">
                                  {val.field_name.replace(/_/g, " ")}
                                </span>

                                {(val.page || val.clause_uid) && (
                                  <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                                    {val.page ? `стр. ${val.page}` : ""}
                                    {val.page && val.clause_uid ? " · " : ""}
                                    {val.clause_uid
                                      ? `clause: ${val.clause_uid}`
                                      : ""}
                                  </div>
                                )}
                              </div>

                              <div className="flex max-w-[60%] shrink-0 items-start gap-2">
                                <span className="break-words text-right text-[11px] font-medium text-[var(--text-primary)]">
                                  {val.field_value}
                                </span>

                                {onOpenAtLocation && (
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    onClick={() =>
                                      handleOpenExtractedValue(val, segment)
                                    }
                                    className="px-2 py-0.5 text-[10px]"
                                  >
                                    Открыть в документе
                                  </Button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};


