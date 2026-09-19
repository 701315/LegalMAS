// =============================================================
// src/components/new-project/Block3Playbook.tsx
//
// Блок 3 — Лёгкий PlaybookPickerBlock.
//
// Только выбор существующей published-версии playbook
// и применение к deal. Без истории, без состава, без создания
// версий — полный DealPlaybookSelectorPanel остаётся нетронутым.
//
// Шаги:
//   1. Выбрать шаблон (playbook line)
//   2. Выбрать опубликованную версию
//   3. Применить к проекту → PATCH /api/v1/deals/:dealId/playbook
// =============================================================

import React from "react";
import { BookOpen, Loader2 } from "lucide-react";
import { useTranslation, Trans } from "react-i18next";

import client from "../../api/client";
import type { PlaybookLineShort, PlaybookVersionShort } from "../../types";
import { getApiErrorMessage } from "../../utils/apiErrors";
import { useStalePlaybooks } from "../../hooks/useStalePlaybooks";

import Button from "../ui/Button";
import InlineAlert from "../InlineAlert";
import OutdatedBadge from "../playbook/OutdatedBadge";

interface Block3PlaybookProps {
  dealId: string;
  /** Текущий playbook_version_id из deal (может быть null) */
  currentVersionId: string | null;
  /** Вызывается после успешного применения */
  onApplied: (versionId: string, versionLabel: string) => void;
}

const cardButtonClassName = [
  "w-full rounded-xl border px-3 py-2.5 text-left text-xs transition-colors",
  "focus-visible:outline-none focus-visible:ring-2",
  "focus-visible:ring-[var(--accent-primary)]/35",
  "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
].join(" ");

const cardIdleClassName =
  "border-[var(--border-soft)] bg-[var(--bg-card)] text-[var(--text-primary)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-elevated-soft)]";

const cardActiveClassName =
  "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--accent-primary)]";

