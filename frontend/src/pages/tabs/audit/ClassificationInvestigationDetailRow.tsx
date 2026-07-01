// =============================================================
// src/pages/tabs/audit/ClassificationInvestigationDetailRow.tsx
// Inline detail block для forensic / explainability анализа
// одного документа внутри раскрытой строки таблицы.
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
      className: "border-green-300/40 bg-green-50 text-green-700",
    },
    low: {
      label: "Низкая",
      className: "border-yellow-300/40 bg-yellow-50 text-yellow-700",
    },
    unknown: {
      label: "Неопределённая",
      className: "border-red-300/40 bg-red-50 text-red-700",
    },
  };
  const c = config[zone];
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${
        c?.className ??
        "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]"
      }`}
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
  <div className="grid grid-cols-[160px_minmax(0,1fr)] gap-3 border-b border-[var(--border-subtle)] py-2.5 last:border-b-0">
    <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
      {label}
    </div>
    <div className="min-w-0 text-sm text-[var(--text-secondary)] break-words">
      {value}
    </div>
  </div>
);

const Section: React.FC<{
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, icon, children }) => (
  <section className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)]">
    <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-card)]/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-[var(--bg-card)]/80">
      {icon ? <span className="text-[var(--text-secondary)]">{icon}</span> : null}
      <h4 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h4>
    </div>

    <div className="px-4 py-4">{children}</div>
  </section>
);

const ClassificationInvestigationDetailRow: React.FC<Props> = ({ documentId }) => {
  const { data, isLoading, isError, error } =
    useClassificationInvestigationDetail(documentId);

  if (isLoading) {
    return (
      <div className="flex min-h-[220px] items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--bg-base)]">
        <Loader2 className="mr-3 animate-spin text-[var(--accent)]" size={20} />
        <span className="text-sm text-[var(--text-muted)]">
          Загружаем explainability по документу…
        </span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-base)] px-6 py-8 text-center">
        <h4 className="text-sm font-semibold text-[var(--text-primary)]">
          Не удалось загрузить детали классификации
        </h4>
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          {error instanceof Error
            ? error.message
            : "Explainability-данные временно недоступны."}
        </p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-base)] px-6 py-8 text-center">
        <p className="text-sm text-[var(--text-muted)]">
          Детали классификации отсутствуют.
        </p>
      </div>
    );
  }

  const applicableTriggers = Array.isArray(data.applicable_triggers)
    ? data.applicable_triggers
    : [];

  const levelsTried = Array.isArray(data.levels_tried) ? data.levels_tried : [];
  const levelResults = Array.isArray(data.level_results) ? data.level_results : [];
  const candidates = Array.isArray(data.candidates) ? data.candidates : [];
  const votingRanking = Array.isArray(data.voting?.ranking)
    ? data.voting.ranking
    : [];

  return (
    <div
      className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)]"
      role="region"
      aria-label={`Логи классификации документа ${data.filename ?? ""}`}
    >
      <div className="border-b border-[var(--border)] px-4 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
          Explainability log
        </p>
      </div>

      <div
        className="max-h-[70vh] overflow-y-auto p-4 focus:outline-none"
        tabIndex={0}
        aria-label={`Прокручиваемая область логов классификации документа ${data.filename ?? ""}`}
      >
        <div className="space-y-4">
          <Section title="Итог классификации" icon={<CheckCircle2 size={16} />}>
            <div className="space-y-1">
              <MetaRow label="Документ" value={data.filename ?? "—"} />
              <MetaRow label="Статус" value={data.status ?? "—"} />
              <MetaRow label="Тип" value={data.doc_type ?? "—"} />
              <MetaRow label="Уровень" value={data.classification_level ?? "—"} />
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

          <Section title="Пройденные этапы" icon={<GitBranch size={16} />}>
            {levelsTried.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {levelsTried.map((level, index) => (
                  <span
                    key={`${String(level)}-${index}`}
                    className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]"
                  >
                    {String(level)}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">
                Список этапов отсутствует.
              </p>
            )}
          </Section>

          <Section title="Результаты по уровням" icon={<FileText size={16} />}>
            {levelResults.length > 0 ? (
              <div className="space-y-3">
                {levelResults.map((item: any, index: number) => (
                  <div
                    key={`${String(item?.level ?? "level")}-${index}`}
                    className="rounded-xl border border-[var(--border)] bg-[var(--bg-base)] px-3 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-[var(--text-primary)]">
                        {item?.level ?? "—"}
                      </span>

                      {item?.type ? (
                        <span className="inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">
                          {String(item.type)}
                        </span>
                      ) : null}
                    </div>

                    <div className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
                      <p>Confidence: {formatConfidence(item?.confidence)}</p>
                      <p>Method: {item?.method ?? "—"}</p>
                      <p>Evidence: {item?.evidence ?? "—"}</p>
                    </div>

                    {item?.extra && Object.keys(item.extra).length > 0 ? (
                      <pre className="mt-3 overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-[11px] leading-5 text-[var(--text-secondary)]">
                        {renderJson(item.extra)}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">
                Нормализованные результаты по уровням отсутствуют.
              </p>
            )}
          </Section>

          <Section title="Кандидаты" icon={<Trophy size={16} />}>
            {candidates.length > 0 ? (
              <div className="space-y-2">
                {candidates.map((candidate: any, index: number) => {
                  const confidence = candidate?.confidence ?? 0;
                  const isWinner = index === 0;
                  const pct = Math.round(confidence * 100);
                  return (
                    <div
                      key={`${String(candidate?.doctype ?? "c")}-${index}`}
                      className={`rounded-xl border p-3 ${
                        isWinner
                          ? "border-green-300/40 bg-green-50"
                          : "border-[var(--border-subtle)] bg-[var(--bg-card)]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          {isWinner && (
                            <span className="text-xs text-green-600">✓</span>
                          )}
                          <span
                            className={`text-xs font-semibold ${
                              isWinner ? "text-green-800" : "text-[var(--text-primary)]"
                            }`}
                          >
                            {candidate?.doctype ?? "—"}
                          </span>
                          {candidate?.level ? (
                            <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                              {String(candidate.level)}
                            </span>
                          ) : null}
                          {candidate?.method ? (
                            <span className="text-[10px] text-[var(--text-faint)]">
                              {String(candidate.method)}
                            </span>
                          ) : null}
                        </div>
                        <span
                          className={`text-xs font-bold ${
                            isWinner ? "text-green-700" : "text-[var(--text-secondary)]"
                          }`}
                        >
                          {pct}%
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">
                        <div
                          className={`h-full rounded-full transition-all ${
                            isWinner ? "bg-green-500" : "bg-[var(--text-muted)]"
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      {candidate?.evidence ? (
                        <p className="mt-2 text-[11px] italic text-[var(--text-muted)]">
                          {String(candidate.evidence)}
                        </p>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">
                Кандидаты не зафиксированы.
              </p>
            )}
          </Section>

          <Section title="Voting / override" icon={<AlertTriangle size={16} />}>
            {data.voting ? (
              <div className="space-y-1">
                <MetaRow label="Strategy" value={data.voting.strategy ?? "—"} />
                <MetaRow label="Reason" value={data.voting.reason ?? "—"} />
                <MetaRow label="Type" value={data.voting.type ?? "—"} />
                <MetaRow
                  label="Confidence"
                  value={formatConfidence(data.voting.confidence)}
                />
                <MetaRow
                  label="Margin"
                  value={
                    data.voting.margin == null ? "—" : String(data.voting.margin)
                  }
                />

                {data.voting.override ? (
                  <div className="mt-3">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Override
                    </p>
                    <pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-3 text-[11px] leading-5 text-[var(--text-secondary)]">
                      {renderJson(data.voting.override)}
                    </pre>
                  </div>
                ) : null}

                {votingRanking.length > 0 ? (
                  <div className="mt-3">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                      Ranking
                    </p>
                    <pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-3 text-[11px] leading-5 text-[var(--text-secondary)]">
                      {renderJson(votingRanking)}
                    </pre>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">
                Voting-данные отсутствуют.
              </p>
            )}
          </Section>

          <Section title="Decision summary" icon={<CheckCircle2 size={16} />}>
            <pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-3 text-[11px] leading-5 text-[var(--text-secondary)]">
              {renderJson(data.decision_summary)}
            </pre>
          </Section>

          <Section title="Raw result" icon={<Database size={16} />}>
            <pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-3 text-[11px] leading-5 text-[var(--text-secondary)]">
              {renderJson(data.raw_result)}
            </pre>
          </Section>

          <Section title="Raw details" icon={<Database size={16} />}>
            <pre className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-3 text-[11px] leading-5 text-[var(--text-secondary)]">
              {renderJson(data.raw_details)}
            </pre>
          </Section>
        </div>
      </div>
    </div>
  );
};

export default ClassificationInvestigationDetailRow;

