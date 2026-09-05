// =============================================================
// src/pages/NewProjectPage.tsx
//
// 2 колонки:
// ~60% — Flow
// ~40% — Готовность + сводка
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import client from "../api/client";
import { useDeal } from "../api/deals";
import { useDocuments } from "../api/documents";
import { queryKeys } from "../api/queryKeys";
import { useStartRun } from "../api/runs";
import { useAuth } from "../hooks/useAuth";
import { useUIStore } from "../stores/uiStore";
import {
  formatLangLabel,
  shouldPollDealLanguageDiscovery,
} from "../utils/languageDiscovery";

import type { RunChecksMode } from "../types";

import FlowBlock from "../components/new-project/FlowBlock";
import type { FlowBlockStatus } from "../components/new-project/FlowBlock";
import ReadinessRail from "../components/new-project/ReadinessRail";
import FlowVisualRail from "../components/new-project/FlowVisualRail";
import type { FlowSummaryData } from "../components/new-project/FlowSummary";

import Block1ProjectInfo from "../components/new-project/Block1ProjectInfo";
import Block2Upload from "../components/new-project/Block2Upload";
import Block3Playbook from "../components/new-project/Block3Playbook";
import Block4ModelConfig from "../components/new-project/Block4ModelConfig";
import Block5Language from "../components/new-project/Block5Language";
import Block6Launch from "../components/new-project/Block6Launch";

import ConfirmDialog from "../components/ConfirmDialog";
import Button from "../components/ui/Button";

interface DealCreateResponse {
  id: string;
}

const DEAL_POLL_INTERVAL = 4000;

