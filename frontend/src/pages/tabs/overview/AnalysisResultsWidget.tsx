// =============================================================
// src/pages/tabs/overview/AnalysisResultsWidget.tsx
// Виджет "Итог анализа" — сводка по проверкам последнего run.
//
// Секции:
//   1) Выполнено проверок X/X + прогресс-бар.
//   2) Обнаруженные проблемы (если есть failed/quarantine).
//   3) Результаты, требующие уточнения — findings с
//      review_status === "unclear", сгруппированные по документу.
//      Это те самые findings, которые в DD Grid отображаются как
//      "Результат не определён LLM на 100%".
//      Внутри блока — только счётчик + первые 3 файла, БЕЗ отдельной
//      кнопки перехода — переход единый снизу.
//   4) Отдельная кнопка "Перейти к списку результатов" —
//      всегда внизу, если анализ завершён.
//      Ведёт в DD Grid list mode без применения фильтра
//      "Скрыть pass" — пользователь сам выбирает что показывать.
//
// Заголовок "Итог анализа" рендерится внешним ColumnShell,
// внутри виджета его нет.
// =============================================================

import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useRun } from "../../../api/runs";
import { useDealReviewDdGridV1 } from "../../../api/dealReview";
import { useDDGridV1UIStore } from "../dd-grid-v1/ddGridV1.collapseStore";
import { selectDDGridV1DerivedModel } from "../dd-grid-v1/ddGridV1.selectors";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_ITEMS_IN_LIST = 3;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface UnclearFindingsItem {
  documentId: string;
  filename: string;
  unclearCount: number;
}

function truncateFilename(filename: string, maxLength = 24): string {
  if (filename.length <= maxLength) return filename;
  const ext = filename.split(".").pop();
  const base = filename.slice(0, maxLength - 4 - (ext?.length ?? 0));
  return ext ? `${base}…${ext}` : `${base}…`;
}

/**
 * Плюрализация "проверок" по русским правилам.
 */
function pluralizeChecks(count: number): string {
  const mod10 = Math.abs(count) % 10;
  const mod100 = Math.abs(count) % 100;
  if (mod100 >= 11 && mod100 <= 19) return "проверок";
  if (mod10 === 1) return "проверка";
  if (mod10 >= 2 && mod10 <= 4) return "проверки";
  return "проверок";
}

/**
 * Плюрализация "документах" по русским правилам.
 */
