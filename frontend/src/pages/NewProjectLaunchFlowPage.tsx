// =============================================================
// src/pages/NewProjectLaunchFlowPage.tsx
//
// Единая страница запуска нового проекта.
// 6 последовательных блоков, каждый активируется после предыдущего.
//
// Временно доступна по /projects/new-v2 для тестирования.
// После проверки — заменит /projects/new.
// =============================================================

import React from "react";
import { useNavigate } from "react-router-dom";

import client from "../api/client";
import { useDeal } from "../api/deals";
import { useDocuments } from "../api/documents";
import { useStartRun } from "../api/runs";
import { useAuth } from "../hooks/useAuth";
import { useUIStore } from "../stores/uiStore";
import { shouldPollDealLanguageDiscovery } from "../utils/languageDiscovery";

import type { RunChecksMode } from "../types";

import FlowBlock from "../components/new-project/FlowBlock";
import type { FlowBlockStatus } from "../components/new-project/FlowBlock";
import Block1ProjectInfo from "../components/new-project/Block1ProjectInfo";
import Block1bResponsibleUser from "../components/new-project/Block1bResponsibleUser";
import Block2Upload from "../components/new-project/Block2Upload";
import Block3Playbook from "../components/new-project/Block3Playbook";
import Block4ModelConfig from "../components/new-project/Block4ModelConfig";
import Block5Language from "../components/new-project/Block5Language";
import Block6Launch from "../components/new-project/Block6Launch";

// ── Types ───────────────────────────────────────────────────

interface DealCreatePayload {
  name: string;
  metadata_?: {
    contact_person?: string | null;
  };
}

interface DealCreateResponse {
  id: string;
}

// ── Constants ───────────────────────────────────────────────

const DEAL_POLL_INTERVAL = 4_000;
const TOTAL_STEPS = 6;

// ── Component ───────────────────────────────────────────────

