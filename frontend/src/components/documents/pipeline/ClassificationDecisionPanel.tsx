// frontend/src/components/documents/pipeline/ClassificationDecisionPanel.tsx

import React from "react";
import { useTranslation } from "react-i18next";
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

function inferDecidedBy(
  data: ClassificationDecisionDTO,
  tFn: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (data.decided_by) return data.decided_by;

  const level = data.classification_level;
  const outcome = data.classification_outcome;

  if (level && outcome === "typed") {
    if (level === "L1") return tFn("classification.decidedBy.L1");
    if (level === "L2") return tFn("classification.decidedBy.L2");
    if (level === "L3") return tFn("classification.decidedBy.L3");
    if (level === "L4") return tFn("classification.decidedBy.L4");
    if (level === "HYBRID") return tFn("classification.decidedBy.HYBRID");
    return level;
  }

  if (outcome === "unknown") return tFn("classification.decidedBy.unknown");
  if (outcome === "failed") return tFn("classification.decidedBy.failed");
  if (outcome === "pending") return tFn("classification.decidedBy.pending");

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
  const { t } = useTranslation("pipeline");
  if (!zone) return null;
  const config: Record<string, { labelKey: string; cls: string }> = {
    confident: {
      labelKey: "classification.confidenceZones.confident",
      cls: "status-border-success status-bg-success status-text-success",
    },
    low: {
      labelKey: "classification.confidenceZones.low",
      cls: "status-border-warning status-bg-warning status-text-warning",
    },
    unknown: {
      labelKey: "classification.confidenceZones.unknown",
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
      {c ? t(c.labelKey) : zone}
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
  const { t } = useTranslation("pipeline");
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
              {t("classification.winnerBadge")}
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
  const { t } = useTranslation("pipeline");
  const hasCandidates = data.candidates.length > 0;
  const hasLevels = data.levels_tried.length > 0;
  const inferredZone = inferConfidenceZone(data);

  return (
    <div className="space-y-3">
      {/* Summary row */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <InfoRow label={t("classification.decisionLabel")} value={inferDecidedBy(data, t)} />
        <InfoRow
          label={t("classification.confidenceZoneLabel")}
          value={
            inferredZone ? (
              <ConfidenceZoneBadge zone={inferredZone} />
            ) : (
              "—"
            )
          }
        />
        <InfoRow
          label={t("classification.cascadeLevelLabel")}
          value={data.classification_level ?? "—"}
        />
        <InfoRow label={t("classification.outcomeLabel")} value={data.classification_outcome ?? "—"} />
        <InfoRow label={t("classification.confidenceLabel")} value={formatConfidence(data.confidence)} />
        <InfoRow label={t("classification.languageLabel")} value={data.language ?? "—"} />
        <InfoRow label={t("classification.jurisdictionLabel")} value={data.jurisdiction ?? "—"} />
        {data.voting_score != null && (
          <InfoRow
            label={t("classification.votingScoreLabel")}
            value={data.voting_score.toFixed(3)}
          />
        )}
      </div>

      {/* Flags */}
      <div className="flex flex-wrap gap-1.5">
        {data.requires_manual_review && (
          <span className="status-border-warning status-bg-warning status-text-warning rounded-full border px-2 py-0.5 text-[10px] font-medium">
            {t("classification.requiresManual")}
          </span>
        )}
        {data.l4_triggered && (
          <span className="rounded-full border border-[var(--color-blue)]/20 bg-[var(--color-blue-highlight)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-blue-strong)]">
            {t("classification.l4Triggered")}
          </span>
        )}
        {data.unknown_corridor_applied && (
          <span className="status-border-error status-bg-error status-text-error rounded-full border px-2 py-0.5 text-[10px] font-medium">
            {t("classification.unknownCorridor")}
          </span>
        )}
      </div>

      {/* Levels tried */}
      {hasLevels && (
        <div>
          <p className="mb-1 text-[11px] font-medium text-[var(--text-secondary)]">
            {t("classification.passedCascade")}
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
            {t("classification.candidatesTitle", { count: data.candidates.length })}
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
          {t("classification.noCandidatesFallback", {
            level: data.classification_level ?? t("classification.decidedBy.unknown"),
          })}
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
  const { t } = useTranslation("pipeline");
  const { data, isLoading, error } = useClassificationDecision(documentId);
  const [expanded, setExpanded] = React.useState(false);

  if (isLoading) {
    return (
      <div className="mt-3 flex items-center gap-2 py-2 text-[11px] text-[var(--text-muted)]">
        <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-primary)] border-t-transparent" />
        {t("classification.loading")}
      </div>
    );
  }

  if (error || !data) {
    return null;
  }

  const decidedByLabel = inferDecidedBy(data, t);

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2.5 text-left transition hover:bg-[var(--bg-elevated-soft)]"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[var(--text-primary)]">
            {t("classification.panelTitle")}
          </span>
          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
            {decidedByLabel}
          </span>
          {data.candidates.length > 0 && (
            <span className="text-[10px] text-[var(--text-muted)]">
              {t("classification.candidatesCount", { count: data.candidates.length })}
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

