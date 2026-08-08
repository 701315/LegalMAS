// frontend/src/components/documents/pipeline/ClassificationDecisionPanel.tsx

import React from "react";
import {
  useClassificationDecision,
  type ClassificationDecisionDTO,
  type ClassificationCandidateDTO,
} from "../../../api/provenance";

// ─── Helpers ─────────────────────────────────────────────────

function formatConfidence(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function inferDecidedBy(data: ClassificationDecisionDTO): string {
  if (data.decided_by) return data.decided_by;

  const level = data.classification_level;
  const outcome = data.classification_outcome;

  if (level && outcome === "typed") {
    if (level === "L1") return `${level} — детерминированное совпадение`;
    if (level === "L2") return `${level} — точное совпадение правила`;
    if (level === "L3") return `${level} — гибридное решение`;
    if (level === "L4") return `${level} — LLM классификация`;
    if (level === "HYBRID") return "HYBRID — гибридное решение";
    return level;
  }

  if (outcome === "unknown") return "Не определено";
  if (outcome === "failed") return "Ошибка классификации";
  if (outcome === "pending") return "В обработке";

  return "—";
}

function inferConfidenceZone(
  data: ClassificationDecisionDTO,
): string | null {
  if (data.confidence_zone) return data.confidence_zone;

  const conf = data.confidence;
  if (conf == null) return null;
  if (conf >= 0.8) return "confident";
  if (conf >= 0.5) return "low";
  return "unknown";
}

function ConfidenceZoneBadge({ zone }: { zone: string | null | undefined }) {
  if (!zone) return null;
  const config: Record<string, { label: string; cls: string }> = {
    confident: {
      label: "Уверенная",
      cls: "status-border-success status-bg-success status-text-success",
    },
    low: {
      label: "Низкая",
      cls: "status-border-warning status-bg-warning status-text-warning",
    },
    unknown: {
      label: "Неопределённая",
      cls: "status-border-error status-bg-error status-text-error",
    },
  };
  const c = config[zone];
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${
        c?.cls ??
        "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]"
      }`}
    >
      {c?.label ?? zone}
    </span>
  );
}

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="shrink-0 text-[11px] text-[var(--text-muted)]">
        {label}
      </span>
      <span className="text-right text-[11px] font-medium text-[var(--text-primary)]">
        {value ?? "—"}
      </span>
    </div>
  );
}

// ─── Candidate row ───────────────────────────────────────────

function CandidateRow({
  candidate,
  rank,
  isWinner,
}: {
  candidate: ClassificationCandidateDTO;
  rank: number;
  isWinner: boolean;
}) {
  const typeLabel = candidate.type_code || candidate.doctype || "—";

  return (
    <div
      className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${
        isWinner
          ? "status-border-success status-bg-success"
          : "border-[var(--border-subtle)] bg-[var(--bg-card)]"
      }`}
    >
      <span className="w-5 shrink-0 text-center text-[10px] font-bold text-[var(--text-muted)]">
        #{rank}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-semibold ${
              isWinner
                ? "status-text-success"
                : "text-[var(--text-primary)]"
            }`}
          >
            {typeLabel}
          </span>
          {isWinner && (
            <span className="status-border-success status-bg-success status-text-success rounded-full border px-1.5 py-0.5 text-[10px] font-medium">
              Выбран
            </span>
          )}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[10px] text-[var(--text-muted)]">
          {candidate.confidence != null && (
            <span>conf: {formatConfidence(candidate.confidence)}</span>
          )}
          {candidate.level && <span>level: {candidate.level}</span>}
          {candidate.method && <span>method: {candidate.method}</span>}
        </div>
        {candidate.evidence && (
          <p className="mt-1 text-[10px] italic text-[var(--text-muted)]">
            «{candidate.evidence}»
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Main panel content ──────────────────────────────────────

function DecisionContent({ data }: { data: ClassificationDecisionDTO }) {
  const hasCandidates = data.candidates.length > 0;
  const hasLevels = data.levels_tried.length > 0;
  const inferredZone = inferConfidenceZone(data);

  return (
    <div className="space-y-3">
      {/* Summary row */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <InfoRow label="Решение" value={inferDecidedBy(data)} />
        <InfoRow
          label="Зона уверенности"
          value={
            inferredZone ? (
              <ConfidenceZoneBadge zone={inferredZone} />
            ) : (
              "—"
            )
          }
        />
        <InfoRow
          label="Уровень каскада"
          value={data.classification_level ?? "—"}
        />
        <InfoRow label="Outcome" value={data.classification_outcome ?? "—"} />
        <InfoRow label="Confidence" value={formatConfidence(data.confidence)} />
        <InfoRow label="Язык" value={data.language ?? "—"} />
        <InfoRow label="Юрисдикция" value={data.jurisdiction ?? "—"} />
        {data.voting_score != null && (
          <InfoRow
            label="Voting score"
            value={data.voting_score.toFixed(3)}
          />
        )}
      </div>

      {/* Flags */}
      <div className="flex flex-wrap gap-1.5">
        {data.requires_manual_review && (
          <span className="status-border-warning status-bg-warning status-text-warning rounded-full border px-2 py-0.5 text-[10px] font-medium">
            Требует ручной проверки
          </span>
        )}
        {data.l4_triggered && (
          <span className="rounded-full border border-[var(--color-blue)]/20 bg-[var(--color-blue-highlight)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-blue-strong)]">
            L4 LLM triggered
          </span>
        )}
        {data.unknown_corridor_applied && (
          <span className="status-border-error status-bg-error status-text-error rounded-full border px-2 py-0.5 text-[10px] font-medium">
            Unknown corridor
          </span>
        )}
      </div>

      {/* Levels tried */}
      {hasLevels && (
        <div>
          <p className="mb-1 text-[11px] font-medium text-[var(--text-secondary)]">
            Пройденные уровни каскада:
          </p>
          <div className="flex flex-wrap gap-1.5">
            {data.levels_tried.map((level) => (
              <span
                key={level}
                className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]"
              >
                {level}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Candidates */}
      {hasCandidates ? (
        <div>
          <p className="mb-1.5 text-[11px] font-medium text-[var(--text-secondary)]">
            Кандидаты классификации ({data.candidates.length}):
          </p>
          <div className="space-y-1.5">
            {data.candidates.map((candidate, idx) => {
              const candidateType =
                candidate.type_code || candidate.doctype || "";
              const isWinner =
                candidateType !== "" && candidateType === data.doc_type;

              return (
                <CandidateRow
                  key={`${candidateType}-${idx}`}
                  candidate={candidate}
                  rank={idx + 1}
                  isWinner={isWinner}
                />
              );
            })}
          </div>
        </div>
      ) : (
        <p className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-[11px] italic text-[var(--text-muted)]">
          Альтернативных кандидатов не рассматривалось — решение принято
          детерминированно на уровне {data.classification_level ?? "правил"}.
        </p>
      )}

      {/* Playbook version */}
      {data.playbook_version_id && (
        <p className="text-[10px] text-[var(--text-faint)]">
          Playbook version: {data.playbook_version_id}
        </p>
      )}
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────

interface Props {
  documentId: string;
}

export function ClassificationDecisionPanel({ documentId }: Props) {
  const { data, isLoading, error } = useClassificationDecision(documentId);
  const [expanded, setExpanded] = React.useState(false);

  if (isLoading) {
    return (
      <div className="mt-3 flex items-center gap-2 py-2 text-[11px] text-[var(--text-muted)]">
        <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-primary)] border-t-transparent" />
        Загрузка решения классификации…
      </div>
    );
  }

  if (error || !data) {
    return null;
  }

  const decidedByLabel = inferDecidedBy(data);

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2.5 text-left transition hover:bg-[var(--bg-elevated-soft)]"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[var(--text-primary)]">
            Как было принято решение
          </span>
          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
            {decidedByLabel}
          </span>
          {data.candidates.length > 0 && (
            <span className="text-[10px] text-[var(--text-muted)]">
              {data.candidates.length} кандидат
              {data.candidates.length > 1 ? "ов" : ""}
            </span>
          )}
        </div>
        <span className="shrink-0 text-[10px] text-[var(--accent-primary)]">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && (
        <div className="mt-1 rounded-b-xl border border-t-0 border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-3">
          <DecisionContent data={data} />
        </div>
      )}
    </div>
  );
}

export default ClassificationDecisionPanel;


