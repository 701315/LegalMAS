// src/pages/tenant-instructions/TenantOverrideDetailPage.tsx

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import {
  useTenantOverrides,
  useValidateTenantOverride,
  useActivateTenantOverride,
  useArchiveTenantOverride,
} from "../../hooks/instructions/useInstructionOverrides";
import { useAuth } from "../../hooks/useAuth";
import OverrideStatusBadge from "../../components/instructions/OverrideStatusBadge";
import StaleWarningBanner from "../../components/instructions/StaleWarningBanner";
import PatchOpsEditor from "../../components/instructions/PatchOpsEditor";
import LoadingBlock from "../../components/ui/LoadingBlock";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import ConfirmDialog from "../../components/ConfirmDialog";
import type {
  InstructionOverrideValidationResponse,
  JsonPatchOperation,
} from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// MetaItem
// ─────────────────────────────────────────────────────────────

const MetaItem: React.FC<{ label: string; value: string }> = ({
  label,
  value,
}) => (
  <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2.5">
    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
      {label}
    </p>
    <p className="mt-0.5 break-all font-mono text-[11px] text-[var(--text-primary)]">
      {value}
    </p>
  </div>
);

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const TenantOverrideDetailPage: React.FC = () => {
  const { t } = useTranslation("instructions");
  const { overrideId } = useParams<{ overrideId: string }>();
  const navigate = useNavigate();

  const { tenantId: authTenantId } = useAuth();
  const tenantId = authTenantId ?? "";

  const { data, isLoading, isError, refetch } = useTenantOverrides(
    tenantId || null,
  );
  const override = data?.items.find((o) => o.id === overrideId) ?? null;

  const validateMut = useValidateTenantOverride();
  const activateMut = useActivateTenantOverride();
  const archiveMut = useArchiveTenantOverride();

  const [validationResult, setValidationResult] =
    useState<InstructionOverrideValidationResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [showArchiveDialog, setShowArchiveDialog] = useState(false);

  const patchOps: JsonPatchOperation[] = override?.patch_ops ?? [];

  const canActivate = override?.status === "draft" && !override?.is_stale;
  const canArchive =
    override?.status === "draft" || override?.status === "active";

  const handleValidate = async () => {
    if (!tenantId || !overrideId) return;
    setActionError(null);
    setValidationResult(null);
    try {
      const result = await validateMut.mutateAsync({ tenantId, overrideId });
      setValidationResult(result);
    } catch {
      setActionError(t("tenantOverride.detailPage.errors.validate"));
    }
  };

  const handleActivate = async () => {
    if (!tenantId || !overrideId) return;
    setActionError(null);
    setActionSuccess(null);
    try {
      await activateMut.mutateAsync({ tenantId, overrideId });
      setActionSuccess(t("tenantOverride.detailPage.success.activate"));
      await refetch();
    } catch {
      setActionError(t("tenantOverride.detailPage.errors.activate"));
    }
  };

  const handleArchiveConfirm = async () => {
    if (!tenantId || !overrideId) return;
    setActionError(null);
    try {
      await archiveMut.mutateAsync({ tenantId, overrideId });
      setShowArchiveDialog(false);
      setActionSuccess(t("tenantOverride.detailPage.success.archive"));
      await refetch();
    } catch {
      setShowArchiveDialog(false);
      setActionError(t("tenantOverride.detailPage.errors.archive"));
    }
  };

  // ── Loading ─────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein p-4 md:p-5">
          <LoadingBlock text={t("tenantOverride.detailPage.loading")} rows={4} />
        </div>
      </div>
    );
  }

  // ── Error / not found ───────────────────────────────────────

  if (isError || (!isLoading && !override)) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein space-y-4 p-4 md:p-5">
          <InlineAlert
            tone="error"
            message={t("tenantOverride.detailPage.notFound")}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate("/tenant-admin/instructions/overrides")}
            leftIcon={<ArrowLeft className="h-3.5 w-3.5" />}
          >
            {t("tenantOverride.detailPage.backToList")}
          </Button>
        </div>
      </div>
    );
  }

  if (!override) return null;

  const baseVersionId =
    override.global_instruction_version_id ??
    override.instruction_version_id ??
    null;

  return (
    <>
      <div className="h-full overflow-y-auto overscroll-contain">
        <div className="animate-fadein space-y-4 p-4 md:p-5">

          {/* ── Шапка ───────────────────────────────────────────── */}
          <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <button
                  type="button"
                  onClick={() =>
                    navigate("/tenant-admin/instructions/overrides")
                  }
                  className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  {t("tenantOverride.detailPage.backLabel")}
                </button>

                <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                  {t("tenantOverride.detailPage.title")}
                </h1>
                {override.change_summary && (
                  <p className="mt-2 text-sm text-[var(--text-secondary)]">
                    {override.change_summary}
                  </p>
                )}
              </div>

              <OverrideStatusBadge
                status={override.status}
                isStale={override.is_stale}
                size="sm"
              />
            </div>
          </header>

          {/* ── Alerts ──────────────────────────────────────────── */}
          {actionError && <InlineAlert tone="error" message={actionError} />}
          {actionSuccess && <InlineAlert tone="success" message={actionSuccess} />}

          {/* ── Stale warning ────────────────────────────────────── */}
          {override.is_stale && <StaleWarningBanner scope="tenant" />}

          {/* ── Детали ──────────────────────────────────────────── */}
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              {t("tenantOverride.detailPage.details.title")}
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <MetaItem
                label={t("tenantOverride.detailPage.details.overrideId")}
                value={override.id}
              />
              <MetaItem
                label={t("tenantOverride.detailPage.details.baseVersion")}
                value={baseVersionId ? `${baseVersionId.slice(0, 8)}…` : "—"}
              />
              <MetaItem
                label={t("tenantOverride.detailPage.details.baseHash")}
                value={`${override.base_content_hash.slice(0, 12)}…`}
              />
            </div>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <MetaItem
                label={t("tenantOverride.detailPage.details.scope")}
                value={
                  override.global_instruction_version_id
                    ? t("tenantOverride.detailPage.details.scopeGlobal")
                    : t("tenantOverride.detailPage.details.scopeDocType")
                }
              />
              <MetaItem
                label={t("tenantOverride.detailPage.details.patchOps")}
                value={t("tenantOverride.detailPage.details.patchOpsCount", {
                  count: patchOps.length,
                })}
              />
            </div>
          </section>

          {/* ── Patch Operations ─────────────────────────────────── */}
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              {t("tenantOverride.detailPage.patchOps.title")}
            </h2>
            <PatchOpsEditor
              value={patchOps}
              onChange={() => {
                /* read-only */
              }}
              disabled={true}
              label={t("tenantOverride.detailPage.patchOps.label")}
            />
            <p className="mt-3 text-xs text-[var(--text-muted)]">
              {t("tenantOverride.detailPage.patchOps.readOnlyHint")}
            </p>
          </section>

          {/* ── Валидация ────────────────────────────────────────── */}
          {override.status === "draft" && (
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                {t("tenantOverride.detailPage.validation.title")}
              </h2>
              <div className="space-y-3">
                {validationResult && (
                  <div
                    className={[
                      "rounded-xl border p-4",
                      validationResult.is_valid
                        ? "border-[var(--color-success-border)] bg-[var(--color-success-bg)]"
                        : "border-[var(--color-error-border)] bg-[var(--color-error-bg)]",
                    ].join(" ")}
                  >
                    <p
                      className={[
                        "text-xs font-semibold",
                        validationResult.is_valid
                          ? "text-[var(--color-success-text)]"
                          : "text-[var(--color-error-text)]",
                      ].join(" ")}
                    >
                      {validationResult.is_valid
                        ? t("tenantOverride.detailPage.validation.success")
                        : t("tenantOverride.detailPage.validation.failed")}
                    </p>
                    {validationResult.errors.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {validationResult.errors.map((e, i) => (
                          <li
                            key={i}
                            className="text-[11px] text-[var(--color-error-text)]"
                          >
                            • {e}
                          </li>
                        ))}
                      </ul>
                    )}
                    {validationResult.checks_count != null && (
                      <p className="mt-2 text-[11px] text-[var(--text-muted)]">
                        Checks: {validationResult.checks_count}
                      </p>
                    )}
                  </div>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleValidate()}
                  isLoading={validateMut.isPending}
                  disabled={validateMut.isPending}
                >
                  {t("tenantOverride.detailPage.validation.action")}
                </Button>
              </div>
            </section>
          )}

          {/* ── Действия ─────────────────────────────────────────── */}
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
            <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              {t("tenantOverride.detailPage.actions.title")}
            </h2>
            <div className="flex flex-wrap items-center gap-3">
              {canActivate && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void handleActivate()}
                  isLoading={activateMut.isPending}
                  disabled={activateMut.isPending}
                >
                  {t("tenantOverride.detailPage.actions.activate")}
                </Button>
              )}

              {override.is_stale && override.status === "draft" && (
                <p className="text-[11px] text-[var(--color-error-text)]">
                  {t("tenantOverride.detailPage.actions.staleWarning")}
                </p>
              )}

              {canArchive && (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setShowArchiveDialog(true)}
                  disabled={archiveMut.isPending || activateMut.isPending}
                >
                  {t("tenantOverride.detailPage.actions.archive")}
                </Button>
              )}

              {override.status === "archived" && (
                <p className="text-[11px] text-[var(--text-muted)]">
                  {t("tenantOverride.detailPage.actions.archivedHint")}
                </p>
              )}
            </div>
          </section>

        </div>
      </div>

      <ConfirmDialog
        open={showArchiveDialog}
        title={t("tenantOverride.detailPage.archiveDialog.title")}
        description={t("tenantOverride.detailPage.archiveDialog.description")}
        confirmLabel={t("tenantOverride.detailPage.archiveDialog.confirm")}
        cancelLabel={t("actions.cancel", { ns: "common" })}
        isConfirming={archiveMut.isPending}
        onConfirm={() => void handleArchiveConfirm()}
        onCancel={() => setShowArchiveDialog(false)}
      />
    </>
  );
};

export default TenantOverrideDetailPage;


