// =============================================================
// src/components/documents/DocumentDetails.tsx
// Правая панель деталей документа на вкладке Documents (view).
// View-компонент:
// - не дергает API-хуки, не использует useAuth
// - получает все данные и capabilities через пропсы
// - содержит только UI и локальное состояние формы / DnD
// =============================================================

import React, { useState } from "react";
import {
  FileText,
  Download,
  ExternalLink,
  Loader2,
  AlertTriangle,
  Upload,
} from "lucide-react";

import {
  DOCUMENT_STATUS_CONFIG,
  getErrorStageLabel,
} from "../../utils/statusConfig";

import { ClassificationBadge } from "../ui/ClassificationBadge";
import { TriggerList } from "../ui/TriggerList";

import type {
  Document,
  ReclassifyInput,
  ClassificationLevel,
  StructuredDataResult,
  ReclassifyResult,
} from "../../types";

// =============================================================
// Типы для view-контракта (container → view)
// =============================================================

/**
 * Упрощённое представление классификации для view.
 * Основано на ClassificationMetadata из types/index.ts.
 */
export interface DocumentDetailsViewClassification {
  doc_type: string;
  classification_level: ClassificationLevel;
  classification_confidence: number;
  applicable_triggers: string[];
  yaml_instruction_available: boolean;
  low_confidence: boolean;
}

/**
 * Семейство документов в виде, удобном для рендера.
 * Совместимо с DocumentFamily из types/index.ts.
 */
export interface DocumentFamilyView {
  master: Document | null;
  appendices: Document[];
  amendments: Document[];
  versions: Document[];
}

/**
 * Структурированные данные для view.
 * Совместимо со StructuredDataResult из types/index.ts.
 */
export interface StructuredDataView {
  document_id: string;
  filename: string;
  doc_type?: string;
  extracted_values: StructuredDataResult["extracted_values"];
  total_extracted: number;
}

/**
 * Полный набор пропсов, которые должен получать
 * чистый view-компонент DocumentDetails.
 */
export interface DocumentDetailsViewProps {
  dealId: string;

  // Основные данные документа
  doc: Document | null;
  classification: DocumentDetailsViewClassification | null;
  family: DocumentFamilyView | null;
  structuredData: StructuredDataView | null;

  // Состояния загрузки / ошибок (минимум для этого этапа)
  isLoading: boolean;
  notFound: boolean;
  error?: string | null;
  structuredNotAvailable?: boolean;

  // Права и действия
  canDownload: boolean;
  canOpenPdf: boolean;
  canReclassify: boolean;
  pdfUrl: string | null;

  onSetReviewed: (checked: boolean) => void;
  isSetReviewedPending: boolean;

  onReclassify: (input: ReclassifyInput) => Promise<void>;
  isReclassifyPending: boolean;
  lastReclassifyResult?: ReclassifyResult;

  onNavigateToGrid?: (dealId: string, docName: string) => void;

  // Заглушка под будущую replace-логику
  onReplaceFile?: (file: File) => Promise<void> | void;
}

// =============================================================
// View-компонент (чистый UI)
// =============================================================

