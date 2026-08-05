// =============================================================
// src/pages/tabs/overview/DocumentsOverviewWidget.tsx
// Виджет "Обзор документов" — общая статистика по загруженным
// документам проекта: количество, статусы обработки, топ типов.
//
// Внутри виджета:
//   1) Блок "Документы в проекте" — счётчики.
//   2) Блок "По типам документов" — топ-5 типов.
//   3) Блок "Требует внимания" — про низкую classification_confidence
//      (< 0.6). Показывает счётчик + первые 3 файла, БЕЗ отдельной
//      кнопки перехода — переход единый снизу.
//   4) Отдельная кнопка "Перейти к списку документов" — всегда внизу,
//      если в проекте есть хотя бы один документ.
// =============================================================

import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { DocumentListItem } from "../../../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LOW_CONFIDENCE_THRESHOLD = 0.6;
const MAX_ITEMS_IN_LIST = 3;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const READY_STATUSES = new Set<string>(["completed"]);
const ERROR_STATUSES = new Set<string>(["failed", "quarantine"]);

interface DocumentsOverviewData {
  total: number;
  ready: number;
  errors: number;
  inProgress: number;
  topDocTypes: Array<{ docType: string; count: number }>;
}

interface LowConfidenceItem {
  documentId: string;
  filename: string;
  confidence: number | null;
}

function buildOverviewData(
  documents: DocumentListItem[],
): DocumentsOverviewData {
  const total = documents.length;
  let ready = 0;
  let errors = 0;
  const docTypeMap = new Map<string, number>();

  for (const doc of documents) {
    if (READY_STATUSES.has(doc.status)) ready++;
    else if (ERROR_STATUSES.has(doc.status)) errors++;

    const docType = doc.doc_type?.trim();
    if (docType) {
      docTypeMap.set(docType, (docTypeMap.get(docType) ?? 0) + 1);
    }
  }

  const inProgress = Math.max(0, total - ready - errors);

  const topDocTypes = [...docTypeMap.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([docType, count]) => ({ docType, count }));

  return { total, ready, errors, inProgress, topDocTypes };
}

function buildLowConfidenceList(
  documents: DocumentListItem[],
): LowConfidenceItem[] {
  return documents
    .filter(
      (doc) =>
        doc.classification_confidence !== null &&
        doc.classification_confidence !== undefined &&
        doc.classification_confidence < LOW_CONFIDENCE_THRESHOLD,
    )
    .map((doc) => ({
      documentId: doc.id,
      filename: doc.filename,
      confidence: doc.classification_confidence ?? null,
    }))
    .sort((a, b) => (a.confidence ?? 0) - (b.confidence ?? 0));
}

function truncateFilename(filename: string, maxLength = 24): string {
  if (filename.length <= maxLength) return filename;
  const ext = filename.split(".").pop();
  const base = filename.slice(0, maxLength - 4 - (ext?.length ?? 0));
  return ext ? `${base}…${ext}` : `${base}…`;
}

function formatConfidencePercent(confidence: number | null): string {
  if (confidence === null) return "";
  return `${Math.round(confidence * 100)}%`;
}

/**
 * Плюрализация "документов" по русским правилам.
 */
function pluralizeDocumentsGenitive(count: number): string {
  const mod10 = Math.abs(count) % 10;
  const mod100 = Math.abs(count) % 100;
  if (mod100 >= 11 && mod100 <= 19) return "документов";
  if (mod10 === 1) return "документа";
  if (mod10 >= 2 && mod10 <= 4) return "документов";
  return "документов";
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

const DocumentsOverviewSkeleton: React.FC = () => (
  <div className="animate-pulse space-y-2">
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
      <div className="h-3 w-24 rounded bg-[var(--bg-elevated-soft)]" />
      <div className="mt-2 grid grid-cols-3 gap-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 rounded-lg bg-[var(--bg-elevated-soft)]" />
        ))}
      </div>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Low confidence item row
// ---------------------------------------------------------------------------

interface LowConfidenceRowProps {
  filename: string;
  confidence: number | null;
  onClick: () => void;
}

const LowConfidenceRow: React.FC<LowConfidenceRowProps> = ({
  filename,
  confidence,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className="group flex w-full items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-2 py-1.5 text-left transition-colors hover:bg-[var(--bg-elevated-soft)]"
    title={filename}
  >
    <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--text-primary)]">
      {truncateFilename(filename)}
    </span>
    {confidence !== null && (
      <span className="shrink-0 rounded-full bg-[var(--color-warning-bg)] px-1.5 py-0.5 text-[9px] font-semibold tabular-nums text-[var(--color-warning-text)]">
        {formatConfidencePercent(confidence)}
      </span>
    )}
    <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100" />
  </button>
);

