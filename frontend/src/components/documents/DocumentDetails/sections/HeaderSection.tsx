// =============================================================
// HeaderSection.tsx
// Шапка документа + действия (открыть/скачать/DD Grid).
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { Download, ExternalLink, FileText } from "lucide-react";
import Button from "../../../ui/Button";

interface HeaderSectionProps {
  pdfUrl: string | null;
  canOpenPdf: boolean;
  canDownload: boolean;
  isDownloadingOriginal: boolean;
  onOpenOriginalFile: () => void;
  onDownloadOriginalFile: () => void;
  onOpenInGrid?: () => void;
}

export const HeaderSection: React.FC<HeaderSectionProps> = ({
  pdfUrl,
  canOpenPdf,
  canDownload,
  isDownloadingOriginal,
  onOpenOriginalFile,
  onDownloadOriginalFile,
  onOpenInGrid,
}) => {
  const { t } = useTranslation("documents");

  return (
    <div className="space-y-3">
      <div
        className="flex flex-wrap items-center gap-2"
        aria-label={t("headerSection.actionsAriaLabel")}
      >
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={onOpenOriginalFile}
          disabled={!pdfUrl || !canOpenPdf}
          leftIcon={<FileText size={14} />}
          title={!pdfUrl ? t("headerSection.originalUnavailable") : undefined}
        >
          {t("headerSection.openFile")}
        </Button>

        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={onDownloadOriginalFile}
          disabled={!pdfUrl || !canDownload || isDownloadingOriginal}
          leftIcon={<Download size={14} />}
          isLoading={isDownloadingOriginal}
          title={
            !pdfUrl ? t("headerSection.downloadUnavailable") : undefined
          }
        >
          {t("headerSection.downloadFile")}
        </Button>

        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={onOpenInGrid}
          disabled={!onOpenInGrid}
          rightIcon={<ExternalLink size={12} />}
        >
          {t("headerSection.openInGrid")}
        </Button>
      </div>
    </div>
  );
};


