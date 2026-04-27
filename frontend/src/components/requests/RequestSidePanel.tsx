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

// Shared components
import { RequestDocumentsList } from "./shared/RequestDocumentsList";
import { RequestStructuredValuesList } from "./shared/RequestStructuredValuesList";

interface Props {
  request: DDRequest | null;
  onClose: () => void;
  onSave: (reqId: string, data: Partial<DDRequest>) => Promise<void>;
  onDelete: (reqId: string) => Promise<void>;
  isSaving: boolean;
  canManageRequests: boolean;
  /**
   * Опциональный словарь docId → имя файла.
   * Если передан — document_refs рендерятся с именами вместо UUID.
   * Backward-compatible: при отсутствии отображается raw docId.
   */
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

  // Преобразуем DDRequest в UI read-model через adapter
  const viewModel = useMemo(() => {
    if (!request) return null;
    return toRequestPanelViewFromLegacy(request, canManageRequests);
  }, [request, canManageRequests]);

  // Синхронизация при выборе нового запроса
  useEffect(() => {
    if (!request) return;
    setText(request.text);
    setPriority(request.priority);
    setStatus(request.status);
    setEditing(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.id]);

  // Закрытие по Escape
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

  // Преобразуем document_refs с опциональными именами из documentNameById
  const documentsWithNames = viewModel.documents.map((doc) => ({
    ...doc,
    name: documentNameById?.[doc.id!] ?? doc.name,
  }));

  return (
    <>
      {/* Затемнение */}
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} />

      {/* Панель */}
      <div className="fixed right-0 top-0 h-full w-[420px] bg-white shadow-2xl z-50 border-l flex flex-col animate-in slide-in-from-right">
        {/* Шапка */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="text-lg font-semibold text-gray-900">
            {viewModel.title}
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-100 rounded transition"
            aria-label="Закрыть"
          >
            <X size={20} />
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Приоритет — редактируемый */}
          <Field label="Приоритет">
            <select
              value={priority}
              onChange={(e) =>
                setPriority(e.target.value as DDRequest["priority"])
              }
              disabled={!editing || !canManageRequests}
              className="w-full p-2 border rounded text-sm disabled:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {PRIORITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </Field>

          {/* Статус — редактируемый */}
          <Field label="Статус">
            <select
              value={status}
              onChange={(e) =>
                setStatus(e.target.value as DDRequest["status"])
              }
              disabled={!editing || !canManageRequests}
              className="w-full p-2 border rounded text-sm disabled:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
              <p className="text-sm text-gray-700 font-medium">
                {viewModel.addressee}
              </p>
            </Field>
          )}

          {/* Источник — используем view model */}
          {viewModel.source && (
            <Field label="Источник">
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${viewModel.source.colorClass}`}
              >
                <span>{viewModel.source.label}</span>
              </span>
              {viewModel.source.helperText && (
                <p className="text-xs text-purple-600 mt-1">
                  {viewModel.source.helperText}
                </p>
              )}
            </Field>
          )}

          {/* Текст запроса — редактируемый */}
          <Field label="Текст запроса">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={8}
              disabled={!editing || !canManageRequests}
              className="w-full p-2 border rounded text-sm resize-y disabled:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </Field>

          {/* Документы — shared component */}
          {documentsWithNames.length > 0 && (
            <Field label={`Документы (${documentsWithNames.length})`}>
              <RequestDocumentsList
                documents={documentsWithNames}
                maxVisible={10}
              />
            </Field>
          )}

          {/* Проверка */}
          {viewModel.checkId && (
            <Field label="Проверка">
              <p className="text-sm text-gray-700">{viewModel.checkId}</p>
              {viewModel.source?.code === "yaml_template" && (
                <p className="text-xs text-gray-400 mt-0.5">
                  Связано с YAML‑проверкой (check_id).
                </p>
              )}
            </Field>
          )}

          {/* Источники (evidence_refs) */}
          {viewModel.evidenceRefs.length > 0 && (
            <Field label={`Источники (${viewModel.evidenceRefs.length})`}>
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {viewModel.evidenceRefs.map((ref, i) => (
                  <div
                    key={ref ?? i}
                    className="text-xs text-gray-600 p-2 bg-gray-50 rounded leading-relaxed"
                  >
                    {ref}
                  </div>
                ))}
              </div>
            </Field>
          )}

          {/* Извлечённые данные — shared component */}
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
        <div className="border-t p-4 flex flex-col gap-2">
          {/* Копировать — доступно всем */}
          <button
            onClick={handleCopy}
            className="flex items-center justify-center gap-1.5 w-full px-4 py-2 border rounded text-sm hover:bg-gray-50 transition"
          >
            {copied ? (
              <>
                <Check size={14} className="text-green-600" />
                <span className="text-green-600">Скопировано!</span>
              </>
            ) : (
              <>
                <Clipboard size={14} />
                Копировать текст
              </>
            )}
          </button>

          {/* Редактирование / сохранение */}
          {editing ? (
            <div className="flex gap-2">
              <button
                onClick={handleSave}
                disabled={isSaving || !canManageRequests}
                className="flex-1 flex items-center justify-center gap-1 px-4 py-2 bg-green-600 text-white rounded text-sm font-medium hover:bg-green-700 transition disabled:opacity-50"
              >
                {isSaving ? (
                  <Loader2 className="animate-spin" size={14} />
                ) : (
                  <Check size={14} />
                )}
                Сохранить
              </button>
              <button
                onClick={() => {
                  setText(request.text);
                  setPriority(request.priority);
                  setStatus(request.status);
                  setEditing(false);
                }}
                className="px-4 py-2 border rounded text-sm text-gray-600 hover:bg-gray-50 transition"
              >
                Отмена
              </button>
            </div>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={() => canManageRequests && setEditing(true)}
                disabled={!canManageRequests}
                className="flex-1 flex items-center justify-center gap-1 px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 transition disabled:opacity-50"
              >
                <Pencil size={14} />
                Редактировать
              </button>
              <button
                onClick={handleDelete}
                disabled={!canManageRequests}
                className="flex items-center justify-center gap-1 px-4 py-2 border border-red-200 text-red-600 rounded text-sm hover:bg-red-50 transition disabled:opacity-50"
              >
                <Trash2 size={14} />
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
};

// -------------------------------------------------------------
// Вспомогательный компонент Field (оставляем локальным)
// -------------------------------------------------------------

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
        {label}
      </label>
      {children}
    </div>
  );
}

export default RequestSidePanel;



