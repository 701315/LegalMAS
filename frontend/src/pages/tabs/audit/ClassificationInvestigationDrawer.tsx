// =============================================================
// src/pages/tabs/audit/ClassificationInvestigationDrawer.tsx
// Side panel с explainability / forensic данными по одному документу.
// Открывается справа от таблицы аудита классификации.
// Аналог DocumentDetailsContainer в разделе Документы.
// =============================================================

import React from "react";
import {
  Loader2,
  FileText,
  GitBranch,
  Trophy,
  Database,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";

import { useClassificationInvestigationDetail } from "../../../api/audit";

interface Props {
  documentId: string;
  filename: string | null;
  onClose: () => void;
}

function formatConfidence(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function ConfidenceZoneBadge({ zone }: { zone: string | null | undefined }) {
  if (!zone) return <span className="text-[var(--text-muted)]">—</span>;

  const config: Record<string, { label: string; className: string }> = {
    confident: {
      label: "Уверенная",
      className:
        "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
    },
    low: {
      label: "Низкая",
      className:
        "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]",
    },
    unknown: {
      label: "Неопределённая",
      className:
        "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]",
    },
  };

  const c = config[zone];

  return (
    <span
      className={[
        "inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium",
        c?.className ??
          "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)]",
      ].join(" ")}
    >
      {c?.label ?? zone}
    </span>
  );
}

function renderJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value);
  }
}

const MetaRow: React.FC<{
  label: string;
  value: React.ReactNode;
}> = ({ label, value }) => (
  <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 border-b border-[var(--border-subtle)] py-2 last:border-b-0">
    <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
      {label}
    </div>
    <div className="min-w-0 break-words text-xs text-[var(--text-secondary)]">
      {value}
    </div>
  </div>
);

const Section: React.FC<{
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, icon, children }) => (
  <section>
    <div className="mb-2 flex items-center gap-2">
      {icon ? (
        <span className="text-[var(--text-secondary)]">{icon}</span>
      ) : null}
      <h4 className="text-xs font-semibold text-[var(--text-primary)]">
        {title}
      </h4>
    </div>
    <div>{children}</div>
  </section>
);