const Block3Playbook: React.FC<Block3PlaybookProps> = ({
  dealId,
  currentVersionId,
  onApplied,
}) => {
  const { t } = useTranslation("projects");
  const stale = useStalePlaybooks();

  // ── Data state ────────────────────────────────────────────
  const [lines, setLines] = React.useState<PlaybookLineShort[]>([]);
  const [versions, setVersions] = React.useState<PlaybookVersionShort[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  // ── Selection state ───────────────────────────────────────
  const [selectedLineId, setSelectedLineId] = React.useState<string | null>(
    null,
  );
  const [selectedVersionId, setSelectedVersionId] = React.useState<
    string | null
  >(null);

  // ── Apply state ───────────────────────────────────────────
  const [isApplying, setIsApplying] = React.useState(false);
  const [applyError, setApplyError] = React.useState<string | null>(null);

  const isLocked = isApplying;

  // ── Load data ─────────────────────────────────────────────
  React.useEffect(() => {
    let cancelled = false;

    async function loadData() {
      setIsLoading(true);
      setLoadError(null);

      try {
        const [linesRes, versionsRes] = await Promise.all([
          client.get<PlaybookLineShort[]>(
            "/api/v1/playbooks/lines?scope=all",
          ),
          client.get<PlaybookVersionShort[]>("/api/v1/playbooks"),
        ]);

        if (cancelled) return;

        const nextLines = linesRes.data ?? [];
        const nextVersions = versionsRes.data ?? [];

        setLines(nextLines);
        setVersions(nextVersions);

        // Если у deal уже есть playbook — выставляем selection
        if (currentVersionId) {
          const currentVersion = nextVersions.find(
            (v) => String(v.id) === String(currentVersionId),
          );

          if (currentVersion) {
            setSelectedVersionId(String(currentVersion.id));

            if (currentVersion.playbook_id) {
              setSelectedLineId(String(currentVersion.playbook_id));
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            getApiErrorMessage(
              err,
              t("newProject.block3.errors.loadLinesFailed"),
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadData();

    return () => {
      cancelled = true;
    };
  }, [currentVersionId, t]);

  // ── Derived: published versions for selected line ─────────
  const publishedVersions = React.useMemo(() => {
    if (!selectedLineId) return [];

    return versions.filter(
      (v) =>
        String(v.playbook_id) === selectedLineId && v.status === "published",
    );
  }, [versions, selectedLineId]);

  const isSameAsCurrent =
    currentVersionId !== null &&
    selectedVersionId === String(currentVersionId);

  const canApply =
    !!selectedVersionId && !isApplying && !isSameAsCurrent;

  // ── Handlers ──────────────────────────────────────────────
  const handleSelectLine = React.useCallback(
    (lineId: string) => {
      if (isLocked) return;

      setApplyError(null);
      setSelectedLineId(lineId);
      setSelectedVersionId(null);
    },
    [isLocked],
  );

  const handleSelectVersion = React.useCallback(
    (versionId: string) => {
      if (isLocked) return;

      setApplyError(null);
      setSelectedVersionId(versionId);
    },
    [isLocked],
  );

  const handleApply = React.useCallback(async () => {
    if (!selectedVersionId || isApplying) return;

    setIsApplying(true);
    setApplyError(null);

    try {
      await client.patch(`/api/v1/deals/${dealId}/playbook`, {
        playbook_version_id: selectedVersionId,
      });

      const version = versions.find(
        (v) => String(v.id) === selectedVersionId,
      );

      const label = version
        ? `${version.name} (${version.semver})`
        : selectedVersionId;

      onApplied(selectedVersionId, label);
    } catch (err) {
      setApplyError(
        getApiErrorMessage(
          err,
          t("newProject.block3.errors.applyFailed"),
        ),
      );
    } finally {
      setIsApplying(false);
    }
  }, [dealId, isApplying, onApplied, selectedVersionId, versions, t]);

  // ── Loading ───────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-4">
        <Loader2
          className="h-4 w-4 animate-spin text-[var(--accent-primary)]"
          aria-hidden="true"
        />
        <span className="text-sm text-[var(--text-muted)]">
          {t("newProject.block3.loadingLines")}
        </span>
      </div>
    );
  }

  // ── Load error ────────────────────────────────────────────
  if (loadError) {
    return <InlineAlert tone="error" message={loadError} />;
  }

  // ── Empty ─────────────────────────────────────────────────
  if (lines.length === 0) {
    return (
      <div className="subtle-panel px-4 py-6 text-center">
        <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
          <BookOpen className="h-5 w-5 text-[var(--text-muted)]" />
        </div>
        <p className="text-sm font-medium text-[var(--text-primary)]">
          {t("newProject.block3.emptyLinesTitle")}
        </p>
        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
          {t("newProject.block3.emptyLinesDesc")}
        </p>
      </div>
    );
  }

  // ── Main content ──────────────────────────────────────────
  return (
    <div className="space-y-4">
      {applyError ? <InlineAlert tone="error" message={applyError} /> : null}

      {/* ── Описание playbook ────────────────────────────── */}
      <div className="subtle-panel px-4 py-3">
        <div className="flex items-start gap-3">
          <div
            className="mt-0.5 shrink-0 text-[var(--text-muted)]"
            aria-hidden="true"
          >
            <BookOpen className="h-4 w-4" />
          </div>

          <div className="min-w-0">
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {t("newProject.block3.infoTitle")}
            </p>
            <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
              {t("newProject.block3.infoDesc1")}
            </p>
            <p className="mt-2 text-[11px] leading-5 text-[var(--text-secondary)]">
              <Trans
                ns="projects"
                i18nKey="newProject.block3.infoDesc2"
                components={{
                  studio: <span className="font-medium text-[var(--text-primary)]" />,
                }}
              />
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* ── Шаблоны ────────────────────────────────────── */}
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {t("newProject.block3.templatePlaybook")}
          </p>

          <ul className="max-h-64 space-y-1 overflow-y-auto">
            {lines.map((line) => {
              const lineId = String(line.id);
              const isSelected = selectedLineId === lineId;

              const metaString = [
                line.deal_type && t("newProject.block3.meta.type", { type: line.deal_type }),
                line.jurisdiction && t("newProject.block3.meta.jurisdiction", { jurisdiction: line.jurisdiction }),
                line.language && t("newProject.block3.meta.language", { language: line.language }),
              ]
                .filter(Boolean)
                .join(" · ");

              return (
                <li key={lineId}>
                  <button
                    type="button"
                    onClick={() => handleSelectLine(lineId)}
                    disabled={isLocked}
                    className={[
                      cardButtonClassName,
                      isSelected ? cardActiveClassName : cardIdleClassName,
                      isLocked
                        ? "cursor-not-allowed opacity-60"
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    <div className="font-semibold">{line.title}</div>

                    {line.description ? (
                      <div className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
                        {line.description}
                      </div>
                    ) : null}

                    {metaString ? (
                      <div className="mt-1 text-[11px] text-[var(--text-muted)]">
                        {metaString}
                      </div>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        {/* ── Версии ─────────────────────────────────────── */}
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {t("newProject.block3.playbookVersion")}
          </p>

          {!selectedLineId ? (
            <div className="subtle-panel px-4 py-6 text-center">
              <p className="text-xs text-[var(--text-muted)]">
                {t("newProject.block3.selectTemplatePrompt")}
              </p>
            </div>
          ) : publishedVersions.length === 0 ? (
            <div className="subtle-panel px-4 py-6 text-center">
              <p className="text-xs text-[var(--text-muted)]">
                {t("newProject.block3.noPublishedVersions")}
              </p>
            </div>
          ) : (
            <>
              <ul className="max-h-48 space-y-1 overflow-y-auto">
                {publishedVersions.map((version) => {
                  const versionId = String(version.id);
                  const isSelected = selectedVersionId === versionId;
                  const isCurrent =
                    currentVersionId !== null &&
                    versionId === String(currentVersionId);

                  return (
                    <li key={versionId}>
                      <button
                        type="button"
                        onClick={() => handleSelectVersion(versionId)}
                        disabled={isLocked}
                        className={[
                          cardButtonClassName,
                          isSelected
                            ? cardActiveClassName
                            : cardIdleClassName,
                          isLocked
                            ? "cursor-not-allowed opacity-60"
                            : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold">
                            {version.name}
                          </span>
                          <span className="text-[11px] font-normal text-[var(--text-muted)]">
                            ({version.semver})
                          </span>
                          {isCurrent ? (
                            <span className="rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--color-success-text)]">
                              {t("newProject.block3.currentBadge")}
                            </span>
                          ) : null}
                          {stale.byId.has(versionId) ? (
                            <OutdatedBadge item={stale.byId.get(versionId)!} />
                          ) : null}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>

              <div className="mt-3 flex justify-end border-t border-[var(--border-subtle)] pt-3">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleApply}
                  disabled={!canApply}
                  isLoading={isApplying}
                >
                  {isSameAsCurrent
                    ? t("newProject.block3.alreadyApplied")
                    : t("newProject.block3.applyBtn")}
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Block3Playbook;


