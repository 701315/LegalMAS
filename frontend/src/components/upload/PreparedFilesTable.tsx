// src/components/upload/PreparedFilesTable.tsx

import React from "react";
import { FileSpreadsheet, FileText } from "lucide-react";
import Button from "../ui/Button";

export interface PreparedFileRow {
  id: string;
  name: string;
  extension: string;
  sizeLabel: string;
  pathLabel: string;
}

interface PreparedFilesTableProps {
  rows: PreparedFileRow[];
  selectedRowIds: string[];
  isUploading: boolean;
  canUpload: boolean;
  onUpload: () => void;
  onToggleRow: (rowId: string) => void;
  onToggleAll: () => void;
  onRemoveSelected: () => void;
  onRemoveSingle: (rowId: string) => void;
}

function getFileIcon(extension: string) {
  const ext = extension.toLowerCase();

  if (["xls", "xlsx", "csv", "tsv"].includes(ext)) {
    return <FileSpreadsheet className="h-4 w-4" />;
  }

  return <FileText className="h-4 w-4" />;
}

const PreparedFilesTable: React.FC<PreparedFilesTableProps> = ({
  rows,
  selectedRowIds,
  isUploading,
  canUpload,
  onUpload,
  onToggleRow,
  onToggleAll,
  onRemoveSelected,
  onRemoveSingle,
}) => {
  const hasRows = rows.length > 0;
  const hasSelection = selectedRowIds.length > 0;
  const allSelected = hasRows && selectedRowIds.length === rows.length;

  return (
    <section className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Подготовленные к загрузке файлы
          </h2>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            Проверьте состав набора перед отправкой в проект.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="primary"
            onClick={onUpload}
            disabled={!canUpload}
            isLoading={isUploading}
          >
            Загрузить
          </Button>

          <Button
            type="button"
            size="sm"
            variant={hasSelection ? "secondary" : "ghost"}
            onClick={onRemoveSelected}
            disabled={!hasSelection}
          >
            Очистить
          </Button>
        </div>
      </div>

      {!hasRows ? (
        <div className="px-5 py-8 text-sm text-[var(--text-muted)]">
          Нет файлов, подготовленных к загрузке.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--bg-base)]">
                <th className="w-12 px-4 py-3 text-left">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={onToggleAll}
                    aria-label="Выбрать все файлы"
                    className="h-4 w-4 rounded border-[var(--border)]"
                  />
                </th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  Файл
                </th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  Тип
                </th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  Размер
                </th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  Путь
                </th>
                <th className="w-24 px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  Действие
                </th>
              </tr>
            </thead>

            <tbody>
              {rows.map((row) => {
                const checked = selectedRowIds.includes(row.id);

                return (
                  <tr
                    key={row.id}
                    className="border-b border-[var(--border-soft)] last:border-b-0"
                  >
                    <td className="px-4 py-3 align-middle">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onToggleRow(row.id)}
                        aria-label={`Выбрать файл ${row.name}`}
                        className="h-4 w-4 rounded border-[var(--border)]"
                      />
                    </td>

                    <td className="px-4 py-3 align-middle">
                      <div className="flex items-center gap-2">
                        <div className="text-[var(--text-muted)]">
                          {getFileIcon(row.extension)}
                        </div>
                        <span className="text-sm text-[var(--text-primary)]">
                          {row.name}
                        </span>
                      </div>
                    </td>

                    <td className="px-4 py-3 align-middle text-xs text-[var(--text-secondary)]">
                      {row.extension}
                    </td>

                    <td className="px-4 py-3 align-middle text-xs text-[var(--text-secondary)]">
                      {row.sizeLabel}
                    </td>

                    <td className="px-4 py-3 align-middle text-xs text-[var(--text-secondary)]">
                      {row.pathLabel}
                    </td>

                    <td className="px-4 py-3 align-middle text-right">
                      <Button
                        type="button"
                        size="sm"
                        variant={checked ? "ghost" : "ghost"}
                        onClick={() => onRemoveSingle(row.id)}
                        disabled={!checked}
                      >
                        Удалить
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};

export default PreparedFilesTable;

