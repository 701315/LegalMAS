// =============================================================
// src/components/new-project/Block2Upload.tsx
//
// Блок 2 — Загрузка документов в проект.
//
// Переиспользует ProjectUploadPanel в mode="embedded".
// Добавляет post-upload sync логику:
//   после успешного upload ждёт, пока backend начнёт
//   возвращать документы в списке, чтобы не требовать
//   ручного reload страницы.
//
// Блок считается завершённым когда confirmedDocumentsCount > 0.
// =============================================================

import React from "react";
import { Loader2, FileCheck2, AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import ProjectUploadPanel from "../upload/ProjectUploadPanel";
import Button from "../ui/Button";

interface Block2UploadProps {
  dealId: string;
  /**
   * Текущее количество документов из useDocuments,
   * которое polling обновляет на уровне родительской страницы.
   */
  confirmedDocumentsCount: number;
  /**
   * Флаг: идёт ли загрузка списка документов.
   * Нужен для статуса post-upload sync.
   */
  isDocumentsLoading: boolean;
  /** Принудительно перезапросить список документов */
  onRefetchDocuments: () => void;
}

const POST_UPLOAD_TIMEOUT_MS = 30_000;
const POST_UPLOAD_POLL_MS = 1_500;

const Block2Upload: React.FC<Block2UploadProps> = ({
  dealId,
  confirmedDocumentsCount,
  isDocumentsLoading,
  onRefetchDocuments,
}) => {
  const { t } = useTranslation("projects");
  const [isWaitingForDocs, setIsWaitingForDocs] = React.useState(false);
  const [waitingTimedOut, setWaitingTimedOut] = React.useState(false);

  const waitingTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const pollingTimerRef = React.useRef<ReturnType<typeof setInterval> | null>(
    null,
  );

  const clearTimers = React.useCallback(() => {
    if (waitingTimerRef.current) {
      clearTimeout(waitingTimerRef.current);
      waitingTimerRef.current = null;
    }

    if (pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
  }, []);

  React.useEffect(() => {
    return clearTimers;
  }, [clearTimers]);

  React.useEffect(() => {
    if (isWaitingForDocs && confirmedDocumentsCount > 0) {
      setIsWaitingForDocs(false);
      setWaitingTimedOut(false);
      clearTimers();
    }
  }, [isWaitingForDocs, confirmedDocumentsCount, clearTimers]);

  const handleUploadFinished = React.useCallback(() => {
    if (confirmedDocumentsCount > 0) {
      return;
    }

    setIsWaitingForDocs(true);
    setWaitingTimedOut(false);
    clearTimers();

    pollingTimerRef.current = setInterval(() => {
      onRefetchDocuments();
    }, POST_UPLOAD_POLL_MS);

    waitingTimerRef.current = setTimeout(() => {
      setWaitingTimedOut(true);

      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    }, POST_UPLOAD_TIMEOUT_MS);
  }, [clearTimers, confirmedDocumentsCount, onRefetchDocuments]);

  const handleManualRetry = React.useCallback(() => {
    setWaitingTimedOut(false);
    setIsWaitingForDocs(true);
    clearTimers();

    onRefetchDocuments();

    pollingTimerRef.current = setInterval(() => {
      onRefetchDocuments();
    }, POST_UPLOAD_POLL_MS);

    waitingTimerRef.current = setTimeout(() => {
      setWaitingTimedOut(true);

      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    }, POST_UPLOAD_TIMEOUT_MS);
  }, [clearTimers, onRefetchDocuments]);

  const hasConfirmedDocs = confirmedDocumentsCount > 0;

  return (
    <div className="space-y-4">
      {isWaitingForDocs && !hasConfirmedDocs && (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
          {waitingTimedOut ? (
            <div className="flex items-start gap-3">
              <div
                className="mt-0.5 shrink-0 text-[var(--color-warning-text)]"
                aria-hidden="true"
              >
                <AlertTriangle className="h-4 w-4" />
              </div>

              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {t("newProject.block2.waitingTitle")}
                </p>
                <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                  {t("newProject.block2.waitingDesc")}
                </p>

                <div className="mt-3">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={handleManualRetry}
                    disabled={isDocumentsLoading}
                  >
                    {t("newProject.block2.checkAgainBtn")}
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <Loader2
                className="h-4 w-4 shrink-0 animate-spin text-[var(--accent-primary)]"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-sm text-[var(--text-primary)]">
                  {t("newProject.block2.loadingTitle")}
                </p>
                <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                  {isDocumentsLoading
                    ? t("newProject.block2.loadingDescProcessing")
                    : t("newProject.block2.loadingDescAuto")}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {hasConfirmedDocs && (
        <div className="subtle-panel px-4 py-3">
          <div className="flex items-start gap-3">
            <div
              className="mt-0.5 shrink-0 text-[var(--color-success-text)]"
              aria-hidden="true"
            >
              <FileCheck2 className="h-4 w-4" />
            </div>

            <div className="min-w-0">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {t("newProject.block2.documentsUploadedCount", {
                  count: confirmedDocumentsCount,
                })}
              </p>
              <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                {t("newProject.block2.successDesc")}
              </p>
            </div>
          </div>
        </div>
      )}

      <ProjectUploadPanel
        dealId={dealId}
        mode="embedded"
        showWorkflow={false}
        onFinished={handleUploadFinished}
      />
    </div>
  );
};

export default Block2Upload;

