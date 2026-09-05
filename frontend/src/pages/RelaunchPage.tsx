// =============================================================
// src/pages/RelaunchPage.tsx
// Dedicated page for restarting the project analysis run.
//
// Architectural solution:
// - Rendered as a full page inside AppShell (via Outlet);
// - Has its own native URL: /projects/:dealId/relaunch;
// - Native browser back button works seamlessly;
// - Upon successful launch: invalidate queries + navigate back;
// - Utilizes LaunchWideOverlay with variant="inline" as core content.
//
// State ownership:
// - Deal is fetched via useDeal query (as in DealRouteWrapper);
// - launchDealPatch — local optimistic patch for primary_language;
// - checksMode / forceReclassify — local form state;
// - Upon submit — invalidates all dependent queries and navigate(-1).
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import type { Deal } from "../types";
import { useDeal } from "../api/deals";
import { useSetPrimaryLanguage, useUpdateDeal } from "../api/deals";
import { useDocuments } from "../api/documents";
import { useDealPermissions } from "../hooks/usePermissions";
import { runKeys, useStartRun } from "../api/runs";
import { queryKeys } from "../api/queryKeys";
import { useAuth } from "../hooks/useAuth";
import {
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../utils/languageDiscovery";
import LaunchWideOverlay from "./tabs/overview/LaunchWideOverlay";
import type { ChecksMode } from "./tabs/OverviewTab";
import Button from "../components/ui/Button";

const POLL_INTERVAL = 4000;

function shouldPollDealLanguageDiscovery(
  status: string | null | undefined,
): boolean {
  return status === "pending" || status === "processing";
}

const RelaunchPage: React.FC = () => {
  const { t } = useTranslation("projects");
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { userId } = useAuth();

  const {
    data: deal,
    isLoading,
    isError,
    error,
  } = useDeal(dealId ?? null, {
    refetchInterval: (query) =>
      shouldPollDealLanguageDiscovery(
        query.state.data?.language_discovery_status,
      )
        ? POLL_INTERVAL
        : false,
  });

  const { data: documentsPage } = useDocuments(dealId ?? "", 1);
  const documentsCount = documentsPage?.total ?? 0;
  const { canStartRun, canUploadDocuments } = useDealPermissions(
    dealId ?? "",
  );

  const startRun = useStartRun(dealId ?? "");
  const updateDealForLaunch = useUpdateDeal(dealId ?? "");
  const setPrimaryLanguage = useSetPrimaryLanguage(dealId ?? "");

  const [checksMode, setChecksMode] =
    React.useState<ChecksMode>("global_and_doc_type");
  const [forceReclassify, setForceReclassify] = React.useState(false);
  const [launchDealPatch, setLaunchDealPatch] = React.useState<Partial<Deal>>(
    {},
  );

  // Reset local patch when dealId, playbook, or primary language changes
  const dealLanguagesKey = JSON.stringify(deal?.languages ?? []);
  React.useEffect(() => {
    setLaunchDealPatch({});
  }, [
    deal?.id,
    deal?.playbook_version_id,
    deal?.primary_language,
    deal?.language_discovery_status,
    dealLanguagesKey,
  ]);

  if (isLoading || !dealId) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-[var(--text-muted)]">
        {t("pages.relaunch.loading")}
      </div>
    );
  }

  if (isError || !deal) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-sm">
        <p className="text-[var(--color-error-text)]">
          {error instanceof Error
            ? error.message
            : t("pages.relaunch.loadError")}
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => navigate("/dashboard")}
        >
          {t("pages.relaunch.backToProjects")}
        </Button>
      </div>
    );
  }

  const currentRunId = deal.last_run_id ?? null;
  const hasCurrentRun = currentRunId !== null;
  const effectiveDeal: Deal = { ...deal, ...launchDealPatch };

  const discoveryStatus = normalizeDiscoveryStatus(
    effectiveDeal.language_discovery_status,
  );
  const isLanguageDiscoveryBlocking =
    discoveryStatus === "pending" || discoveryStatus === "processing";

  const canLaunchRun =
    canStartRun &&
    documentsCount > 0 &&
    !!effectiveDeal.playbook_version_id &&
    !!effectiveDeal.primary_language &&
    !isLanguageDiscoveryBlocking &&
    !startRun.isPending &&
    !updateDealForLaunch.isPending &&
    !setPrimaryLanguage.isPending;

  const isSubmitting =
    startRun.isPending ||
    updateDealForLaunch.isPending ||
    setPrimaryLanguage.isPending;

  const handlePrimaryLanguageChange = (value: string) => {
    const normalizedValue = normalizeLang(value) || null;
    setLaunchDealPatch((prev) => ({
      ...prev,
      primary_language: normalizedValue,
    }));
    setPrimaryLanguage.mutate(
      { primary_language: normalizedValue },
      {
        onError: () => {
          setLaunchDealPatch((prev) => ({
            ...prev,
            primary_language: deal.primary_language ?? null,
          }));
        },
      },
    );
  };

  const handleDealPatched = async (patch?: Partial<Deal>) => {
    if (patch && Object.keys(patch).length > 0) {
      setLaunchDealPatch((prev) => ({ ...prev, ...patch }));
    }
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
    ]);
  };

  const handleSubmit = () => {
    if (!canLaunchRun) return;
    startRun.mutate(
      {
        profile: "core",
        checks_mode: checksMode,
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: async (run) => {
          setForceReclassify(false);
          await Promise.all([
            qc.invalidateQueries({ queryKey: runKeys.detail(run.id, true) }),
            qc.invalidateQueries({ queryKey: runKeys.detail(run.id, false) }),
            qc.invalidateQueries({
              queryKey: runKeys.classificationReport(run.id),
            }),
            qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
            qc.invalidateQueries({ queryKey: runKeys.history(deal.id, false) }),
            qc.invalidateQueries({ queryKey: runKeys.history(deal.id, true) }),
            qc.invalidateQueries({ queryKey: queryKeys.userProjects(userId ?? "") }),
          ]);
          // Return to the previous project dashboard
          navigate(`/projects/${deal.id}`, { replace: true });
        },
      },
    );
  };

  const handleCancel = () => {
    navigate(`/projects/${deal.id}`);
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      {/* ── Page Header ────────────────────────────────────────────────
          Standardized project header pattern.
          Breadcrumbs: Project Name › Relaunch analysis.
          Cancel button navigates back to the main project page. */}
      <header className="shrink-0 border-b border-[var(--border)] bg-[var(--bg-card)] px-5 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-primary)]"
                aria-hidden
              />
              <button
                type="button"
                onClick={handleCancel}
                className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--text-secondary)] transition hover:text-[var(--accent-primary)]"
              >
                <ArrowLeft className="h-3 w-3" aria-hidden />
                {deal.name}
              </button>
              <span className="text-xs text-[var(--text-muted)]">›</span>
              <span className="text-xs font-semibold text-[var(--accent-primary)]">
                {hasCurrentRun ? t("pages.relaunch.relaunchTitle") : t("pages.relaunch.launchTitle")}
              </span>
            </div>
            <h1 className="mt-2 truncate text-base font-semibold text-[var(--text-primary)]">
              {hasCurrentRun
                ? t("pages.relaunch.relaunchDesc")
                : t("pages.relaunch.launchDesc")}
            </h1>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleCancel}
            >
              {t("pages.relaunch.cancel")}
            </Button>
          </div>
        </div>
      </header>

      {/* ── Launch Content ─────────────────────────────────────────────
          LaunchWideOverlay with variant="inline" renders directly in-flow
          within the scrollable page container. Subpanes (Upload, Playbook,
          ModelConfig) work natively. */}
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="p-4 lg:p-6">
          <LaunchWideOverlay
            variant="inline"
            open={true}
            deal={effectiveDeal}
            hasCurrentRun={hasCurrentRun}
            documentsCount={documentsCount}
            checksMode={checksMode}
            onChecksModeChange={setChecksMode}
            forceReclassify={forceReclassify}
            onForceReclassifyChange={setForceReclassify}
            canStartRun={canLaunchRun}
            canUploadDocuments={canUploadDocuments}
            isSubmitting={isSubmitting}
            onPrimaryLanguageChange={handlePrimaryLanguageChange}
            onSubmit={handleSubmit}
            onClose={handleCancel}
            onDealPatched={handleDealPatched}
          />
        </div>
      </div>
    </div>
  );
};

export default RelaunchPage;


