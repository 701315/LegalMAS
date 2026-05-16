// =============================================================
// src/pages/tabs/audit/ClassificationAuditView.tsx
// Экран "Аудит классификации документов" внутри вкладки Audit.
// Только таблица + раскрытие дополнительной информации под строкой.
// =============================================================

import React from "react";
import {
  Loader2,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
} from "lucide-react";

import { useClassificationInvestigation } from "../../../api/audit";
import { cn } from "../../../utils";
import type { ClassificationInvestigationRow } from "../../../types";
import Button from "../../../components/ui/Button";
import ClassificationInvestigationDetailRow from "./ClassificationInvestigationDetailRow";

interface ClassificationAuditViewProps {
  dealId: string;
}

const INVESTIGATION_PER_PAGE = 20;
const TABLE_COLUMNS = 9;

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

function formatConfidenceZone(zone: string | null): string {
  if (!zone) return "—";

  switch (zone) {
    case "high":
      return "Высокая";
    case "medium":
      return "Средняя";
    case "low":
      return "Низкая";
    case "unknown":
      return "Неизвестно";
    default:
      return zone;
  }
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
  const [expandedDocumentId, setExpandedDocumentId] = React.useState<string | null>(
    null,
  );

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

  React.useEffect(() => {
    if (!expandedDocumentId || items.length === 0) {
      return;
    }

    const stillExistsOnPage = items.some(
      (item) => item.document_id === expandedDocumentId,
    );

    if (!stillExistsOnPage) {
      setExpandedDocumentId(null);
    }
  }, [items, expandedDocumentId]);

  const toggleRow = React.useCallback((documentId: string) => {
    setExpandedDocumentId((current) =>
      current === documentId ? null : documentId,
    );
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

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Логи классификации документов проекта
          </h3>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Нажмите на строку документа, чтобы раскрыть полный путь классификации
            по этапам, кандидатов, voting и raw explainability payload.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {isFetching && !isLoading ? (
            <span className="inline-flex items-center gap-2 text-xs text-[var(--text-muted)]">
              <Loader2 size={14} className="animate-spin" />
              Обновляем…
            </span>
          ) : null}

          <span className="text-xs text-[var(--text-muted)]">{pageDescription}</span>
        </div>
      </div>

      {isLoading ? (
        <div className="flex min-h-[320px] items-center justify-center">
          <Loader2 className="mr-3 animate-spin text-[var(--accent)]" size={20} />
          <span className="text-sm text-[var(--text-muted)]">
            Загружаем аудит классификации…
          </span>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1120px] border-collapse">
              <thead className="border-b border-[var(--border)] bg-[var(--bg-elevated-soft)]">
                <tr>
                  <th
                    scope="col"
                    className="w-10 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                  />
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
                  const isExpanded = expandedDocumentId === row.document_id;

                  return (
                    <React.Fragment key={row.document_id}>
                      <tr
                        className={cn(
                          "cursor-pointer border-b border-[var(--border)] align-top transition-colors hover:bg-[var(--bg-elevated-soft)]",
                          row.classification_requires_review &&
                            "bg-[color:color-mix(in_srgb,var(--color-warning,#f59e0b)_4%,transparent)]",
                          isExpanded &&
                            "bg-[color:color-mix(in_srgb,var(--accent-primary)_8%,transparent)]",
                        )}
                        onClick={() => toggleRow(row.document_id)}
                        aria-expanded={isExpanded}
                      >
                        <td className="px-3 py-3 text-[var(--text-muted)]">
                          {isExpanded ? (
                            <ChevronDown size={16} />
                          ) : (
                            <ChevronRight size={16} />
                          )}
                        </td>

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

                        <td className="px-3 py-3 text-xs text-[var(--text-secondary)]">
                          {formatConfidenceZone(row.confidence_zone)}
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
                            <span className="text-xs text-[var(--text-muted)]">—</span>
                          )}
                        </td>

                        <td className="px-3 py-3 text-[11px] text-[var(--text-secondary)]">
                          <div className="space-y-1">
                            <p>
                              Сегментов: {row.segment_summary?.segment_count ?? "—"}
                            </p>
                            <p>
                              Primary:{" "}
                              {row.segment_summary?.primary_segment_label ?? "—"}
                            </p>
                            <p>
                              Segment classification:{" "}
                              {row.segment_summary?.has_segment_classification ==
                              null
                                ? "—"
                                : row.segment_summary.has_segment_classification
                                  ? "Да"
                                  : "Нет"}
                            </p>
                          </div>
                        </td>

                        <td className="px-3 py-3 text-[11px] text-[var(--text-secondary)]">
                          {formatDateTime(row.updated_at)}
                        </td>
                      </tr>

                      {isExpanded ? (
                        <tr className="border-b border-[var(--border)] bg-[var(--bg-base)]">
                          <td colSpan={TABLE_COLUMNS + 1} className="px-4 py-4">
                            <ClassificationInvestigationDetailRow
                              documentId={row.document_id}
                            />
                          </td>
                        </tr>
                      ) : null}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {items.length === 0 && (
            <div className="py-10 text-center">
              <p className="mb-1 text-sm text-[var(--text-secondary)]">
                Данные по классификации не найдены
              </p>
              <p className="text-xs text-[var(--text-muted)]">
                Для этого проекта ещё нет документов или explainability-данные пока
                не собраны.
              </p>
            </div>
          )}

          {totalPages > 1 && (
            <div className="flex flex-wrap items-center justify-center gap-3 border-t border-[var(--border)] px-4 py-4">
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
                onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
                disabled={page >= totalPages}
                rightIcon={<ChevronRight size={14} />}
              >
                Вперёд
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default ClassificationAuditView;