const NewProjectLaunchFlowPage: React.FC = () => {
  const navigate = useNavigate();
  const { globalRole } = useAuth();
  const setProjectRole = useUIStore((s) => s.setProjectRole);

  // ── Access check ──────────────────────────────────────────
  const canCreate =
    globalRole === "superadmin" || globalRole === "tenant_admin";

  React.useEffect(() => {
    if (!canCreate) {
      navigate("/dashboard", { replace: true });
    }
  }, [canCreate, navigate]);

  // ── Block 1 state — project creation ──────────────────────
  const [projectName, setProjectName] = React.useState("");
  const [createdDealId, setCreatedDealId] = React.useState<string | null>(
    null,
  );
  const [isCreating, setIsCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  // ── Block 1b state — responsible user ─────────────────────
  const [block1bDone, setBlock1bDone] = React.useState(false);
  const [responsibleUserName, setResponsibleUserName] = React.useState<
    string | null
  >(null);

  // ── Block 3 state — playbook summary ──────────────────────
  const [playbookSummary, setPlaybookSummary] = React.useState<string | null>(
    null,
  );

  // ── Block 4 state — model config summary ──────────────────
  const [modelConfigSummary, setModelConfigSummary] = React.useState<
    string | null
  >(null);
  const [block4Done, setBlock4Done] = React.useState(false);

  // ── Block 5 state — language summary ──────────────────────
  const [languageSummary, setLanguageSummary] = React.useState<string | null>(
    null,
  );

  // ── Block 6 state — launch config ─────────────────────────
  const [checksMode, setChecksMode] =
    React.useState<RunChecksMode>("global_and_doc_type");
  const [forceReclassify, setForceReclassify] = React.useState(false);
  const [launchError, setLaunchError] = React.useState<string | null>(null);

  // ── Deal polling ──────────────────────────────────────────
  const { data: deal, refetch: refetchDeal } = useDeal(createdDealId, {
    refetchInterval: (query) =>
      shouldPollDealLanguageDiscovery(
        query.state.data?.language_discovery_status,
      )
        ? DEAL_POLL_INTERVAL
        : false,
  });

  // ── Documents polling ─────────────────────────────────────
  const {
    data: documentsPage,
    isLoading: isDocumentsLoading,
    refetch: refetchDocuments,
  } = useDocuments(createdDealId ?? "", 1);

  const documentsCount = documentsPage?.total ?? 0;

  // ── Start run mutation ────────────────────────────────────
  const startRun = useStartRun(createdDealId ?? "");

  // ── Block 1 — create deal ─────────────────────────────────
  const handleCreateProject = React.useCallback(async () => {
    const trimmedName = projectName.trim();

    if (!trimmedName) {
      setCreateError("Укажите название проекта.");
      return;
    }

    setIsCreating(true);
    setCreateError(null);

    try {
      const payload: DealCreatePayload = {
        name: trimmedName,
      };

      const res = await client.post<DealCreateResponse>(
        "/api/v1/deals",
        payload,
      );

      const dealId = res.data.id;
      setCreatedDealId(dealId);
      setProjectRole(dealId, "admin");
    } catch (err: unknown) {
      let message = "Не удалось создать проект. Попробуйте позже.";

      if (typeof err === "object" && err !== null) {
        if ("response" in err) {
          const resp = (err as { response?: { data?: { detail?: string } } })
            .response;

          if (typeof resp?.data?.detail === "string") {
            message = resp.data.detail;
          }
        } else if (
          "detail" in err &&
          typeof (err as { detail?: unknown }).detail === "string"
        ) {
          message = (err as { detail: string }).detail;
        } else if (
          "message" in err &&
          typeof (err as { message?: unknown }).message === "string"
        ) {
          message = (err as { message: string }).message;
        }
      }

      setCreateError(message);
    } finally {
      setIsCreating(false);
    }
  }, [projectName, setProjectRole]);

  // ── Block 1b — responsible user completed ─────────────────
  const handleResponsibleCompleted = React.useCallback(
    (userName: string | null) => {
      setBlock1bDone(true);
      setResponsibleUserName(userName);
    },
    [],
  );

  // ── Block 3 — playbook applied ────────────────────────────
  const handlePlaybookApplied = React.useCallback(
    (_versionId: string, label: string) => {
      setPlaybookSummary(label);
      void refetchDeal();
    },
    [refetchDeal],
  );

  // ── Block 4 — model config applied / skipped ──────────────
  const handleModelConfigApplied = React.useCallback(
    (_configId: string, configName: string) => {
      setModelConfigSummary(configName);
      setBlock4Done(true);
      void refetchDeal();
    },
    [refetchDeal],
  );

  const handleModelConfigSkipped = React.useCallback(() => {
    setModelConfigSummary("По умолчанию");
    setBlock4Done(true);
  }, []);

  // ── Block 5 — language set ────────────────────────────────
  const handleLanguageSet = React.useCallback(
    (_lang: string, label: string) => {
      setLanguageSummary(label);
      void refetchDeal();
    },
    [refetchDeal],
  );

  // ── Block 6 — launch ─────────────────────────────────────
  const handleLaunch = React.useCallback(() => {
    if (!createdDealId) return;

    setLaunchError(null);

    startRun.mutate(
      {
        profile: "core",
        checks_mode: checksMode,
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: () => {
          navigate(`/projects/${createdDealId}?tab=overview`);
        },
        onError: (err) => {
          let message = "Не удалось запустить анализ. Попробуйте ещё раз.";

          if (typeof err === "object" && err !== null && "message" in err) {
            message = (err as { message: string }).message;
          }

          setLaunchError(message);
        },
      },
    );
  }, [checksMode, createdDealId, forceReclassify, navigate, startRun]);

  // ── Derived block statuses ────────────────────────────────
  const isBlock1Done = createdDealId !== null && block1bDone;
  const hasDocuments = documentsCount > 0;
  const hasPlaybook = !!deal?.playbook_version_id;
  const hasLanguage = !!deal?.primary_language;

  const block1Status: FlowBlockStatus = isBlock1Done
    ? "done"
    : "active";

  const block2Status: FlowBlockStatus =
    createdDealId === null
      ? "disabled"
      : hasDocuments && isBlock1Done
        ? "done"
        : createdDealId !== null
          ? "active"
          : "disabled";

  const block3Status: FlowBlockStatus = !hasDocuments
    ? "disabled"
    : hasPlaybook
      ? "done"
      : "active";

  const block4Status: FlowBlockStatus = !hasPlaybook
    ? "disabled"
    : block4Done
      ? "done"
      : "active";

  const block5Status: FlowBlockStatus = !hasPlaybook
    ? "disabled"
    : hasLanguage
      ? "done"
      : "active";

  const block6Status: FlowBlockStatus = !hasLanguage
    ? "disabled"
    : "active";

  // ── Can launch ────────────────────────────────────────────
  const canLaunch =
    !!createdDealId &&
    hasDocuments &&
    hasPlaybook &&
    hasLanguage &&
    !startRun.isPending;

  // ── Progress counter ──────────────────────────────────────
  const doneCount = [
    block1Status === "done",
    block2Status === "done",
    block3Status === "done",
    block4Status === "done",
    block5Status === "done",
  ].filter(Boolean).length;

  // ── Block 1 summary ──────────────────────────────────────
  const block1Summary = React.useMemo(() => {
    const parts: string[] = [];

    if (projectName.trim()) {
      parts.push(projectName.trim());
    }

    if (responsibleUserName) {
      parts.push(`Ответственный: ${responsibleUserName}`);
    }

    return parts.join(" · ") || undefined;
  }, [projectName, responsibleUserName]);

  // ── Block 2 summary ──────────────────────────────────────
  const block2Summary = hasDocuments
    ? `${documentsCount} документ${documentsCount === 1 ? "" : documentsCount < 5 ? "а" : "ов"}`
    : undefined;

  // ── Cancel ────────────────────────────────────────────────
  const handleCancel = React.useCallback(() => {
    navigate("/dashboard");
  }, [navigate]);

  // ── Refetch documents callback ────────────────────────────
  const handleRefetchDocuments = React.useCallback(() => {
    void refetchDocuments();
  }, [refetchDocuments]);

  // ── Guard ─────────────────────────────────────────────────
  if (!canCreate) {
    return null;
  }

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">
        {/* ── Header ───────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Запуск нового проекта
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Последовательно настройте проект и запустите анализ. Все
                параметры можно будет изменить позже.
              </p>
            </div>

            <div className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-1.5">
              <span className="text-[11px] font-semibold text-[var(--text-muted)]">
                {doneCount} из {TOTAL_STEPS}
              </span>
            </div>
          </div>
        </header>

        {/* ── Block 1: Project Info + Responsible ──────────── */}
        <FlowBlock
          step={1}
          title="Информация о проекте"
          status={block1Status}
          summary={block1Summary}
        >
          <div className="space-y-5">
            <Block1ProjectInfo
              projectName={projectName}
              onProjectNameChange={setProjectName}
              onCreateProject={handleCreateProject}
              onCancel={!createdDealId ? handleCancel : undefined}
              isSubmitting={isCreating}
              isCreated={createdDealId !== null}
              errorText={createError}
            />

            {createdDealId && !block1bDone ? (
              <div className="border-t border-[var(--border-subtle)] pt-5">
                <Block1bResponsibleUser
                  dealId={createdDealId}
                  onCompleted={handleResponsibleCompleted}
                />
              </div>
            ) : null}
          </div>
        </FlowBlock>

        {/* ── Block 2: Upload Documents ────────────────────── */}
        <FlowBlock
          step={2}
          title="Загрузка документов"
          status={block2Status}
          summary={block2Summary}
        >
          {createdDealId ? (
            <Block2Upload
              dealId={createdDealId}
              confirmedDocumentsCount={documentsCount}
              isDocumentsLoading={isDocumentsLoading}
              onRefetchDocuments={handleRefetchDocuments}
            />
          ) : null}
        </FlowBlock>

        {/* ── Block 3: Playbook ────────────────────────────── */}
        <FlowBlock
          step={3}
          title="Выбор playbook"
          status={block3Status}
          summary={
            playbookSummary
              ? `Playbook: ${playbookSummary}`
              : undefined
          }
        >
          {createdDealId ? (
            <Block3Playbook
              dealId={createdDealId}
              currentVersionId={
                deal?.playbook_version_id
                  ? String(deal.playbook_version_id)
                  : null
              }
              onApplied={handlePlaybookApplied}
            />
          ) : null}
        </FlowBlock>

        {/* ── Block 4: Model Config ────────────────────────── */}
        <FlowBlock
          step={4}
          title="Профиль модели"
          status={block4Status}
          summary={
            modelConfigSummary
              ? `Профиль: ${modelConfigSummary}`
              : undefined
          }
        >
          {createdDealId ? (
            <Block4ModelConfig
              dealId={createdDealId}
              currentConfigId={
                deal?.model_config_id
                  ? String(deal.model_config_id)
                  : null
              }
              currentConfigName={deal?.model_config_name ?? null}
              onApplied={handleModelConfigApplied}
              onSkipped={handleModelConfigSkipped}
            />
          ) : null}
        </FlowBlock>

        {/* ── Block 5: Language ─────────────────────────────── */}
        <FlowBlock
          step={5}
          title="Основной язык анализа"
          status={block5Status}
          summary={
            languageSummary
              ? `Язык: ${languageSummary}`
              : undefined
          }
        >
          {createdDealId && deal ? (
            <Block5Language
              dealId={createdDealId}
              languages={deal.languages ?? []}
              primaryLanguage={deal.primary_language ?? null}
              discoveryStatus={deal.language_discovery_status ?? null}
              onLanguageSet={handleLanguageSet}
            />
          ) : null}
        </FlowBlock>

        {/* ── Block 6: Launch ──────────────────────────────── */}
        <FlowBlock
          step={6}
          title="Запуск анализа"
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
            canLaunch={canLaunch}
            isSubmitting={startRun.isPending}
            errorText={launchError}
            onLaunch={handleLaunch}
          />
        </FlowBlock>
      </div>
    </div>
  );
};

export default NewProjectLaunchFlowPage;