const NewProjectPage: React.FC = () => {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { globalRole, userId } = useAuth();

  const setProjectRole = useUIStore((s) => s.setProjectRole);

  const canCreate =
    globalRole === "superadmin" || globalRole === "tenant_admin";

  React.useEffect(() => {
    if (!canCreate) {
      navigate("/dashboard", { replace: true });
    }
  }, [canCreate, navigate]);

  // ───────────── STATE ─────────────

  const [projectName, setProjectName] = React.useState("");
  const [createdDealId, setCreatedDealId] = React.useState<string | null>(null);
  const [isCreating, setIsCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  const [playbookSummary, setPlaybookSummary] =
    React.useState<string | null>(null);
  const [modelConfigSummary, setModelConfigSummary] =
    React.useState<string | null>(null);

  const [block4Done, setBlock4Done] = React.useState(false);

  const [languageSummary, setLanguageSummary] =
    React.useState<string | null>(null);

  const [checksMode, setChecksMode] =
    React.useState<RunChecksMode>("global_and_doc_type");
  const [forceReclassify, setForceReclassify] = React.useState(false);
  const [launchError, setLaunchError] = React.useState<string | null>(null);

  /**
   * Какой завершённый шаг сейчас открыт на редактирование.
   * null = обычный flow без ручного редактирования.
   */
  const [editingStep, setEditingStep] = React.useState<number | null>(null);

  const [showExitConfirm, setShowExitConfirm] = React.useState(false);

  // Защита от случайного закрытия вкладки браузера (F5 или крестик)
  React.useEffect(() => {
    const isDirty = projectName.trim().length > 0 || createdDealId !== null;
    if (!isDirty) return;

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [projectName, createdDealId]);

  // ───────────── DATA ─────────────

  // Сначала инициализируем документы и их количество
  const {
    data: documentsPage,
    isLoading: isDocumentsLoading,
    refetch: refetchDocuments,
  } = useDocuments(createdDealId ?? "", 1);

  const documentsCount = documentsPage?.total ?? 0;
  const startRun = useStartRun(createdDealId ?? "");

  // Теперь useDeal может безопасно использовать documentsCount!
  const { data: deal, refetch: refetchDeal } = useDeal(createdDealId, {
    refetchInterval: (query) => {
      const dealData = query.state.data;
      const status = dealData?.language_discovery_status;
      const langs = dealData?.languages;

      // 1. Discovery явно в процессе (pending/processing) — опрашиваем
      if (shouldPollDealLanguageDiscovery(status)) {
        return DEAL_POLL_INTERVAL;
      }

      // 2. Документы загружены, но языки ещё не определены
      if (
        documentsCount > 0 &&
        (!langs || langs.length === 0) &&
        status !== "failed"
      ) {
        return DEAL_POLL_INTERVAL;
      }

      return false;
    },
  });

  // При изменении числа документов — переполучаем сделку,
  // чтобы React Query узнал актуальный статус language discovery.
  // Без этого polling не включится: кэш хранит status=null
  // от момента создания сделки, а воркер уже ставит "pending".
  React.useEffect(() => {
    if (createdDealId && documentsCount > 0) {
      refetchDeal();
    }
  }, [createdDealId, documentsCount, refetchDeal]);

  // ───────────── CREATE DEAL ─────────────

  const handleCreateProject = async () => {
    if (!projectName.trim()) {
      setCreateError(t("newProject.errors.nameRequired"));
      return;
    }

    setIsCreating(true);
    setCreateError(null);

    try {
      const res = await client.post<DealCreateResponse>(
        "/api/v1/deals",
        { name: projectName.trim() },
      );

      setCreatedDealId(res.data.id);
      setProjectRole(res.data.id, "admin");

      await queryClient.invalidateQueries({
        queryKey: queryKeys.userProjects(userId ?? "anonymous"),
      });

    } catch (err: any) {
      setCreateError(err?.detail || t("newProject.errors.createFailed"));
    } finally {
      setIsCreating(false);
    }
  };

  // ───────────── CALLBACKS ─────────────

  const handlePlaybookApplied = (_: string, label: string) => {
    setPlaybookSummary(label);
    refetchDeal();
    setEditingStep(null);
  };

  const handleModelConfigApplied = (_: string, label: string) => {
    setModelConfigSummary(label);
    setBlock4Done(true);
    refetchDeal();
    setEditingStep(null);
  };

  const handleModelConfigSkipped = () => {
    setModelConfigSummary(t("newProject.defaults.defaultModelConfig"));
    setBlock4Done(true);
    setEditingStep(null);
  };

  const handleLanguageSet = (_: string, label: string) => {
    setLanguageSummary(label);
    refetchDeal();
    setEditingStep(null);
  };

  const handleLaunch = () => {
    if (!createdDealId) return;

    startRun.mutate(
      {
        profile: "core",
        checks_mode: checksMode,
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: () =>
          navigate(`/projects/${createdDealId}?tab=overview`),
        onError: () =>
          setLaunchError(t("newProject.errors.launchFailed")),
      },
    );
  };

  // ───────────── STATUS ─────────────

  const hasDocuments = documentsCount > 0;
  const hasPlaybook = !!deal?.playbook_version_id;
  const hasLanguage = !!deal?.primary_language;
  const block1Done = !!createdDealId;
  const isEditMode = editingStep !== null;

  const block1BaseStatus: FlowBlockStatus =
    block1Done ? "done" : "active";

  const block2BaseStatus: FlowBlockStatus =
    !createdDealId ? "disabled" :
    hasDocuments ? "done" : "active";

  const block3BaseStatus: FlowBlockStatus =
    !hasDocuments ? "disabled" :
    hasPlaybook ? "done" : "active";

  const block4BaseStatus: FlowBlockStatus =
    !hasPlaybook ? "disabled" :
    block4Done ? "done" : "active";

  const block5BaseStatus: FlowBlockStatus =
    !hasPlaybook ? "disabled" :
    hasLanguage ? "done" : "active";

  const block6BaseStatus: FlowBlockStatus =
    !hasLanguage ? "disabled" : "active";

  const resolveStatus = (
    step: number,
    baseStatus: FlowBlockStatus,
  ): FlowBlockStatus => {
    if (editingStep === null) {
      return baseStatus;
    }

    if (step > editingStep) {
      return "disabled";
    }

    if (step === editingStep) {
      return baseStatus === "disabled" ? "disabled" : "active";
    }

    return baseStatus === "disabled" ? "disabled" : "done";
  };

  const block1Status = resolveStatus(1, block1BaseStatus);
  const block2Status = resolveStatus(2, block2BaseStatus);
  const block3Status = resolveStatus(3, block3BaseStatus);
  const block4Status = resolveStatus(4, block4BaseStatus);
  const block5Status = resolveStatus(5, block5BaseStatus);
  const block6Status = resolveStatus(6, block6BaseStatus);

  // ───────────── SUMMARY ─────────────

  const documentsSummary = documentsCount > 0
    ? t("flowSummary.documentsCount", { count: documentsCount })
    : null;

  const normalizedPrimaryLanguage =
    languageSummary ??
    (deal?.primary_language ? formatLangLabel(deal.primary_language) : null);

  const effectiveModelConfigSummary =
    modelConfigSummary ??
    deal?.model_config_name ??
    (hasPlaybook ? t("newProject.defaults.defaultModelConfig") : null);

  const summaryData: FlowSummaryData = {
    projectName: projectName.trim() || null,
    documentsCount,
    playbookLabel: playbookSummary,
    modelConfigLabel: effectiveModelConfigSummary,
    primaryLanguage: normalizedPrimaryLanguage,
  };

  const readinessData = {
    hasProject: block1Done,
    hasDocuments,
    hasPlaybook,
    hasLanguage,
  };

  const requiredStepsDone = [
    readinessData.hasProject,
    readinessData.hasDocuments,
    readinessData.hasPlaybook,
    readinessData.hasLanguage,
  ].filter(Boolean).length;

  const requiredStepsTotal = 4;

  const getBackProps = (step: number) =>
    editingStep === step
      ? {
          onBackRequest: () => setEditingStep(null),
          backLabel: t("newProject.steps.closeEdit"),
        }
      : {};

  if (!canCreate) return null;

  // ───────────── RENDER ─────────────

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein p-4 md:p-5">

        {/* HEADER */}
        <header className="mb-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-xl font-semibold">
                {t("newProject.header.title")}
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                {t("newProject.header.subtitle")}
              </p>
            </div>

            <div className="flex items-center gap-4">
              {requiredStepsDone > 0 && (
                <div className="hidden rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-1.5 md:block">
                  <span className="text-[11px] font-semibold text-[var(--text-muted)]">
                    {t("newProject.header.readyProgress", { done: requiredStepsDone, total: requiredStepsTotal })}
                  </span>
                </div>
              )}
              
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowExitConfirm(true)}
              >
                {createdDealId ? t("newProject.header.defer") : t("newProject.header.cancel")}
              </Button>
            </div>
          </div>
        </header>

        {/* 3 COLUMNS */}
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr_1fr]">
          {/* FLOW */}
          <div className="space-y-4">
            <FlowBlock
              step={1}
              title={t("newProject.steps.step1Title")}
              status={block1Status}
              summary={projectName.trim() || undefined}
            >
              <Block1ProjectInfo
                projectName={projectName}
                onProjectNameChange={setProjectName}
                onCreateProject={handleCreateProject}
                onCancel={() => setShowExitConfirm(true)}
                isSubmitting={isCreating}
                isCreated={!!createdDealId}
                errorText={createError}
              />
            </FlowBlock>

            <FlowBlock
              step={2}
              title={t("newProject.steps.step2Title")}
              status={block2Status}
              summary={documentsSummary ?? undefined}
              onEditRequest={
                !isEditMode && hasDocuments
                  ? () => setEditingStep(2)
                  : undefined
              }
              {...getBackProps(2)}
            >
              {createdDealId && (
                <Block2Upload
                  dealId={createdDealId}
                  confirmedDocumentsCount={documentsCount}
                  isDocumentsLoading={isDocumentsLoading}
                  onRefetchDocuments={refetchDocuments}
                />
              )}
            </FlowBlock>

            <FlowBlock
              step={3}
              title={t("newProject.steps.step3Title")}
              status={block3Status}
              summary={playbookSummary ?? undefined}
              onEditRequest={
                !isEditMode && hasPlaybook
                  ? () => setEditingStep(3)
                  : undefined
              }
              {...getBackProps(3)}
            >
              {createdDealId && (
                <Block3Playbook
                  dealId={createdDealId}
                  currentVersionId={deal?.playbook_version_id ?? null}
                  onApplied={handlePlaybookApplied}
                />
              )}
            </FlowBlock>

            <FlowBlock
              step={4}
              title={t("newProject.steps.step4Title")}
              status={block4Status}
              summary={effectiveModelConfigSummary ?? undefined}
              onEditRequest={
                !isEditMode && hasPlaybook
                  ? () => setEditingStep(4)
                  : undefined
              }
              {...getBackProps(4)}
            >
              {createdDealId && (
                <Block4ModelConfig
                  dealId={createdDealId}
                  currentConfigId={deal?.model_config_id ?? null}
                  currentConfigName={deal?.model_config_name ?? null}
                  onApplied={handleModelConfigApplied}
                  onSkipped={handleModelConfigSkipped}
                />
              )}
            </FlowBlock>

            <FlowBlock
              step={5}
              title={t("newProject.steps.step5Title")}
              status={block5Status}
              summary={normalizedPrimaryLanguage ?? undefined}
              onEditRequest={
                !isEditMode && hasLanguage
                  ? () => setEditingStep(5)
                  : undefined
              }
              {...getBackProps(5)}
            >
              {createdDealId && deal && (
                <Block5Language
                  dealId={createdDealId}
                  languages={deal.languages ?? []}
                  primaryLanguage={deal.primary_language ?? null}
                  discoveryStatus={deal.language_discovery_status ?? null}
                  onLanguageSet={handleLanguageSet}
                />
              )}
            </FlowBlock>

            <FlowBlock
              step={6}
              title={t("newProject.steps.step6Title")}
              status={block6Status}
            >
              <Block6Launch
                checksMode={checksMode}
                onChecksModeChange={setChecksMode}
                forceReclassify={forceReclassify}
                onForceReclassifyChange={setForceReclassify}
                showForceReclassify={
                  deal?.has_pending_manual_reclassifications ?? false
                }
                canLaunch={
                  !!createdDealId &&
                  hasDocuments &&
                  hasPlaybook &&
                  hasLanguage
                }
                isSubmitting={startRun.isPending}
                errorText={launchError}
                onLaunch={handleLaunch}
              />
            </FlowBlock>
          </div>

          {/* RIGHT RAIL — готовность + сводка */}
          <div className="hidden xl:block">
            <ReadinessRail
              readiness={readinessData}
              summary={summaryData}
            />
          </div>

          {/* FAR-RIGHT RAIL — визуал */}
          <div className="hidden xl:block">
            <FlowVisualRail />
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={showExitConfirm}
        title={createdDealId ? t("newProject.exitConfirm.titleDefer") : t("newProject.exitConfirm.titleCancel")}
        description={createdDealId ? t("newProject.exitConfirm.descDefer") : t("newProject.exitConfirm.descCancel")}
        confirmLabel={createdDealId ? t("newProject.exitConfirm.confirmExit") : t("newProject.exitConfirm.confirmCancel")}
        cancelLabel={t("newProject.exitConfirm.stay")}
        onConfirm={() => navigate("/dashboard")}
        onCancel={() => setShowExitConfirm(false)}
      />
    </div>
  );
};

export default NewProjectPage;


