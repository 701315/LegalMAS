// =============================================================
// src/pages/tabs/audit/ClassificationAuditView.tsx
// Экран "Аудит классификации документов" внутри вкладки Audit.
// Layout: master (таблица) + detail (side panel справа), как в Документах.
// =============================================================

import React from "react";
import {
  Loader2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { useClassificationInvestigation } from "../../../api/audit";
import { cn } from "../../../utils";
import type { ClassificationInvestigationRow } from "../../../types";
import Button from "../../../components/ui/Button";
import ClassificationInvestigationDrawer from "./ClassificationInvestigationDrawer";

interface ClassificationAuditViewProps {
  dealId: string;
}

const INVESTIGATION_PER_PAGE = 20;

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatConfidence(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function ConfidenceZoneBadge({ zone }: { zone: string | null }) {
  if (!zone) {
    return <span className="text-xs text-[var(--text-muted)]">—</span>;
  }

  const config: Record<string, { label: string; cls: string }> = {
    confident: {
      label: "Уверенная",
      cls: "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
    },
    low: {
      label: "Низкая",
      cls: "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]",
    },
    unknown: {
      label: "Неопр.",
      cls: "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]",
    },
  };

  const c = config[zone];

  return (
    <span
      className={cn(
        "inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium",
        c?.cls ??
          "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
      )}
    >
      {c?.label ?? zone}
    </span>
  );
}

function getRowBadges(row: ClassificationInvestigationRow): string[] {
  const badges: string[] = [];

  if (row.classification_requires_review) {
    badges.push("Требует проверки");
  }
  if (row.contradiction_detected) {
    badges.push("Есть противоречие");
  }
  if (row.l4_triggered) {
    badges.push("L4 triggered");
  }
  if (row.classification_level) {
    badges.push(row.classification_level);
  }

  return badges;
}

const ClassificationAuditView: React.FC<ClassificationAuditViewProps> = ({
  dealId,
}) => {
  const [page, setPage] = React.useState(1);
  const [selectedDocumentId, setSelectedDocumentId] = React.useState<
    string | null
  >(null);

  const { data, isLoading, isFetching, isError, error } =
    useClassificationInvestigation(dealId, {
      page,
      per_page: INVESTIGATION_PER_PAGE,
    });

  const items = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;

  const pageDescription = React.useMemo(() => {
    if (!data || data.total === 0 || items.length === 0) {
      return "Документы не найдены";
    }

    const from = (data.page - 1) * data.per_page + 1;
    const to = from + items.length - 1;
    return `Показаны ${from}–${to} из ${data.total}`;
  }, [data, items.length]);

  const selectedRow = React.useMemo(
    () =>
      selectedDocumentId
        ? items.find((row) => row.document_id === selectedDocumentId) ?? null
        : null,
    [items, selectedDocumentId],
  );

  // Если раскрытый документ пропал с текущей страницы — снимаем selection
  React.useEffect(() => {
    if (!selectedDocumentId || items.length === 0) {
      return;
    }
    const stillExists = items.some(
      (item) => item.document_id === selectedDocumentId,
    );
    if (!stillExists) {
      setSelectedDocumentId(null);
    }
  }, [items, selectedDocumentId]);

  const toggleRow = React.useCallback((documentId: string) => {
    setSelectedDocumentId((current) =>
      current === documentId ? null : documentId,
    );
  }, []);

  const handleRowKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLTableRowElement>, documentId: string) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleRow(documentId);
      }
    },
    [toggleRow],
  );

  const handleCloseDrawer = React.useCallback(() => {
    setSelectedDocumentId(null);
  }, []);

  if (isError) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 shadow-sm">
        <div className="mx-auto max-w-2xl text-center">
          <h3 className="text-base font-semibold text-[var(--text-primary)]">
            Не удалось загрузить аудит классификации
          </h3>
          <p className="mt-2 text-sm text-[var(--text-muted)]">
            {error instanceof Error
              ? error.message
              : "Сервис временно недоступен или данные ещё не готовы."}
          </p>
        </div>
      </div>
    );
  }

  const isDrawerOpen = selectedDocumentId !== null;

  return (
    <div
      className={cn(
        "grid min-h-0 flex-1 gap-4",
        isDrawerOpen
          ? "lg:grid-cols-[minmax(0,2fr)_minmax(360px,1fr)]"
          : "grid-cols-1",
      )}
    >
      {/* ── Основная секция: таблица ─────────────────────────── */}
      <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        {/* Header */}
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-4">
          <div>
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              Логи классификации документов проекта
            </h3>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              Нажмите на строку документа, чтобы открыть панель с полным путём
              классификации, кандидатами, voting и raw explainability payload.
            </p>
          </div>

          <div className="flex items-center gap-3">
            {isFetching && !isLoading ? (
              <span className="inline-flex items-center gap-2 text-xs text-[var(--text-muted)]">
                <Loader2 size={14} className="animate-spin" />
                Обновляем…
              </span>
            ) : null}

            <span className="text-xs text-[var(--text-muted)]">
              {pageDescription}
            </span>
          </div>
        </div>

        {isLoading ? (
          <div className="flex min-h-0 flex-1 items-center justify-center">
            <Loader2
              className="mr-3 animate-spin text-[var(--accent-primary)]"
              size={20}
            />
            <span className="text-sm text-[var(--text-muted)]">
              Загружаем аудит классификации…
            </span>
          </div>
        ) : (
          <>
            {/* Scrollable table area */}
            <div className="min-h-0 flex-1 overflow-auto">
              <table className="w-full min-w-[1120px] border-collapse">
                <thead className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--bg-elevated-soft)]">
                  <tr>
                    <th
                      scope="col"
                      className="w-72 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                    >
                      Документ
                    </th>
                    <th
                      scope="col"
                      className="w-40 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                    >
                      Тип
                    </th>
                    <th
                      scope="col"
                      className="w-28 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                    >
                      Уровень
                    </th>
                    <th
                      scope="col"
                      className="w-28 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                    >
                      Confidence
                    </th>
                    <th
                      scope="col"
                      className="w-32 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                    >
                      Зона
                    </th>
                    <th
                      scope="col"
                      className="w-40 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                    >
                      Решение
                    </th>
                    <th
                      scope="col"
                      className="w-48 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                    >
                      Сигналы
                    </th>
                    <th
                      scope="col"
                      className="w-44 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                    >
                      Сегментация
                    </th>
                    <th
                      scope="col"
                      className="w-44 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                    >
                      Обновлено
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {items.map((row) => {
                    const badges = getRowBadges(row);
                    const isSelected =
                      selectedDocumentId === row.document_id;

                    return (
                      <tr
                        key={row.document_id}
                        className={cn(
                          "cursor-pointer border-b border-[var(--border)] align-top transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-inset",
                          isSelected
                            ? "bg-[var(--bg-elevated-soft)] shadow-[inset_3px_0_0_var(--accent-primary)]"
                            : "hover:bg-[var(--bg-elevated-soft)]",
                        )}
                        onClick={() => toggleRow(row.document_id)}
                        onKeyDown={(event) =>
                          handleRowKeyDown(event, row.document_id)
                        }
                        aria-selected={isSelected}
                        role="button"
                        tabIndex={0}
                      >
                        <td className="px-3 py-3">
                          <div className="min-w-0">
                            <p
                              className="truncate text-sm font-medium text-[var(--text-primary)]"
                              title={row.filename}
                            >
                              {row.filename}
                            </p>

                            {row.folder_path ? (
                              <p
                                className="mt-1 truncate text-[11px] text-[var(--text-muted)]"
                                title={row.folder_path}
                              >
                                {row.folder_path}
                              </p>
                            ) : null}

                            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                              Статус: {row.status}
                            </p>
                          </div>
                        </td>

                        <td className="px-3 py-3 text-xs text-[var(--text-secondary)]">
                          {row.doc_type ?? "—"}
                        </td>

                        <td className="px-3 py-3 text-xs text-[var(--text-secondary)]">
                          {row.classification_level ?? "—"}
                        </td>

                        <td className="px-3 py-3 text-xs text-[var(--text-secondary)]">
                          {formatConfidence(row.classification_confidence)}
                        </td>

                        <td className="px-3 py-3">
                          <ConfidenceZoneBadge zone={row.confidence_zone} />
                        </td>

                        <td className="px-3 py-3 text-xs text-[var(--text-secondary)]">
                          {row.decided_by ?? "—"}
                        </td>

                        <td className="px-3 py-3">
                          {badges.length > 0 ? (
                            <div className="flex flex-wrap gap-1.5">
                              {badges.map((badge) => (
                                <span
                                  key={`${row.document_id}-${badge}`}
                                  className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]"
                                >
                                  {badge}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-xs text-[var(--text-muted)]">
                              —
                            </span>
                          )}
                        </td>

                        <td className="px-3 py-3 text-[11px] text-[var(--text-secondary)]">
                          <div className="space-y-1">
                            <p>
                              Сегментов:{" "}
                              {row.segment_summary?.segment_count ?? "—"}
                            </p>
                            <p>
                              Primary:{" "}
                              {row.segment_summary?.primary_segment_label ??
                                "—"}
                            </p>
                            <p>
                              Segment classification:{" "}
                              {row.segment_summary
                                ?.has_segment_classification == null
                                ? "—"
                                : row.segment_summary
                                    .has_segment_classification
                                  ? "Да"
                                  : "Нет"}
                            </p>
                          </div>
                        </td>

                        <td className="px-3 py-3 text-[11px] text-[var(--text-secondary)]">
                          {formatDateTime(row.updated_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {items.length === 0 && (
                <div className="py-10 text-center">
                  <p className="mb-1 text-sm text-[var(--text-secondary)]">
                    Данные по классификации не найдены
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    Для этого проекта ещё нет документов или
                    explainability-данные пока не собраны.
                  </p>
                </div>
              )}
            </div>

            {/* Pagination footer */}
            {totalPages > 1 && (
              <div className="flex shrink-0 flex-wrap items-center justify-center gap-3 border-t border-[var(--border)] px-4 py-4">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                  disabled={page <= 1}
                  leftIcon={<ChevronLeft size={14} />}
                >
                  Назад
                </Button>

                <span className="text-xs text-[var(--text-muted)]">
                  Страница {page} из {totalPages}
                </span>

                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    setPage((prev) => Math.min(totalPages, prev + 1))
                  }
                  disabled={page >= totalPages}
                  rightIcon={<ChevronRight size={14} />}
                >
                  Вперёд
                </Button>
              </div>
            )}
          </>
        )}
      </section>

      {/* ── Side panel: explainability drawer ────────────────── */}
      {isDrawerOpen && selectedDocumentId ? (
        <ClassificationInvestigationDrawer
          documentId={selectedDocumentId}
          filename={selectedRow?.filename ?? null}
          onClose={handleCloseDrawer}
        />
      ) : null}
    </div>
  );
};

export default ClassificationAuditView;


