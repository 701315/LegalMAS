// =============================================================
// src/components/documents/pipeline/PipelineStageModal.tsx
// =============================================================

import React from "react";
import { useTranslation, Trans } from "react-i18next";
import { X, Sparkles, Braces, Loader2 } from "lucide-react";
import type {
  PipelineStageKind,
  PipelineStageViewDTO,
  StageViewMode,
  OpenViewerAtFn,
} from "../../../types";
import { getDocumentPipelineView } from "../../../api/documentPipelineView";
import { PdfStageViewer } from "./PdfStageViewer";
import { LayoutStageViewer } from "./LayoutStageViewer";
import { StructureStageViewer } from "./StructureStageViewer";
import { ChunksStageViewer } from "./ChunksStageViewer";
import { StageRepresentationBanner } from "./StageRepresentationBanner";
import Button from "../../ui/Button";

interface Props {
  stage: PipelineStageViewDTO | null;
  stages: PipelineStageViewDTO[];
  documentId: string;
  onOpenAtLocation?: OpenViewerAtFn;
  onClose: () => void;
}

const FRIENDLY_SUPPORTED_KINDS: PipelineStageKind[] = ["structure", "chunks"];
const FRIENDLY_DEFAULT_KINDS: PipelineStageKind[] = ["chunks"];

function supportsFriendlyMode(stage: PipelineStageViewDTO): boolean {
  return FRIENDLY_SUPPORTED_KINDS.includes(stage.kind);
}

function getDefaultViewMode(stage: PipelineStageViewDTO): StageViewMode {
  const backendMode = stage.representation?.view_mode;
  if (backendMode === "friendly" || backendMode === "canonical") {
    return backendMode;
  }
  if (FRIENDLY_DEFAULT_KINDS.includes(stage.kind)) {
    return "friendly";
  }
  return "canonical";
}

function getErrorMessage(err: unknown, tFn: (key: string) => string): string {
  if (typeof err === "object" && err !== null) {
    const maybeDetail = (err as { detail?: unknown }).detail;
    if (typeof maybeDetail === "string" && maybeDetail.trim()) {
      return maybeDetail;
    }

    const maybeMessage = (err as { message?: unknown }).message;
    if (typeof maybeMessage === "string" && maybeMessage.trim()) {
      return maybeMessage;
    }
  }

  return tFn("stageModal.switchError");
}

function getToggleLabels(kind: PipelineStageKind, tFn: (key: string) => string): {
  toFriendly: string;
  toCanonical: string;
  toFriendlyTitle: string;
  toCanonicalTitle: string;
} {
  if (kind === "chunks") {
    return {
      toFriendly: tFn("stageModal.toggle.chunksFriendly"),
      toCanonical: tFn("stageModal.toggle.chunksCanonical"),
      toFriendlyTitle: tFn("stageModal.toggle.chunksFriendlyTitle"),
      toCanonicalTitle: tFn("stageModal.toggle.chunksCanonicalTitle"),
    };
  }

  return {
    toFriendly: tFn("stageModal.toggle.genericFriendly"),
    toCanonical: tFn("stageModal.toggle.genericCanonical"),
    toFriendlyTitle: tFn("stageModal.toggle.genericFriendlyTitle"),
    toCanonicalTitle: tFn("stageModal.toggle.genericCanonicalTitle"),
  };
}

