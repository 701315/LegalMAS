// =============================================================
// src/components/requests/RequestSidePanel.tsx
// Side panel деталей DD-запроса для юриста.
// - Приоритет (селектор)
// - Статус (селектор)
// - Текст запроса (редактируемый)
// - Адресат
// - Источник (badge + пояснение для yaml_template)
// - Связанные документы
// - Проверка (check_id)
// - Извлечённые данные (structured_values)
// - Действия: копировать текст, сохранить, удалить
// =============================================================

import React, { useEffect, useState } from "react";
import type { DDRequest } from "../../types";
import { DD_REQUEST_SOURCE_DISPLAY } from "../../constants";
import { X, Clipboard, Check, Trash2, Pencil, Loader2 } from "lucide-react";

interface Props {
  request: DDRequest | null;
  onClose: () => void;
  onSave: (reqId: string, data: Partial<DDRequest>) => Promise<void>;
  onDelete: (reqId: string) => Promise<void>;
  isSaving: boolean;
  canManageRequests: boolean;
}

export const RequestSidePanel: React.FC<Props> = ({
  request,
  onClose,
  onSave,
  onDelete,
  isSaving,
  canManageRequests,
}) => {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [priority, setPriority] = useState<DDRequest["priority"]>("medium");
  const [status, setStatus] = useState<DDRequest["status"]>("open");
  const [copied, setCopied] = useState(false);

  // Синхронизация при выборе нового запроса
  useEffect(() => {
    if (request) {
      setText(request.text);
      setPriority(request.priority);
      setStatus(request.status);
      setEditing(false);
    }
  }, [request]);

  // Закрытие по Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!request) return null;

  // Копирование текста
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Сохранение изменений
  const handleSave = async () => {
    if (!canManageRequests) return;
    await onSave(request.id, { text, priority, status });
    setEditing(false);
  };

  // Удаление запроса
  const handleDelete = async () => {
    if (!canManageRequests) return;
    if (!confirm("Удалить запрос? Это действие нельзя отменить.")) return;
    await onDelete(request.id);
    onClose();
  };

  // Приоритеты — фиксированный список (из типа)
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

  const sourceCfg = request.source
    ? DD_REQUEST_SOURCE_DISPLAY[request.source]
    : undefined;

  const documentCount = Array.isArray(request.document_refs)
    ? request.document_refs.length
    : 0;

  return (
    <>
      {/* Затемнение */}
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
      />

      {/* Панель */}
      <div className="fixed right-0 top-0 h-full w-[420px] bg-white shadow-2xl z-50 border-l flex flex-col animate-in slide-in-from-right">
        {/* Шапка */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="text-lg font-semibold text-gray-900">
            Запрос #{request.id.slice(-6)}
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-100 rounded transition"
          >
            <X size={20} />
          </button>
        </div>

        {/* Тело */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Приоритет */}
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

          {/* Статус */}
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
          {request.addressee && (
            <Field label="Адресат">
              <p className="text-sm text-gray-700 font-medium">
                {request.addressee}
              </p>
            </Field>
          )}

          {/* Источник */}
          {request.source && (
            <Field label="Источник">
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                  sourceCfg?.color || "bg-gray-100 text-gray-600"
                }`}
              >
                {sourceCfg?.icon && (
                  <span aria-hidden="true">{sourceCfg.icon}</span>
                )}
                <span>
                  {sourceCfg?.label || request.source}
                </span>
              </span>
              {request.source === "yaml_template" && (
                <p className="text-xs text-purple-600 mt-1">
                  Текст и адресат сгенерированы автоматически
                  из YAML-инструкции типа документа.
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
              disabled={!editing || !canManageRequests}
              className="w-full p-2 border rounded text-sm resize-y disabled:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </Field>

          {/* Документы */}
          <Field label={`Документы (${documentCount})`}>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {request.document_refs.slice(0, 10).map((docId, i) => (
                <div
                  key={docId ?? i}
                  className="flex items-center gap-2 text-sm text-gray-700 p-2 bg-gray-50 rounded"
                >
                  <span>📄</span>
                  <span className="truncate">{docId}</span>
                </div>
              ))}
              {documentCount > 10 && (
                <p className="text-xs text-gray-400 py-1 text-center">
                  … и ещё {documentCount - 10}
                </p>
              )}
            </div>
          </Field>

          {/* Проверка */}
          <Field label="Проверка">
            <p className="text-sm text-gray-700">
              {request.check_id ?? "—"}
            </p>
            {request.source === "yaml_template" && (
              <p className="text-xs text-gray-400 mt-0.5">
                Связано с YAML‑проверкой (check_id).
              </p>
            )}
          </Field>

          {/* Извлечённые данные */}
          {request.structured_values &&
            request.structured_values.length > 0 && (
              <Field
                label={`Извлечённые данные (${request.structured_values.length})`}
              >
                <div className="space-y-1 bg-gray-50 rounded p-2 max-h-40 overflow-y-auto">
                  {request.structured_values.map((sv, i) => {
                    const [key] = Object.keys(sv);
                    const [val] = Object.values(sv);
                    return (
                      <div
                        key={i}
                        className="flex justify-between text-xs py-0.5 border-b border-gray-100 last:border-0"
                      >
                        <span className="text-gray-400 capitalize">
                          {String(key || "").replace(/_/g, " ")}
                        </span>
                        <span className="text-gray-700 font-medium text-right">
                          {val != null ? String(val) : "—"}
                        </span>
                      </div>
                    );
                  })}
                </div>
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
                <Check
                  size={14}
                  className="text-green-600"
                />
                <span className="text-green-600">
                  Скопировано!
                </span>
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
                  <Loader2
                    className="animate-spin"
                    size={14}
                  />
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
