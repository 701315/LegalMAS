import React, { useEffect, useState, useMemo } from "react";
import type { DDRequest } from "../../types";
import { toRequestPanelViewFromLegacy } from "../../viewAdapters/requestPresentation";
import { Clipboard, Check, Trash2, Pencil, Loader2 } from "lucide-react";

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
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fail-silent
    }
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

  const documentsWithNames = viewModel.documents.map((doc) => ({
    ...doc,
    name: documentNameById?.[doc.id!] ?? doc.name,
  }));

  const canEdit = editing && canManageRequests;

  return (
    <aside
      className="flex min-h-0 flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] shadow-[inset_3px_0_0_var(--accent-primary)]"
      aria-labelledby="request-panel-title"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
            DD‑запрос
          </p>
          <h2
            id="request-panel-title"
            className="mt-1 text-sm font-semibold text-[var(--text-primary)]"
          >
            {viewModel.title}
          </h2>
          {viewModel.checkId && (
            <p className="mt-1 text-[12px] text-[var(--text-muted)]">
              Проверка: {viewModel.checkId}
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть панель запроса"
          className="rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-card)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]"
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-3">
        {/* Priority */}
        <Field label="Приоритет">
          <select
            value={priority}
            onChange={(e) =>
              setPriority(e.target.value as DDRequest["priority"])
            }
            disabled={!canEdit}
            className="mt-1 w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {PRIORITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </Field>

        {/* Status */}
        <Field label="Статус">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as DDRequest["status"])}
            disabled={!canEdit}
            className="mt-1 w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-sm text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </Field>

        {/* Addressee */}
        {viewModel.addressee && (
          <Field label="Адресат">
            <p className="mt-1 text-sm font-medium text-[var(--text-secondary)]">
              {viewModel.addressee}
            </p>
          </Field>
        )}

        {/* Source */}
        {viewModel.source && (
          <Field label="Источник">
            <span
              className={[
                "mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
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

        {/* Request text */}
        <Field label="Текст запроса">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={8}
            disabled={!canEdit}
            className="mt-1 w-full resize-y rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-sm leading-6 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)] disabled:cursor-not-allowed disabled:opacity-60"
          />
        </Field>

        {/* Documents */}
        {documentsWithNames.length > 0 && (
          <Field label={`Документы (${documentsWithNames.length})`}>
            <RequestDocumentsList
              documents={documentsWithNames}
              maxVisible={10}
            />
          </Field>
        )}

        {/* YAML link */}
        {viewModel.checkId && viewModel.source?.code === "yaml_template" && (
          <Field label="Связь с проверкой">
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              Связано с YAML‑проверкой (check_id: {viewModel.checkId}).
            </p>
          </Field>
        )}

        {/* Evidence refs */}
        {viewModel.evidenceRefs.length > 0 && (
          <Field label={`Источники (${viewModel.evidenceRefs.length})`}>
            <div className="mt-1 max-h-32 space-y-1 overflow-y-auto rounded-xl bg-[var(--bg-elevated-soft)] p-2">
              {viewModel.evidenceRefs.map((ref, i) => (
                <div
                  key={ref ?? i}
                  className="rounded-lg bg-[var(--bg-card)] p-2 text-xs leading-relaxed text-[var(--text-secondary)]"
                >
                  {ref}
                </div>
              ))}
            </div>
          </Field>
        )}

        {/* Structured values */}
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

      {/* Footer */}
      <div className="flex flex-col gap-2 border-t border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
        {/* Copy */}
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={handleCopy}
          className="inline-flex w-full items-center justify-center gap-1.5"
        >
          {copied ? (
            <>
              <Check className="h-4 w-4" />
              <span>Скопировано</span>
            </>
          ) : (
            <>
              <Clipboard className="h-4 w-4" />
              <span>Копировать текст</span>
            </>
          )}
        </Button>

        {/* Edit / Save */}
        {editing ? (
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant="primary"
              className="inline-flex flex-1 items-center justify-center gap-1.5"
              onClick={handleSave}
              disabled={isSaving || !canManageRequests}
            >
              {isSaving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              <span>Сохранить</span>
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
              <Pencil className="h-4 w-4" />
              <span>Редактировать</span>
            </Button>
            <Button
              type="button"
              size="sm"
              variant="danger"
              onClick={handleDelete}
              disabled={!canManageRequests}
              className="inline-flex items-center justify-center gap-1.5"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </aside>
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
      <label className="block text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
        {label}
      </label>
      {children}
    </div>
  );
}

export default RequestSidePanel;