// ---------------------------------------------------------------------------
// Widget
// ---------------------------------------------------------------------------

interface DocumentsOverviewWidgetProps {
  documents: DocumentListItem[] | undefined;
  isLoading: boolean;
  isError: boolean;
}

export const DocumentsOverviewWidget: React.FC<
  DocumentsOverviewWidgetProps
> = ({ documents, isLoading, isError }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const handleOpenDocuments = React.useCallback(() => {
    const params = new URLSearchParams(location.search);
    params.set("tab", "documents");
    navigate(
      {
        pathname: location.pathname,
        search: params.toString(),
      },
      { replace: false },
    );
  }, [location.pathname, location.search, navigate]);

  if (isLoading) return <DocumentsOverviewSkeleton />;

  if (isError || !documents) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <p className="text-[11px] text-[var(--text-muted)]">
          Не удалось загрузить документы
        </p>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-4 text-center">
        <p className="text-[11px] text-[var(--text-muted)]">
          Документы ещё не загружены
        </p>
      </div>
    );
  }

  const data = buildOverviewData(documents);
  const lowConfidenceItems = buildLowConfidenceList(documents);
  const visibleLowConfidence = lowConfidenceItems.slice(0, MAX_ITEMS_IN_LIST);
  const hiddenLowConfidenceCount =
    lowConfidenceItems.length - visibleLowConfidence.length;

  const lowConfidenceCounterText = `Требуют уточнения: ${lowConfidenceItems.length} ${pluralizeDocumentsGenitive(
    lowConfidenceItems.length,
  )} с низкой уверенностью классификации.`;

  return (
    <div className="space-y-2">
      {/* Итого */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          Документы в проекте
        </p>
        <p className="mt-1 text-xl font-semibold tracking-tight tabular-nums text-[var(--text-primary)]">
          {data.total}
        </p>

        <div className="mt-3 grid grid-cols-3 gap-2">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-2 py-1.5">
            <p className="text-[10px] text-[var(--text-muted)]">Готовы</p>
            <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--color-success-text)]">
              {data.ready}
            </p>
          </div>
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-2 py-1.5">
            <p className="text-[10px] text-[var(--text-muted)]">В работе</p>
            <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
              {data.inProgress}
            </p>
          </div>
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-2 py-1.5">
            <p className="text-[10px] text-[var(--text-muted)]">Ошибок</p>
            <p
              className={`mt-0.5 text-sm font-semibold tabular-nums ${
                data.errors > 0
                  ? "text-[var(--color-error-text)]"
                  : "text-[var(--text-muted)]"
              }`}
            >
              {data.errors}
            </p>
          </div>
        </div>
      </div>

      {/* По типам */}
      {data.topDocTypes.length > 0 && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
            По типам документов
          </p>
          <div className="space-y-1.5">
            {data.topDocTypes.map(({ docType, count }) => (
              <div
                key={docType}
                className="flex items-center justify-between gap-2"
              >
                <span className="truncate text-xs text-[var(--text-primary)]">
                  {docType}
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-[var(--text-muted)]">
                  {count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Требует внимания к классифицированным документам */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          Требует внимания
        </p>

        {lowConfidenceItems.length === 0 ? (
          <p className="text-[11px] leading-5 text-[var(--text-secondary)]">
            Все документы классифицированы с высоким уровнем
            уверенности. Специального внимания специалиста не
            требуется.
          </p>
        ) : (
          <div className="space-y-1.5">
            <p className="text-[11px] leading-5 text-[var(--text-secondary)]">
              {lowConfidenceCounterText}
            </p>
            <div className="space-y-1">
              {visibleLowConfidence.map((item) => (
                <LowConfidenceRow
                  key={item.documentId}
                  filename={item.filename}
                  confidence={item.confidence}
                  onClick={handleOpenDocuments}
                />
              ))}
            </div>
            {hiddenLowConfidenceCount > 0 && (
              <p className="text-[10px] text-[var(--text-muted)]">
                Ещё {hiddenLowConfidenceCount}…
              </p>
            )}
          </div>
        )}
      </div>

      {/* Отдельная ссылка на страницу со списком документов */}
      <button
        type="button"
        onClick={handleOpenDocuments}
        className="flex w-full items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-left transition-colors hover:bg-[var(--bg-elevated-soft)]"
      >
        <span className="text-xs font-medium text-[var(--text-primary)]">
          Перейти к списку документов
        </span>
        <ChevronRight className="h-3.5 w-3.5 text-[var(--text-muted)]" />
      </button>
    </div>
  );
};

export default DocumentsOverviewWidget;


