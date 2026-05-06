// =============================================================
// HeaderSection.tsx
// Шапка документа + действия (открыть/скачать/DD Grid).
// =============================================================

import React from "react";
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
  return (
    <div className="space-y-3">
      <div
        className="flex flex-wrap items-center gap-2"
        aria-label="Действия по выбранному документу"
      >
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={onOpenOriginalFile}
          disabled={!pdfUrl || !canOpenPdf}
          leftIcon={<FileText size={14} />}
          title={!pdfUrl ? "Исходный файл пока недоступен" : undefined}
        >
          Открыть файл
        </Button>

        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={onDownloadOriginalFile}
          disabled={!pdfUrl || !canDownload || isDownloadingOriginal}
          leftIcon={<Download size={14} />}
          isLoading={isDownloadingOriginal}
          title={!pdfUrl ? "Скачивание оригинала сейчас недоступно" : undefined}
        >
          Скачать файл
        </Button>

        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={onOpenInGrid}
          disabled={!onOpenInGrid}
          rightIcon={<ExternalLink size={12} />}
        >
          Открыть в DD Grid
        </Button>
      </div>
    </div>
  );
};


