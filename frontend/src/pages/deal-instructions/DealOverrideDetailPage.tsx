// src/pages/deal-instructions/DealOverrideDetailPage.tsx
// Detail deal-level override.
// Включает rebase flow — только deal overrides имеют rebase endpoint.

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import {
  useDealOverrides,
  useValidateDealOverride,
  useActivateDealOverride,
  useArchiveDealOverride,
  useRebaseDealOverride,
} from "../../hooks/instructions/useInstructionOverrides";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import OverrideStatusBadge from "../../components/instructions/OverrideStatusBadge";
import StaleWarningBanner from "../../components/instructions/StaleWarningBanner";
import PatchOpsEditor from "../../components/instructions/PatchOpsEditor";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import Field from "../../components/ui/Field";
import type {
  InstructionOverrideValidationResponse,
  JsonPatchOperation,
} from "../../types/instructions";

const inputClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60";

const DealOverrideDetailPage: React.FC = () => {
  const { t } = useTranslation("instructions");
  const { dealId, docType: overrideId } = useParams<{
    dealId: string;
    docType: string;
  }>();
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useDealOverrides(
    dealId ?? null,
  );
  const override = data?.items.find((o) => o.id === overrideId) ?? null;

  const validateMutation = useValidateDealOverride();
  const activateMutation = useActivateDealOverride();
  const archiveMutation = useArchiveDealOverride();
  const rebaseMutation = useRebaseDealOverride();

  // Local state
  const [validationResult, setValidationResult] =
    useState<InstructionOverrideValidationResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [showArchiveDialog, setShowArchiveDialog] = useState(false);

  // Rebase form state
  const [showRebaseForm, setShowRebaseForm] = useState(false);
  const [newBaseVersionId, setNewBaseVersionId] = useState("");
  const [rebasePatchOps, setRebasePatchOps] = useState<JsonPatchOperation[]>(
    override?.patch_ops ?? [],
  );

  const canActivate = override?.status === "draft" && !override?.is_stale;
  const canArchive =
    override?.status === "draft" || override?.status === "active";

  const handleValidate = async () => {
    if (!dealId || !overrideId) return;
    setActionError(null);
    setValidationResult(null);
    try {
      const result = await validateMutation.mutateAsync({ dealId, overrideId });
      setValidationResult(result);
    } catch {
      setActionError(t("deal.detailPage.errors.validate"));
    }
  };

  const handleActivate = async () => {
    if (!dealId || !overrideId) return;
    setActionError(null);
    try {
      await activateMutation.mutateAsync({ dealId, overrideId });
      setActionSuccess(t("deal.detailPage.success.activate"));
      await refetch();
    } catch {
      setActionError(t("deal.detailPage.errors.activate"));
    }
  };

  const handleArchiveConfirm = async () => {
    if (!dealId || !overrideId) return;
    try {
      await archiveMutation.mutateAsync({ dealId, overrideId });
      setShowArchiveDialog(false);
      setActionSuccess(t("deal.detailPage.success.archive"));
      await refetch();
    } catch {
      setShowArchiveDialog(false);
      setActionError(t("deal.detailPage.errors.archive"));
    }
  };

  const handleRebase = async () => {
    if (!dealId || !overrideId || !newBaseVersionId.trim()) return;
    setActionError(null);
    try {
      await rebaseMutation.mutateAsync({
        dealId,
        overrideId,
        body: {
          new_base_version_id: newBaseVersionId.trim(),
          new_patch_ops: rebasePatchOps,
        },
      });
      setActionSuccess(t("deal.detailPage.success.rebase"));
      setShowRebaseForm(false);
      await refetch();
    } catch {
      setActionError(t("deal.detailPage.errors.rebase"));
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-4xl">
          <LoadingBlock text={t("deal.detailPage.loading")} rows={4} />
        </div>
      </div>
    );
  }

  if (isError || (!isLoading && !override)) {
    return (
      <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-4xl space-y-3">
          <InlineAlert tone="error" message={t("deal.detailPage.notFound")} />
          <Button variant="secondary" size="sm" onClick={() => navigate(-1)}>
            &larr; {t("deal.detailPage.rebaseForm.cancel", { ns: "common" }) || "Back"}
          </Button>
        </div>
      </div>
    );
  }

  if (!override) return null;

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        {/* Header */}
        <InstructionPageHeader
          breadcrumbs={[
            { label: t("deal.breadcrumbs.project"), to: `/projects/${dealId}` },
            {
              label: t("deal.breadcrumbs.instructions"),
              to: `/projects/${dealId}/instructions`,
            },
            {
              label: t("deal.breadcrumbs.overrides"),
              to: `/projects/${dealId}/instructions/overrides`,
            },
            { label: override.id.slice(0, 8) + "…" },
          ]}
          title={t("deal.detailPage.title")}
          subtitle={override.change_summary ?? override.id}
          rightSlot={
            <div className="flex items-center gap-2">
              <OverrideStatusBadge
                status={override.status}
                isStale={override.is_stale}
                size="sm"
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refetch()}
                aria-label={t("actions.refresh", { ns: "common" }) || "Refresh"}
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </div>
          }
        />

        <InlineAlert tone="error" message={actionError} />
        <InlineAlert tone="success" message={actionSuccess} />

        {/* Stale warning с rebase кнопкой */}
        {override.is_stale && (
          <StaleWarningBanner
            scope="deal"
            onRebase={() => {
              setRebasePatchOps(override.patch_ops);
              setShowRebaseForm(true);
            }}
            isRebasing={rebaseMutation.isPending}
          />
        )}

        {/* Meta */}
        <div className="grid grid-cols-2 gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-[11px] sm:grid-cols-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("deal.detailPage.meta.id")}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-[var(--text-primary)]">
              {override.id}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("deal.detailPage.meta.baseVersion")}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-[var(--text-primary)]">
              {override.instruction_version_id?.slice(0, 8) ?? "…"}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("deal.detailPage.meta.scope")}
            </div>
            <div className="mt-0.5 font-semibold text-[var(--text-primary)]">
              {override.override_scope}
            </div>
          </div>
        </div>

        {/* Patch ops */}
        <PageSection title={t("deal.detailPage.patchOps.title")}>
          <PatchOpsEditor
            value={override.patch_ops}
            onChange={() => {}}
            disabled={true}
            label={t("deal.detailPage.patchOps.label")}
          />
        </PageSection>

        {/* Rebase form */}
        {showRebaseForm && (
          <PageSection title={t("deal.detailPage.rebaseForm.title")}>
            <div className="space-y-3">
              <p className="text-[11px] text-[var(--text-secondary)]">
                {t("deal.detailPage.rebaseForm.description")}
              </p>

              <Field label={t("deal.detailPage.rebaseForm.newBaseVersionId")} required>
                <input
                  type="text"
                  value={newBaseVersionId}
                  onChange={(e) => setNewBaseVersionId(e.target.value)}
                  className={inputClassName}
                  placeholder={t("deal.detailPage.rebaseForm.newBaseVersionPlaceholder") || "uuid..."}
                  disabled={rebaseMutation.isPending}
                />
              </Field>

              <PatchOpsEditor
                value={rebasePatchOps}
                onChange={setRebasePatchOps}
                disabled={rebaseMutation.isPending}
                label={t("deal.detailPage.rebaseForm.patchOpsLabel")}
              />

              <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] pt-3">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowRebaseForm(false)}
                  disabled={rebaseMutation.isPending}
                >
                  {t("actions.cancel", { ns: "common" })}
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void handleRebase()}
                  isLoading={rebaseMutation.isPending}
                  disabled={
                    !newBaseVersionId.trim() || rebaseMutation.isPending
                  }
                >
                  {t("deal.detailPage.rebaseForm.submit")}
                </Button>
              </div>
            </div>
          </PageSection>
        )}

        {/* Validation */}
        {override.status === "draft" && (
          <PageSection title={t("deal.detailPage.validation.title")}>
            <div className="space-y-3">
              {validationResult && (
                <div
                  className={[
                    "rounded-xl border px-4 py-3",
                    validationResult.is_valid
                      ? "border-[var(--color-success-border)] bg-[var(--color-success-bg)]"
                      : "border-[var(--color-error-border)] bg-[var(--color-error-bg)]",
                  ].join(" ")}
                >
                  <div
                    className={[
                      "text-xs font-semibold",
                      validationResult.is_valid
                        ? "text-[var(--color-success-text)]"
                        : "text-[var(--color-error-text)]",
                    ].join(" ")}
                  >
                    {validationResult.is_valid
                      ? t("deal.detailPage.validation.success")
                      : t("deal.detailPage.validation.failed")}
                  </div>
                  {validationResult.errors.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {validationResult.errors.map((e, i) => (
                        <li key={i} className="text-[11px] text-[var(--color-error-text)]">
                          • {e}
                        </li>
                      ))}
                    </ul>
                  )}
                  {validationResult.checks_count != null && (
                    <div className="mt-1 text-[11px] text-[var(--text-muted)]">
                      Checks: {validationResult.checks_count}
                    </div>
                  )}
                </div>
              )}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleValidate()}
                isLoading={validateMutation.isPending}
                disabled={validateMutation.isPending}
              >
                {t("deal.detailPage.validation.action")}
              </Button>
            </div>
          </PageSection>
        )}

        {/* Actions */}
        <PageSection title={t("deal.detailPage.actions.title")}>
          <div className="flex flex-wrap items-center gap-2">
            {canActivate && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => void handleActivate()}
                isLoading={activateMutation.isPending}
                disabled={activateMutation.isPending}
              >
                {t("deal.detailPage.actions.activate")}
              </Button>
            )}
            {override.is_stale && (
              <p className="text-[11px] text-[var(--color-error-text)]">
                {t("deal.detailPage.actions.rebaseWarning")}
              </p>
            )}
            {canArchive && (
              <Button
                variant="danger"
                size="sm"
                onClick={() => setShowArchiveDialog(true)}
                disabled={
                  archiveMutation.isPending || activateMutation.isPending
                }
              >
                {t("deal.detailPage.actions.archive")}
              </Button>
            )}
          </div>
        </PageSection>
      </div>

      <ConfirmDialog
        open={showArchiveDialog}
        title={t("deal.detailPage.archiveDialog.title")}
        description={t("deal.detailPage.archiveDialog.description")}
        confirmLabel={t("deal.detailPage.actions.archive")}
        cancelLabel={t("actions.cancel", { ns: "common" })}
        isConfirming={archiveMutation.isPending}
        onConfirm={() => void handleArchiveConfirm()}
        onCancel={() => setShowArchiveDialog(false)}
      />
    </div>
  );
};

export default DealOverrideDetailPage;