function pluralizeDocuments(count: number): string {
  const mod10 = Math.abs(count) % 10;
  const mod100 = Math.abs(count) % 100;
  if (mod100 >= 11 && mod100 <= 19) return "документах";
  if (mod10 === 1) return "документе";
  if (mod10 >= 2 && mod10 <= 4) return "документах";
  return "документах";
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

const AnalysisResultsSkeleton: React.FC = () => (
  <div className="animate-pulse space-y-2">
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
      <div className="h-3 w-24 rounded bg-[var(--bg-elevated-soft)]" />
      <div className="mt-2 h-8 w-20 rounded bg-[var(--bg-elevated-soft)]" />
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Unclear findings item row
// ---------------------------------------------------------------------------

interface UnclearFindingsRowProps {
  filename: string;
  unclearCount: number;
  onClick: () => void;
}

const UnclearFindingsRow: React.FC<UnclearFindingsRowProps> = ({
  filename,
  unclearCount,
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
    <span className="shrink-0 rounded-full bg-[var(--color-warning-bg)] px-1.5 py-0.5 text-[9px] font-semibold tabular-nums text-[var(--color-warning-text)]">
      {unclearCount}
    </span>
    <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100" />
  </button>
);

// ---------------------------------------------------------------------------
// Widget
// ---------------------------------------------------------------------------

interface AnalysisResultsWidgetProps {
  dealId: string;
  runId: string | null;
}

export const AnalysisResultsWidget: React.FC<
  AnalysisResultsWidgetProps
> = ({ dealId, runId }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: run, isLoading, isError } = useRun(runId, false);
  const { data: ddGridResponse } = useDealReviewDdGridV1(dealId, runId);

  const ddGridModel = React.useMemo(
    () => selectDDGridV1DerivedModel(ddGridResponse ?? null),
    [ddGridResponse],
  );

  // Findings с review_status === "unclear", сгруппированные по документу.
  const unclearFindingsItems = React.useMemo<UnclearFindingsItem[]>(() => {
    if (!ddGridResponse) return [];

    const documentMap = new Map<
      string,
      { filename: string; unclearCount: number }
    >();

    for (const row of ddGridModel.rows) {
      const drawerByCheck = ddGridModel.drawerContents[row.documentId] ?? {};

      for (const drawer of Object.values(drawerByCheck)) {
        if (!drawer) continue;
        if (drawer.review_status === "unclear") {
          const existing = documentMap.get(row.documentId);
          if (existing) {
            existing.unclearCount += 1;
          } else {
            documentMap.set(row.documentId, {
              filename: row.filename || "[no name]",
              unclearCount: 1,
            });
          }
        }
      }
    }

    return [...documentMap.entries()]
      .map(([documentId, meta]) => ({
        documentId,
        filename: meta.filename,
        unclearCount: meta.unclearCount,
      }))
      .sort((a, b) => b.unclearCount - a.unclearCount);
  }, [ddGridModel, ddGridResponse]);

  // Общий счётчик findings и документов
  const totalUnclearFindingsCount = React.useMemo(
    () =>
      unclearFindingsItems.reduce((sum, item) => sum + item.unclearCount, 0),
    [unclearFindingsItems],
  );

  const affectedDocumentsCount = unclearFindingsItems.length;

  // Клик по файлу в списке unclear findings — переход в DD Grid list mode
  // с включённым фильтром "Скрыть pass", чтобы юрист сразу увидел
  // только проблемные findings.
  const handleOpenUnclearInDDGrid = React.useCallback(() => {
    const store = useDDGridV1UIStore.getState();
    store.setFormat("list");
    store.setShowPassInList(false);

    const params = new URLSearchParams(location.search);
    params.set("tab", "dd_grid");
    navigate(
      {
        pathname: location.pathname,
        search: params.toString(),
      },
      { replace: false },
    );
  }, [location.pathname, location.search, navigate]);

  // Клик по нижней кнопке "Перейти к списку результатов" — переход
  // в DD Grid list mode БЕЗ применения фильтра "Скрыть pass".
  // Пользователь сам решает какие результаты показывать.
  const handleOpenAllResultsInDDGrid = React.useCallback(() => {
    const store = useDDGridV1UIStore.getState();
    store.setFormat("list");
    store.setShowPassInList(true);

    const params = new URLSearchParams(location.search);
    params.set("tab", "dd_grid");
    navigate(
      {
        pathname: location.pathname,
        search: params.toString(),
      },
      { replace: false },
    );
  }, [location.pathname, location.search, navigate]);

  if (!runId) {
    return (
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-4 text-center">
        <p className="text-[11px] text-[var(--text-muted)]">
          Анализ ещё не запускался
        </p>
        <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
          Результаты появятся после первого запуска
        </p>
      </div>
    );
  }

  if (isLoading) return <AnalysisResultsSkeleton />;

  if (isError || !run) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <p className="text-[11px] text-[var(--text-muted)]">
          Не удалось загрузить результаты
        </p>
      </div>
    );
  }

  const totalChecks = run.total_checks ?? 0;
  const completedChecks = run.completed_checks ?? 0;
  const hasErrors = run.has_errors ?? false;
  const failedDocs = run.failed_docs_count ?? 0;
  const quarantineDocs = run.quarantine_docs_count ?? 0;

  const isRunning =
    run.status === "pending" || run.status === "running";

  const progressPercent =
    totalChecks > 0 ? Math.round((completedChecks / totalChecks) * 100) : 0;

  const canOpenDDGrid =
    run.status === "completed" || run.status === "completed_with_errors";

  const visibleUnclearFindings = unclearFindingsItems.slice(0, MAX_ITEMS_IN_LIST);
  const hiddenUnclearFindingsCount =
    unclearFindingsItems.length - visibleUnclearFindings.length;

  const counterText = `Требуют уточнения: ${totalUnclearFindingsCount} ${pluralizeChecks(
    totalUnclearFindingsCount,
  )} в ${affectedDocumentsCount} ${pluralizeDocuments(affectedDocumentsCount)}.`;

  return (
    <div className="space-y-2">
      {/* Основная карточка со счётчиком */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="text-[10px] text-[var(--text-muted)]">
              Выполнено проверок
            </p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-[var(--text-primary)]">
              {completedChecks}
              <span className="text-sm font-normal text-[var(--text-muted)]">
                {" / "}
                {totalChecks}
              </span>
            </p>
          </div>

          {isRunning && (
            <span className="shrink-0 rounded-full bg-[var(--accent-muted)] px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.08em] text-[var(--accent-primary)]">
              Идёт анализ
            </span>
          )}
        </div>

        {/* Progress bar */}
        {totalChecks > 0 && (
          <div className="mt-3">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">
              <div
                className="h-full rounded-full bg-[var(--accent-primary)] transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <p className="mt-1 text-[10px] text-[var(--text-muted)]">
              {progressPercent}% готово
            </p>
          </div>
        )}
      </div>

      {/* Проблемы — только если есть */}
      {(hasErrors || failedDocs > 0 || quarantineDocs > 0) && (
        <div className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--color-warning-text)]">
            Обнаружены проблемы
          </p>
          <div className="mt-1.5 space-y-1">
            {failedDocs > 0 && (
              <p className="text-[11px] text-[var(--color-warning-text)]">
                Ошибки обработки: {failedDocs}
              </p>
            )}
            {quarantineDocs > 0 && (
              <p className="text-[11px] text-[var(--color-warning-text)]">
                В карантине: {quarantineDocs}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Результаты, требующие уточнения — findings с review_status === "unclear" */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          Результаты, требующие уточнения
        </p>

        {unclearFindingsItems.length === 0 ? (
          <p className="text-[11px] leading-5 text-[var(--text-secondary)]">
            Нет проверок, требующих уточнения. Специального внимания
            не требуется.
          </p>
        ) : (
          <div className="space-y-1.5">
            <p className="text-[11px] leading-5 text-[var(--text-secondary)]">
              {counterText}
            </p>
            <div className="space-y-1">
              {visibleUnclearFindings.map((item) => (
                <UnclearFindingsRow
                  key={item.documentId}
                  filename={item.filename}
                  unclearCount={item.unclearCount}
                  onClick={handleOpenUnclearInDDGrid}
                />
              ))}
            </div>
            {hiddenUnclearFindingsCount > 0 && (
              <p className="text-[10px] text-[var(--text-muted)]">
                Ещё {hiddenUnclearFindingsCount}…
              </p>
            )}
          </div>
        )}
      </div>

      {/* Отдельная ссылка на страницу со списком результатов —
          без применения фильтра "Скрыть pass".
          Пользователь сам решает, какие результаты показывать. */}
      {canOpenDDGrid && (
        <button
          type="button"
          onClick={handleOpenAllResultsInDDGrid}
          className="flex w-full items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-left transition-colors hover:bg-[var(--bg-elevated-soft)]"
        >
          <span className="text-xs font-medium text-[var(--text-primary)]">
            Перейти к списку результатов
          </span>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
        </button>
      )}
    </div>
  );
};

export default AnalysisResultsWidget;