export const PipelineStageModal: React.FC<Props> = ({
  stage,
  stages,
  documentId,
  onOpenAtLocation,
  onClose,
}) => {
  const { t } = useTranslation("pipeline");
  const [currentStage, setCurrentStage] =
    React.useState<PipelineStageViewDTO | null>(stage);
  const [currentStages, setCurrentStages] =
    React.useState<PipelineStageViewDTO[]>(stages);
  const [viewMode, setViewMode] = React.useState<StageViewMode>("canonical");
  const [loading, setLoading] = React.useState<boolean>(false);
  const [error, setError] = React.useState<string | null>(null);

  const titleId = React.useId();
  const descriptionId = React.useId();

  React.useEffect(() => {
    setCurrentStage(stage ?? null);
    setCurrentStages(stages);
    setError(null);
    setViewMode(stage ? getDefaultViewMode(stage) : "canonical");
  }, [stage, stages]);

  React.useEffect(() => {
    if (!currentStage) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !loading) {
        event.preventDefault();
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentStage, loading, onClose]);

  const handleBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (loading) return;
    if (event.target === event.currentTarget) {
      onClose();
    }
  };

  if (!currentStage) {
    return null;
  }

  const stageData: PipelineStageViewDTO = currentStage;
  const canToggleFriendly =
    supportsFriendlyMode(stageData) && stageData.status === "ready";

  const toggleLabels = getToggleLabels(stageData.kind, t);

  async function handleToggleViewMode() {
    if (!documentId || !canToggleFriendly || loading) return;

    const nextViewMode: StageViewMode =
      viewMode === "canonical" ? "friendly" : "canonical";

    try {
      setLoading(true);
      setError(null);

      const result = await getDocumentPipelineView(
        documentId,
        undefined,
        nextViewMode,
      );

      const updatedStage =
        result.stages.find((item) => item.code === stageData.code) ?? null;

      if (!updatedStage) {
        throw new Error(
          `Stage ${stageData.code} not found in pipeline response`,
        );
      }

      setCurrentStages(result.stages);
      setCurrentStage(updatedStage);
      setViewMode(nextViewMode);
    } catch (err) {
      setError(getErrorMessage(err, t));
    } finally {
      setLoading(false);
    }
  }

  function renderContent() {
    switch (stageData.kind) {
      case "pdf":
        return <PdfStageViewer stage={stageData} />;

      case "layout":
        return <LayoutStageViewer stage={stageData} />;

      case "structure": {
        const chunksStage =
          currentStages.find((item) => item.code === "CHUNKS") ?? null;

        return (
          <StructureStageViewer
            documentId={documentId}
            structureStage={stageData}
            chunksStage={chunksStage}
            onOpenAtLocation={onOpenAtLocation}
          />
        );
      }

      case "chunks":
        return (
          <ChunksStageViewer
            stage={stageData}
            documentId={documentId}
            onOpenAtLocation={onOpenAtLocation}
          />
        );

      default:
        return (
          <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4 text-sm text-[var(--text-muted)] shadow-sm">
            {t("stageModal.noViewer")}
          </div>
        );
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]"
      onClick={handleBackdropClick}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="flex h-[92vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
              {stageData.code}
            </p>
            <h2
              id={titleId}
              className="mt-1 text-base font-semibold text-[var(--text-primary)]"
            >
              {stageData.title}
            </h2>
            <p
              id={descriptionId}
              className="mt-1 max-w-3xl text-sm text-[var(--text-muted)]"
            >
              {stageData.description}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {canToggleFriendly && (
              <Button
                type="button"
                size="sm"
                variant={viewMode === "canonical" ? "secondary" : "ghost"}
                onClick={handleToggleViewMode}
                disabled={loading}
                title={
                  viewMode === "canonical"
                    ? toggleLabels.toFriendlyTitle
                    : toggleLabels.toCanonicalTitle
                }
                className="gap-1.5"
              >
                {loading ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    {t("stageModal.switching")}
                  </>
                ) : viewMode === "canonical" ? (
                  <>
                    <Sparkles size={14} />
                    {toggleLabels.toFriendly}
                  </>
                ) : (
                  <>
                    <Braces size={14} />
                    {toggleLabels.toCanonical}
                  </>
                )}
              </Button>
            )}

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onClose}
              disabled={loading}
              aria-label={t("stageModal.closeAria")}
              className="px-2 py-1.5"
            >
              <X size={16} />
            </Button>
          </div>
        </div>

        <StageRepresentationBanner
          representation={stageData.representation}
          meta={stageData.meta ?? null}
        />

        {error && (
          <div className="mx-5 mt-4 rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-4 py-3 text-sm text-[var(--color-error-text)]">
            {error}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-hidden bg-[var(--bg-subtle)] p-5">
          {renderContent()}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] bg-[var(--bg-card)] px-5 py-3">
          <p className="text-xs text-[var(--text-muted)]">
            <Trans
              t={t}
              i18nKey="stageModal.representationMode"
              values={{ mode: viewMode === "friendly" ? "friendly" : "canonical" }}
              components={{
                bold: <span className="font-medium text-[var(--text-primary)]" />,
              }}
            />
          </p>

          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onClose}
            disabled={loading}
          >
            {t("actions.close", { ns: "common" })}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default PipelineStageModal;



