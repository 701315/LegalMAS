//src/components/upload/UploadDropzoneCard.tsx

import React from "react";
import { HardDriveUpload } from "lucide-react";
import Button from "../ui/Button";

interface UploadDropzoneCardProps {
  isDragActive: boolean;
  isSubmitting: boolean;
  selectedCount: number;
  onDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragEnter: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onPickFiles: () => void;
  onPickFolder: () => void;
}

const UploadDropzoneCard: React.FC<UploadDropzoneCardProps> = ({
  isDragActive,
  isSubmitting,
  selectedCount,
  onDragOver,
  onDragEnter,
  onDragLeave,
  onDrop,
  onPickFiles,
  onPickFolder,
}) => {
  return (
    <section className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <div className="flex h-full min-h-[220px] flex-col">
        <div
          onDragOver={onDragOver}
          onDragEnter={onDragEnter}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          className={[
            "flex flex-1 flex-col items-center justify-center rounded-[20px] border border-dashed px-5 py-6 text-center transition-colors",
            isDragActive
              ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
              : "border-[var(--border)] bg-[var(--bg-base)]",
          ].join(" ")}
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--accent-muted)] text-[var(--accent-primary)]">
            <HardDriveUpload className="h-5 w-5" />
          </div>

          <h2 className="mt-4 text-sm font-semibold text-[var(--text-primary)]">
            Перетащите документы сюда
          </h2>

          <p className="mt-2 max-w-md text-xs leading-5 text-[var(--text-secondary)]">
            Поддерживается загрузка отдельных файлов или содержимого папки.
            После подготовки набора можно перейти к загрузке в проект.
          </p>

          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="primary"
              onClick={onPickFiles}
              disabled={isSubmitting}
            >
              Выбрать файлы
            </Button>

            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={onPickFolder}
              disabled={isSubmitting}
            >
              Выбрать папку
            </Button>
          </div>
        </div>

        <div className="mt-3 text-xs text-[var(--text-muted)]">
          {selectedCount > 0
            ? `Подготовлено файлов: ${selectedCount}`
            : "Файлы ещё не выбраны"}
        </div>
      </div>
    </section>
  );
};

export default UploadDropzoneCard;