const ClassificationInvestigationDrawer: React.FC<Props> = ({
  documentId,
  filename,
  onClose,
}) => {
  const { data, isLoading, isError, error } =
    useClassificationInvestigationDetail(documentId);

  // Закрытие по Escape
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const applicableTriggers =
    data && Array.isArray(data.applicable_triggers)
      ? data.applicable_triggers
      : [];

  const levelsTried =
    data && Array.isArray(data.levels_tried) ? data.levels_tried : [];
  const levelResults =
    data && Array.isArray(data.level_results) ? data.level_results : [];
  const candidates =
    data && Array.isArray(data.candidates) ? data.candidates : [];
  const votingRanking =
    data && Array.isArray(data.voting?.ranking) ? data.voting.ranking : [];

  return (
    <aside className="relative flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      {/* Accent strip слева */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-[3px] bg-[var(--accent-primary)]" />

      {/* Header */}
      <div className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Explainability
          </span>
          <span className="text-[var(--text-faint)]">·</span>
          <span
            className="truncate text-sm font-medium text-[var(--text-primary)]"
            title={filename ?? documentId}
          >
            {filename ?? documentId}
          </span>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
          aria-label="Закрыть панель explainability"
        >
          ✕
        </button>
      </div>

      {/* Scrollable content */}
      <div className="min-h-0 flex-1 overflow-y-auto bg-[var(--bg-elevated-soft)]">
        {isLoading ? (
          <div className="flex items-center gap-3 px-5 py-6">
            <Loader2
              className="animate-spin text-[var(--accent-primary)]"
              size={18}
            />
            <span className="text-sm text-[var(--text-muted)]">
              Загружаем explainability…
            </span>
          </div>
        ) : isError ? (
          <div className="px-5 py-6">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              Не удалось загрузить детали классификации
            </p>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {error instanceof Error
                ? error.message
                : "Explainability-данные временно недоступны."}
            </p>
          </div>
        ) : !data ? (
          <div className="px-5 py-6">
            <p className="text-sm text-[var(--text-muted)]">
              Детали классификации отсутствуют.
            </p>
          </div>
        ) : (
          <div className="space-y-5 px-5 py-5">
            <Section
              title="Итог классификации"
              icon={<CheckCircle2 size={14} />}
            >
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2">
                <MetaRow label="Статус" value={data.status ?? "—"} />
                <MetaRow label="Тип" value={data.doc_type ?? "—"} />
                <MetaRow
                  label="Уровень"
                  value={data.classification_level ?? "—"}
                />
                <MetaRow
                  label="Confidence"
                  value={formatConfidence(data.classification_confidence)}
                />
                <MetaRow
                  label="Confidence zone"
                  value={<ConfidenceZoneBadge zone={data.confidence_zone} />}
                />
                <MetaRow label="Decided by" value={data.decided_by ?? "—"} />
                <MetaRow label="Language" value={data.language ?? "—"} />
                <MetaRow
                  label="Jurisdiction"
                  value={data.jurisdiction_guess ?? "—"}
                />
                <MetaRow
                  label="Requires review"
                  value={data.classification_requires_review ? "Да" : "Нет"}
                />
                <MetaRow
                  label="Contradiction"
                  value={data.contradiction_detected ? "Да" : "Нет"}
                />
                <MetaRow
                  label="L4 triggered"
                  value={data.l4_triggered ? "Да" : "Нет"}
                />
                <MetaRow
                  label="Triggers"
                  value={
                    applicableTriggers.length > 0
                      ? applicableTriggers.join(", ")
                      : "—"
                  }
                />
              </div>
            </Section>

            <Section title="Пройденные этапы" icon={<GitBranch size={14} />}>
              {levelsTried.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {levelsTried.map((level, index) => (
                    <span
                      key={`${String(level)}-${index}`}
                      className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]"
                    >
                      {String(level)}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[var(--text-muted)]">
                  Список этапов отсутствует.
                </p>
              )}
            </Section>

            <Section
              title="Результаты по уровням"
              icon={<FileText size={14} />}
            >
              {levelResults.length > 0 ? (
                <div className="space-y-2">
                  {levelResults.map((item: any, index: number) => (
                    <div
                      key={`${String(item?.level ?? "level")}-${index}`}
                      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2.5"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-semibold text-[var(--text-primary)]">
                          {item?.level ?? "—"}
                        </span>

                        {item?.type ? (
                          <span className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
                            {String(item.type)}
                          </span>
                        ) : null}
                      </div>

                      <div className="mt-2 space-y-0.5 text-xs text-[var(--text-secondary)]">
                        <p>Confidence: {formatConfidence(item?.confidence)}</p>
                        <p>Method: {item?.method ?? "—"}</p>
                        <p>Evidence: {item?.evidence ?? "—"}</p>
                      </div>

                      {item?.extra &&
                      Object.keys(item.extra).length > 0 ? (
                        <pre className="mt-2 overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2 text-[10px] leading-4 text-[var(--text-secondary)]">
                          {renderJson(item.extra)}
                        </pre>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[var(--text-muted)]">
                  Нормализованные результаты по уровням отсутствуют.
                </p>
              )}
            </Section>

            <Section title="Кандидаты" icon={<Trophy size={14} />}>
              {candidates.length > 0 ? (
                <div className="space-y-1.5">
                  {candidates.map((candidate: any, index: number) => {
                    const confidence = candidate?.confidence ?? 0;
                    const isWinner = index === 0;
                    const pct = Math.round(confidence * 100);
                    return (
                      <div
                        key={`${String(candidate?.doctype ?? "c")}-${index}`}
                        className={[
                          "rounded-xl border px-3 py-2",
                          isWinner
                            ? "border-[var(--color-success-border)] bg-[var(--color-success-bg)]"
                            : "border-[var(--border-subtle)] bg-[var(--bg-card)]",
                        ].join(" ")}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-1.5">
                            {isWinner && (
                              <span className="text-[11px] text-[var(--color-success-text)]">
                                ✓
                              </span>
                            )}
                            <span
                              className={[
                                "truncate text-xs font-semibold",
                                isWinner
                                  ? "text-[var(--color-success-text)]"
                                  : "text-[var(--text-primary)]",
                              ].join(" ")}
                            >
                              {candidate?.doctype ?? "—"}
                            </span>
                            {candidate?.level ? (
                              <span className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                                {String(candidate.level)}
                              </span>
                            ) : null}
                          </div>
                          <span
                            className={[
                              "shrink-0 text-xs font-bold tabular-nums",
                              isWinner
                                ? "text-[var(--color-success-text)]"
                                : "text-[var(--text-secondary)]",
                            ].join(" ")}
                          >
                            {pct}%
                          </span>
                        </div>
                        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">
                          <div
                            className={[
                              "h-full rounded-full transition-all",
                              isWinner
                                ? "bg-[var(--color-success)]"
                                : "bg-[var(--text-muted)]",
                            ].join(" ")}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        {candidate?.method ? (
                          <p className="mt-1 text-[10px] text-[var(--text-faint)]">
                            {String(candidate.method)}
                          </p>
                        ) : null}
                        {candidate?.evidence ? (
                          <p className="mt-1 text-[10px] italic text-[var(--text-muted)]">
                            {String(candidate.evidence)}
                          </p>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-[var(--text-muted)]">
                  Кандидаты не зафиксированы.
                </p>
              )}
            </Section>

            <Section
              title="Voting / override"
              icon={<AlertTriangle size={14} />}
            >
              {data.voting ? (
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2">
                  <MetaRow
                    label="Strategy"
                    value={data.voting.strategy ?? "—"}
                  />
                  <MetaRow
                    label="Reason"
                    value={data.voting.reason ?? "—"}
                  />
                  <MetaRow label="Type" value={data.voting.type ?? "—"} />
                  <MetaRow
                    label="Confidence"
                    value={formatConfidence(data.voting.confidence)}
                  />
                  <MetaRow
                    label="Margin"
                    value={
                      data.voting.margin == null
                        ? "—"
                        : String(data.voting.margin)
                    }
                  />

                  {data.voting.override ? (
                    <div className="mt-2">
                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                        Override
                      </p>
                      <pre className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2 text-[10px] leading-4 text-[var(--text-secondary)]">
                        {renderJson(data.voting.override)}
                      </pre>
                    </div>
                  ) : null}

                  {votingRanking.length > 0 ? (
                    <div className="mt-2">
                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                        Ranking
                      </p>
                      <pre className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2 text-[10px] leading-4 text-[var(--text-secondary)]">
                        {renderJson(votingRanking)}
                      </pre>
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="text-xs text-[var(--text-muted)]">
                  Voting-данные отсутствуют.
                </p>
              )}
            </Section>

            <Section
              title="Decision summary"
              icon={<CheckCircle2 size={14} />}
            >
              <pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-[10px] leading-4 text-[var(--text-secondary)]">
                {renderJson(data.decision_summary)}
              </pre>
            </Section>

            <Section title="Raw result" icon={<Database size={14} />}>
              <pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-[10px] leading-4 text-[var(--text-secondary)]">
                {renderJson(data.raw_result)}
              </pre>
            </Section>

            <Section title="Raw details" icon={<Database size={14} />}>
              <pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-[10px] leading-4 text-[var(--text-secondary)]">
                {renderJson(data.raw_details)}
              </pre>
            </Section>
          </div>
        )}
      </div>
    </aside>
  );
};

export default ClassificationInvestigationDrawer;



