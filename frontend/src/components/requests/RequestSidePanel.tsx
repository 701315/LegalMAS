// =============================================================
// src/components/requests/RequestSidePanel.tsx
// Side panel деталей DD-запроса для юриста (legacy CRUD mode).
// Поддерживает редактирование, удаление, управление статусом.
// Использует shared presentation components и adapter.
// НЕ показывает segment context (legacy DDRequest не имеет этих полей).
// =============================================================

import React, { useEffect, useState, useMemo } from "react";
import type { DDRequest } from "../../types";
import { toRequestPanelViewFromLegacy } from "../../viewAdapters/requestPresentation";
import { X, Clipboard, Check, Trash2, Pencil, Loader2 } from "lucide-react";

import { RequestDocumentsList } from "./shared/RequestDocumentsList";
import { RequestStructuredValuesList } from "./shared/RequestStructuredValuesList";
import Button from "../ui/Button";

interface Props {
  request: DDRequest | null;
  onClose: () => void;
  onSave: (reqId: string, data: Partial<DDRequest>) => Promise<void>;
  onDelete: (reqId: string) => Promise<void>;
  isSaving: boolean;
  canManageRequests: boolean;
  documentNameById?: Record<string, string>;
}

export const RequestSidePanel: React.FC<Props> = ({
  request,
  onClose,
  onSave,
  onDelete,
  isSaving,
  canManageRequests,
  documentNameById,
}) => {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [priority, setPriority] = useState<DDRequest["priority"]>("medium");
  const [status, setStatus] = useState<DDRequest["status"]>("open");
  const [copied, setCopied] = useState(false);

  const viewModel = useMemo(() => {
    if (!request) return null;
    return toRequestPanelViewFromLegacy(request, canManageRequests);
  }, [request, canManageRequests]);

  useEffect(() => {
    if (!request) return;
    setText(request.text);
    setPriority(request.priority);
    setStatus(request.status);
    setEditing(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.id]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!viewModel || !request) return null;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSave = async () => {
    if (!canManageRequests) return;
    await onSave(request.id, { text, priority, status });
    setEditing(false);
  };

  const handleDelete = async () => {
    if (!canManageRequests) return;
    if (!confirm("Удалить запрос? Это действие нельзя отменить.")) return;
    await onDelete(request.id);
    onClose();
  };

  const PRIORITY_OPTIONS: { value: DDRequest["priority"]; label: string }[] = [
    { value: "critical", label: "Критичный" },
    { value: "high", label: "Высокий" },
    { value: "medium", label: "Средний" },
  ];

  const STATUS_OPTIONS: { value: DDRequest["status"]; label: string }[] = [
    { value: "open", label: "Открыт" },
    { value: "in_progress", label: "В работе" },
    { value: "resolved", label: "Закрыт" },
  ];

  const documentsWithNames = viewModel.documents.map((doc) => ({
    ...doc,
    name: documentNameById?.[doc.id!] ?? doc.name,
  }));

  const canEdit = editing && canManageRequests;

  return (
    <>
      {/* Затемнение */}
      <div
        className="fixed inset-0 z-40 bg-[oklch(0.2_0.03_260/0.5)] backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Панель */}
      <div className="fixed right-0 top-0 z-50 flex h-full w-[440px] flex-col border-l border-[var(--border)] bg-[var(--bg-panel)] shadow-[0_0_40px_rgba(15,23,42,0.7)] animate-in slide-in-from-right">
        {/* Шапка */}
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
          <div>
            <h3 className="text-sm font-semibold tracking-tight text-[var(--text-primary)]">
              {viewModel.title}
            </h3>
            {viewModel.checkId && (
              <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                Проверка: {viewModel.checkId}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)]"
            aria-label="Закрыть"
          >
            <X size={18} />
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {/* Приоритет */}
          <Field label="Приоритет">
            <select
              value={priority}
              onChange={(e) =>
                setPriority(e.target.value as DDRequest["priority"])
              }
              disabled={!canEdit}
              className="input-base"
            >
              {PRIORITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </Field>

          {/* Статус */}
          <Field label="Статус">
            <select
              value={status}
              onChange={(e) =>
                setStatus(e.target.value as DDRequest["status"])
              }
              disabled={!canEdit}
              className="input-base"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </Field>

          {/* Адресат */}
          {viewModel.addressee && (
            <Field label="Адресат">
              <p className="text-sm font-medium text-[var(--text-secondary)]">
                {viewModel.addressee}
              </p>
            </Field>
          )}

          {/* Источник */}
          {viewModel.source && (
            <Field label="Источник">
              <span
                className={[
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                  viewModel.source.colorClass,
                ].join(" ")}
              >
                <span>{viewModel.source.label}</span>
              </span>
              {viewModel.source.helperText && (
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {viewModel.source.helperText}
                </p>
              )}
            </Field>
          )}

          {/* Текст запроса */}
          <Field label="Текст запроса">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={8}
              disabled={!canEdit}
              className="input-base resize-y"
            />
          </Field>

          {/* Документы */}
          {documentsWithNames.length > 0 && (
            <Field label={`Документы (${documentsWithNames.length})`}>
              <RequestDocumentsList
                documents={documentsWithNames}
                maxVisible={10}
              />
            </Field>
          )}

          {/* Связь с проверкой (YAML) */}
          {viewModel.checkId && viewModel.source?.code === "yaml_template" && (
            <Field label="Связь с проверкой">
              <p className="text-xs text-[var(--text-muted)]">
                Связано с YAML‑проверкой (check_id: {viewModel.checkId}).
              </p>
            </Field>
          )}

          {/* Источники (evidence_refs) */}
          {viewModel.evidenceRefs.length > 0 && (
            <Field label={`Источники (${viewModel.evidenceRefs.length})`}>
              <div className="max-h-32 space-y-1 overflow-y-auto rounded-xl bg-[var(--bg-elevated-soft)] p-2">
                {viewModel.evidenceRefs.map((ref, i) => (
                  <div
                    key={ref ?? i}
                    className="rounded-lg bg-[var(--bg-card)]/80 p-2 text-xs leading-relaxed text-[var(--text-secondary)]"
                  >
                    {ref}
                  </div>
                ))}
              </div>
            </Field>
          )}

          {/* Извлечённые данные */}
          {viewModel.structuredValues.length > 0 && (
            <Field
              label={`Извлечённые данные (${viewModel.structuredValues.length})`}
            >
              <RequestStructuredValuesList
                values={viewModel.structuredValues}
                maxHeight="10rem"
              />
            </Field>
          )}
        </div>

        {/* Подвал */}
        <div className="flex flex-col gap-2 border-t border-[var(--border)] px-4 py-3">
          {/* Копирование */}
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={handleCopy}
            className="inline-flex w-full items-center justify-center gap-1.5"
          >
            {copied ? (
              <>
                <Check size={14} className="text-[var(--success)]" />
                <span>Скопировано!</span>
              </>
            ) : (
              <>
                <Clipboard size={14} />
                <span>Копировать текст</span>
              </>
            )}
          </Button>

          {/* Редактирование / сохранение */}
          {editing ? (
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="inline-flex flex-1 items-center justify-center gap-1.5"
                onClick={handleSave}
                disabled={isSaving || !canManageRequests}
              >
                {isSaving ? (
                  <Loader2 className="animate-spin" size={14} />
                ) : (
                  <Check size={14} />
                )}
                Сохранить
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setText(request.text);
                  setPriority(request.priority);
                  setStatus(request.status);
                  setEditing(false);
                }}
              >
                Отмена
              </Button>
            </div>
          ) : (
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="inline-flex flex-1 items-center justify-center gap-1.5"
                onClick={() => canManageRequests && setEditing(true)}
                disabled={!canManageRequests}
              >
                <Pencil size={14} />
                Редактировать
              </Button>
              <Button
                type="button"
                size="sm"
                variant="danger"
                onClick={handleDelete}
                disabled={!canManageRequests}
                className="inline-flex items-center justify-center gap-1.5"
              >
                <Trash2 size={14} />
              </Button>
            </div>
          )}
        </div>
      </div>
    </>
  );
};

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
        {label}
      </label>
      {children}
    </div>
  );
}

export default RequestSidePanel;