export const DocumentDetails: React.FC<DocumentDetailsViewProps> = ({
  dealId,
  doc,
  classification,
  family,
  structuredData,
  structuredNotAvailable,
  isLoading,
  notFound,
  error,
  canDownload,
  canOpenPdf,
  canReclassify,
  pdfUrl,
  onSetReviewed,
  isSetReviewedPending,
  onReclassify,
  isReclassifyPending,
  lastReclassifyResult,
  onNavigateToGrid,
  onReplaceFile,
}) => {
  const [isDragging, setIsDragging] = useState(false);

  // Состояние формы переклассификации
  const [showReclassifyForm, setShowReclassifyForm] = useState(false);
  const [reclassifyDocType, setReclassifyDocType] = useState("");
  const [reclassifyReason, setReclassifyReason] = useState("");
  const [rerunChecks, setRerunChecks] = useState(false);

  // Лоадер
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <Loader2 className="animate-spin mr-2" size={20} />
        Загрузка…
      </div>
    );
  }

  // 404 / notFound от стейт-хука
  if (notFound) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Документ не найден
      </div>
    );
  }

  // Настоящая ошибка (500, сеть и т.д.)
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4">
        <AlertTriangle className="text-red-500 mb-2" size={20} />
        <p className="text-sm text-red-700 mb-1">
          Ошибка загрузки документа
        </p>
        <p className="text-xs text-gray-500 max-w-sm">
          {error}
        </p>
      </div>
    );
  }

  // Нет документа — показываем сообщение (doc может быть null)
  if (!doc) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Документ не найден
      </div>
    );
  }

  const hasFamily: boolean =
    !!family &&
    (family.master !== null ||
      family.appendices.length > 0 ||
      family.amendments.length > 0 ||
      family.versions.length > 0);

  const lowConfidence =
    classification?.classification_confidence !== undefined &&
    classification?.classification_confidence !== null &&
    classification.classification_confidence < 0.6;

  const handleFile = async (file: File) => {
    if (onReplaceFile) {
      await onReplaceFile(file);
    } else {
      console.warn("Replace file not implemented yet", file.name);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      void handleFile(file);
    }
  };

  const processingError = doc.processing_error_details || null;
  const statusConfig = DOCUMENT_STATUS_CONFIG[doc.status];

  return (
    <div className="h-full overflow-y-auto p-5 space-y-6">
      {/* ========== Заголовок ========== */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-gray-900 break-words">
            {doc.filename}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {doc.folder_path || "/"}
          </p>
        </div>
        <span
          className={`shrink-0 px-2.5 py-1 rounded text-xs font-semibold ${
            statusConfig
              ? // Простейшее сопоставление цвета на Tailwind-класс.
                statusConfig.color === "success"
                ? "bg-green-100 text-green-700"
                : statusConfig.color === "warning"
                ? "bg-yellow-100 text-yellow-800"
                : statusConfig.color === "error"
                ? "bg-red-100 text-red-700"
                : statusConfig.color === "info"
                ? "bg-blue-100 text-blue-700"
                : "bg-gray-100 text-gray-600"
              : "bg-gray-100 text-gray-600"
          }`}
        >
          {statusConfig ? statusConfig.label : doc.status}
        </span>
      </div>

      {/* ========== Информация ========== */}
      <Section title="Информация">
        <InfoRow
          label="Тип документа"
          value={doc.doc_type || "Не определён"}
        />
        <InfoRow label="Язык" value={doc.language || "—"} />
        <InfoRow
          label="Страниц"
          value={doc.page_count ? String(doc.page_count) : "—"}
        />
        <InfoRow
          label="Загружен"
          value={new Date(doc.created_at).toLocaleDateString("ru-RU", {
            day: "numeric",
            month: "long",
            year: "numeric",
          })}
        />

        {/* Блок ошибки обработки, если есть */}
        {processingError && (
          <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
            <div className="flex items-start gap-2">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <div className="space-y-0.5">
                <p className="font-semibold">
                  {processingError.type === "quarantine"
                    ? "Документ в карантине"
                    : "Ошибка обработки"}
                  {(() => {
                    const stageLabel = getErrorStageLabel(processingError);
                    return stageLabel && stageLabel !== "Неизвестная стадия"
                      ? ` · ${stageLabel}`
                      : "";
                  })()}
                </p>

                {processingError.message && (
                  <p className="break-words">
                    {processingError.message}
                  </p>
                )}

                <div className="flex flex-wrap gap-2 text-[11px] text-red-700">
                  {processingError.reason && (
                    <span className="px-1.5 py-0.5 rounded bg-red-100">
                      Причина: {processingError.reason}
                    </span>
                  )}
                  {processingError.timestamp && (
                    <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                      Время:{" "}
                      {new Date(processingError.timestamp).toLocaleString("ru-RU")}
                    </span>
                  )}
                  {processingError.run_id && (
                    <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">
                      Run: {processingError.run_id}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Флаг "Проверка юриста не требуется" */}
        <div className="mt-2 flex items-center justify-between">
          <span className="text-sm text-gray-400">
            Проверка юриста не требуется
          </span>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              className="rounded border-gray-300"
              checked={!!doc.reviewed_by_person}
              disabled={isSetReviewedPending}
              onChange={(e) => onSetReviewed(e.target.checked)}
            />
          </label>
        </div>
      </Section>

      {/* ========== Классификация ========== */}
      <Section title="Классификация документа">
        {classification ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <ClassificationBadge
                level={classification.classification_level}
                confidence={classification.classification_confidence}
                showConfidence
              />
              {classification.doc_type && (
                <span className="text-sm font-medium text-gray-700">
                  {classification.doc_type}
                </span>
              )}
            </div>

            {/* YAML флаг */}
            {classification.yaml_instruction_available ? (
              <p className="text-xs text-green-600 flex items-center gap-1">
                ✅ YAML-инструкция загружена
              </p>
            ) : (
              <p className="text-xs text-gray-400 flex items-center gap-1">
                ⬜ YAML-инструкция не найдена
              </p>
            )}

            {/* Низкая уверенность */}
            {lowConfidence && (
              <div className="bg-yellow-50 border border-yellow-200 rounded p-2">
                <p className="text-xs text-yellow-800">
                  ⚠️ Низкая уверенность классификации (
                  {Math.round(
                    (classification.classification_confidence || 0) * 100,
                  )}
                  %) — рекомендуется проверить тип документа
                </p>
              </div>
            )}

            {/* Triggers */}
            {classification.applicable_triggers &&
              classification.applicable_triggers.length > 0 && (
                <div>
                  <p className="text-xs text-gray-400 mb-1">
                    Активные триггеры:
                  </p>
                  <TriggerList
                    triggers={classification.applicable_triggers}
                    maxVisible={4}
                  />
                </div>
              )}

            {/* Кнопка переклассификации (Editor+) */}
            {canReclassify && !showReclassifyForm && (
              <button
                onClick={() => {
                  setReclassifyDocType(classification.doc_type || "");
                  setShowReclassifyForm(true);
                }}
                className="mt-2 text-xs text-blue-600 hover:underline flex items-center gap-1"
              >
                ✏️ Переклассифицировать вручную
              </button>
            )}

            {/* Форма переклассификации */}
            {showReclassifyForm && (
              <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg space-y-3">
                <p className="text-xs font-semibold text-blue-800">
                  Ручная переклассификация
                </p>

                <div>
                  <label className="text-xs text-gray-500 block mb-1">
                    Новый тип документа
                  </label>
                  <input
                    type="text"
                    value={reclassifyDocType}
                    onChange={(e) => setReclassifyDocType(e.target.value)}
                    placeholder="Например: SPA, SHA, Устав, Протокол..."
                    className="w-full text-sm border rounded px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="text-xs text-gray-500 block mb-1">
                    Причина изменения
                  </label>
                  <textarea
                    value={reclassifyReason}
                    onChange={(e) => setReclassifyReason(e.target.value)}
                    rows={2}
                    placeholder="Опишите причину..."
                    className="w-full text-sm border rounded px-2 py-1.5 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={rerunChecks}
                    onChange={(e) => setRerunChecks(e.target.checked)}
                    className="rounded border-gray-300"
                  />
                  <span className="text-xs text-gray-700">
                    Перезапустить проверки по новому типу
                  </span>
                </label>

                <div className="flex gap-2">
                  <button
                    onClick={async () => {
                      if (!reclassifyDocType.trim()) return;
                      try {
                        await onReclassify({
                          doc_type: reclassifyDocType,
                          reason: reclassifyReason,
                          rerun_checks: rerunChecks,
                        } as ReclassifyInput);
                        setShowReclassifyForm(false);
                      } catch {
                        alert("Ошибка переклассификации");
                      }
                    }}
                    disabled={
                      !reclassifyDocType.trim() || isReclassifyPending
                    }
                    className="flex-1 bg-blue-600 text-white text-xs rounded py-1.5 hover:bg-blue-700 transition disabled:opacity-50"
                  >
                    {isReclassifyPending ? "Сохранение…" : "Применить"}
                  </button>
                  <button
                    onClick={() => setShowReclassifyForm(false)}
                    className="px-3 border rounded text-xs text-gray-600 hover:bg-gray-50 transition"
                  >
                    Отмена
                  </button>
                </div>

                {lastReclassifyResult && (
                  <p className="text-xs text-green-600">
                    ✅ Тип изменён на «
                    {lastReclassifyResult.new_doc_type}»
                    {lastReclassifyResult.yaml_instruction_found
                      ? " · YAML-инструкция найдена"
                      : " · YAML-инструкция не найдена"}
                  </p>
                )}
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-gray-400">
            Классификация не выполнена или документ в обработке
          </p>
        )}
      </Section>

      {/* ========== Семейство документов ========== */}
      {hasFamily && family && (
        <Section title="Семейство документов">
          {family.master && (
            <FamilyRow icon="📄" label="Основной" doc={family.master} />
          )}
          {family.appendices.map((d) => (
            <FamilyRow key={d.id} icon="📎" label="Приложение" doc={d} />
          ))}
          {family.amendments.map((d) => (
            <FamilyRow key={d.id} icon="✏️" label="Дополнение" doc={d} />
          ))}
          {family.versions.map((d) => (
            <FamilyRow key={d.id} icon="🔄" label="Версия" doc={d} />
          ))}
        </Section>
      )}

      {/* ========== Структурированные данные ========== */}

      <Section title="Структурированные данные">
        {structuredNotAvailable ? (
          <p className="text-xs text-gray-400">
            Структурированные данные можно посмотреть через меню документа
            (отдельное окно просмотра).
          </p>
        ) : structuredData && structuredData.extracted_values.length > 0 ? (
          <div className="space-y-1 bg-gray-50 rounded p-2 max-h-40 overflow-y-auto">
            {structuredData.extracted_values.map((val, idx) => (
              <div
                key={idx}
                className="flex justify-between text-xs py-0.5 border-b border-gray-100 last:border-0"
              >
                <span className="text-gray-400">
                  {val.field_name.replace(/_/g, " ")}
                </span>
                <span className="text-gray-700 font-medium text-right">
                  {val.field_value}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-400">
            Структурированные данные находятся в обработке или недоступны.
          </p>
        )}
      </Section>

      {/* ========== Действия ========== */}
      <Section title="Действия">
        <div className="flex flex-col gap-2">
          {pdfUrl && canOpenPdf && (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 transition"
            >
              <FileText size={16} />
              Открыть PDF
            </a>
          )}

          {pdfUrl && canDownload && (
            <a
              href={pdfUrl}
              download={doc.filename}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm font-medium hover:bg-gray-200 transition"
            >
              <Download size={16} />
              Скачать
            </a>
          )}

          {onNavigateToGrid && (
            <button
              onClick={() => onNavigateToGrid(dealId, doc.filename)}
              className="mt-1 text-sm text-blue-600 hover:underline flex items-center gap-1"
            >
              Открыть в DD Grid <ExternalLink size={12} />
            </button>
          )}
        </div>
      </Section>

      {/* ========== Карантин / повторная загрузка (каркас) ========== */}
      {doc.status === "quarantine" && (
        <Section title="Карантин / повторная загрузка">
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-3">
            <div className="flex items-start gap-2">
              <AlertTriangle
                size={16}
                className="text-red-500 mt-0.5 shrink-0"
              />
              <div className="text-sm text-red-800">
                <p className="font-medium mb-1">Документ в карантине</p>
                <p className="text-xs text-red-600">
                  Замените файл корректной версией, чтобы запустить
                  повторную обработку.
                </p>
              </div>
            </div>
          </div>

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-8 text-center transition ${
              isDragging
                ? "border-blue-500 bg-blue-50"
                : "border-gray-300 bg-gray-50"
            }`}
          >
            <Upload className="mx-auto text-gray-400 mb-2" size={32} />
            <p className="text-sm text-gray-600 mb-3">
              Перетащите файл сюда
            </p>
            <label className="inline-block px-4 py-2 bg-blue-600 text-white text-sm rounded cursor-pointer hover:bg-blue-700 transition">
              Выбрать файл
              <input
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleFile(file);
                }}
              />
            </label>
          </div>
        </Section>
      )}
    </div>
  );
};

// =============================================================
// Вспомогательные компоненты
// =============================================================

interface SectionProps {
  title: string;
  children: React.ReactNode;
}

const Section: React.FC<SectionProps> = ({ title, children }) => (
  <section>
    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
      {title}
    </h4>
    <div className="bg-white border border-gray-100 rounded-lg p-3 shadow-sm">
      {children}
    </div>
  </section>
);

interface InfoRowProps {
  label: string;
  value: string;
}

const InfoRow: React.FC<InfoRowProps> = ({ label, value }) => (
  <div className="flex text-sm justify-between py-0.5">
    <span className="text-gray-400">{label}</span>
    <span className="text-gray-800 font-medium max-w-[60%] text-right break-words">
      {value}
    </span>
  </div>
);

interface FamilyRowProps {
  icon: string;
  label: string;
  doc: Document;
}

const FamilyRow: React.FC<FamilyRowProps> = ({ icon, label, doc }) => (
  <div className="flex items-center justify-between text-sm py-1 border-b border-gray-100 last:border-0">
    <div className="flex items-center gap-2 min-w-0">
      <span className="text-lg">{icon}</span>
      <div className="min-w-0">
        <p className="text-gray-800 truncate">{doc.filename}</p>
        <p className="text-[11px] text-gray-400 truncate">
          {label} · {doc.doc_type || "тип не указан"}
        </p>
      </div>
    </div>
  </div>
);

export default DocumentDetails;
