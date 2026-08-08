// src/pages/PlaybooksRegistryPage.tsx
// Read-only реестр стандартных playbook.
// Показывает опубликованные playbook-версии с деталями состава.
// Позволяет экспортировать всё в Excel и Word.

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  FileSpreadsheet,
  FileText,
  RefreshCw,
  Search,
  X,
} from "lucide-react";

import client from "../api/client";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import InlineAlert from "../components/InlineAlert";
import LoadingBlock from "../components/ui/LoadingBlock";
import VersionStatusBadge from "../components/instructions/VersionStatusBadge";
import type { ApiError } from "../types";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

interface PlaybookLineShort {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  deal_type?: string | null;
  jurisdiction?: string | null;
  language?: string | null;
  risk_profile?: string | null;
}

interface PlaybookLineItem {
  kind: string;
  instruction_code: string;
  order_index: number;
}

interface PlaybookLineDetail extends PlaybookLineShort {
  items: PlaybookLineItem[];
}

interface PlaybookVersionShort {
  id: string;
  name: string;
  semver?: string | null;
  status: string;
  playbook_id?: string | null;
}

interface GlobalCheckInfo {
  id: string;
  name: string;
  description?: string | null;
  group?: string | null;
  severity?: string | null;
}

interface RegistryEntry {
  line: PlaybookLineShort;
  detail: PlaybookLineDetail | null;
  publishedVersion: PlaybookVersionShort | null;
  allVersions: PlaybookVersionShort[];
}

// ─────────────────────────────────────────────────────────────
// SectionCard
// ─────────────────────────────────────────────────────────────

interface SectionCardProps {
  title: string;
  subtitle?: string;
  rightSlot?: React.ReactNode;
  children: React.ReactNode;
}

const SectionCard: React.FC<SectionCardProps> = ({
  title,
  subtitle,
  rightSlot,
  children,
}) => (
  <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
    <div className="mb-4 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          {title}
        </h2>
        {subtitle && (
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">{subtitle}</p>
        )}
      </div>
      {rightSlot && <div className="shrink-0">{rightSlot}</div>}
    </div>
    {children}
  </section>
);

// ─────────────────────────────────────────────────────────────
// SearchInput
// ─────────────────────────────────────────────────────────────

interface SearchInputProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}

const SearchInput: React.FC<SearchInputProps> = ({
  value,
  onChange,
  placeholder = "Поиск…",
}) => (
  <div className="relative w-full sm:w-80">
    <Search
      className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]"
      aria-hidden="true"
    />
    <input
      type="search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      autoComplete="off"
      className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] py-2 pl-9 pr-9 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
    />
    {value.length > 0 && (
      <button
        type="button"
        onClick={() => onChange("")}
        aria-label="Очистить"
        className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    )}
  </div>
);

// ─────────────────────────────────────────────────────────────
// Export utils
// ─────────────────────────────────────────────────────────────

function downloadFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function escapeCsvValue(value: unknown): string {
  const str = value == null ? "" : String(value);
  if (/[",\n;]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function buildCsvExport(
  entries: RegistryEntry[],
  checksMap: Map<string, GlobalCheckInfo>,
): string {
  const rows: string[] = [];

  rows.push(
    [
      "Playbook code",
      "Playbook title",
      "Description",
      "Deal type",
      "Jurisdiction",
      "Language",
      "Risk profile",
      "Published version",
      "Semver",
      "Instruction code",
      "Instruction name",
      "Group",
      "Severity",
    ]
      .map(escapeCsvValue)
      .join(";"),
  );

  for (const entry of entries) {
    const { line, detail, publishedVersion } = entry;
    const items = detail?.items ?? [];

    if (items.length === 0) {
      rows.push(
        [
          line.code, line.title, line.description ?? "", line.deal_type ?? "",
          line.jurisdiction ?? "", line.language ?? "", line.risk_profile ?? "",
          publishedVersion?.name ?? "", publishedVersion?.semver ?? "",
          "", "", "", "",
        ].map(escapeCsvValue).join(";"),
      );
      continue;
    }

    for (const item of items) {
      const check = checksMap.get(item.instruction_code);
      rows.push(
        [
          line.code, line.title, line.description ?? "", line.deal_type ?? "",
          line.jurisdiction ?? "", line.language ?? "", line.risk_profile ?? "",
          publishedVersion?.name ?? "", publishedVersion?.semver ?? "",
          item.instruction_code, check?.name ?? "", check?.group ?? "",
          check?.severity ?? "",
        ].map(escapeCsvValue).join(";"),
      );
    }
  }

  return "\uFEFF" + rows.join("\n");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildWordExport(
  entries: RegistryEntry[],
  checksMap: Map<string, GlobalCheckInfo>,
): string {
  const parts: string[] = [];

  parts.push(`<?xml version="1.0" encoding="UTF-8"?>`);
  parts.push(
    `<html xmlns="http://www.w3.org/1999/xhtml" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word">`,
  );
  parts.push(`<head><meta charset="UTF-8" /><title>Реестр playbook</title>`);
  parts.push(`<style>
    body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: rgb(26 25 23); }
    h1 { font-size: 18pt; margin-bottom: 6pt; }
    h2 { font-size: 14pt; margin-top: 24pt; margin-bottom: 6pt; border-bottom: 1px solid rgb(232 228 221); padding-bottom: 4pt; }
    h3 { font-size: 12pt; margin-top: 12pt; margin-bottom: 4pt; }
    .meta { color: rgb(120 117 111); font-size: 10pt; margin-bottom: 8pt; }
    .desc { margin-bottom: 8pt; }
    table { border-collapse: collapse; width: 100%; margin-top: 6pt; font-size: 10pt; }
    th, td { border: 1px solid rgb(232 228 221); padding: 4pt 6pt; text-align: left; vertical-align: top; }
    th { background: rgb(243 240 235); font-weight: bold; }
    .code { font-family: Consolas, monospace; color: rgb(120 117 111); }
  </style></head><body>`);

  parts.push(`<h1>Реестр стандартных playbook</h1>`);
  parts.push(
    `<p class="meta">Сгенерировано: ${new Date().toLocaleString("ru-RU")}. Всего playbook: ${entries.length}.</p>`,
  );

  for (const entry of entries) {
    const { line, detail, publishedVersion } = entry;
    parts.push(`<h2>${escapeHtml(line.title)}</h2>`);

    const metaParts: string[] = [];
    metaParts.push(`Код: <span class="code">${escapeHtml(line.code)}</span>`);
    if (publishedVersion?.semver)
      metaParts.push(`Версия: v${escapeHtml(publishedVersion.semver)}`);
    if (line.deal_type) metaParts.push(`Тип: ${escapeHtml(line.deal_type)}`);
    if (line.jurisdiction)
      metaParts.push(`Юрисдикция: ${escapeHtml(line.jurisdiction)}`);
    if (line.language) metaParts.push(`Язык: ${escapeHtml(line.language)}`);
    parts.push(`<p class="meta">${metaParts.join(" · ")}</p>`);

    if (line.description)
      parts.push(`<p class="desc">${escapeHtml(line.description)}</p>`);

    const items = detail?.items ?? [];
    if (items.length === 0) {
      parts.push(`<p><i>Состав пуст.</i></p>`);
      continue;
    }

    parts.push(`<h3>Состав (${items.length})</h3>`);
    parts.push(`<table>`);
    parts.push(
      `<thead><tr><th>#</th><th>Instruction code</th><th>Название</th><th>Группа</th><th>Severity</th></tr></thead><tbody>`,
    );
    items.forEach((item, idx) => {
      const check = checksMap.get(item.instruction_code);
      parts.push(
        `<tr><td>${idx + 1}</td><td class="code">${escapeHtml(item.instruction_code)}</td><td>${escapeHtml(check?.name ?? "")}</td><td>${escapeHtml(check?.group ?? "")}</td><td>${escapeHtml(check?.severity ?? "")}</td></tr>`,
      );
    });
    parts.push(`</tbody></table>`);
  }

  parts.push(`</body></html>`);
  return parts.join("\n");
}

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const PlaybooksRegistryPage: React.FC = () => {
  const navigate = useNavigate();

  const [entries, setEntries] = useState<RegistryEntry[]>([]);
  const [checks, setChecks] = useState<GlobalCheckInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const loadAll = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [linesRes, versionsRes, checksRes] = await Promise.all([
        client.get<PlaybookLineShort[]>("/api/v1/playbooks/lines"),
        client.get<PlaybookVersionShort[]>("/api/v1/playbooks"),
        client.get<GlobalCheckInfo[]>("/api/v1/playbooks/checks"),
      ]);

      const lines = linesRes.data || [];
      const versions = versionsRes.data || [];
      setChecks(checksRes.data || []);

      const detailPromises: Promise<RegistryEntry | null>[] = lines.map(
        async (line): Promise<RegistryEntry | null> => {
          const lineVersions = versions.filter(
            (v) => v.playbook_id === line.id,
          );
          const published =
            lineVersions.find((v) => v.status === "published") ?? null;

          if (!published) return null;

          try {
            const detailRes = await client.get<PlaybookLineDetail>(
              `/api/v1/playbooks/lines/${line.id}`,
            );
            return {
              line,
              detail: detailRes.data,
              publishedVersion: published,
              allVersions: lineVersions,
            };
          } catch {
            return {
              line,
              detail: null,
              publishedVersion: published,
              allVersions: lineVersions,
            };
          }
        },
      );

      const results = await Promise.all(detailPromises);
      const filtered: RegistryEntry[] = results.filter(
        (r): r is RegistryEntry => r !== null,
      );
      filtered.sort((a, b) => a.line.title.localeCompare(b.line.title, "ru"));
      setEntries(filtered);
      setIsLoading(false);
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.detail || "Не удалось загрузить реестр playbook.");
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const checksMap = useMemo(() => {
    const map = new Map<string, GlobalCheckInfo>();
    for (const c of checks) map.set(c.id, c);
    return map;
  }, [checks]);

  const filteredEntries = useMemo(() => {
    if (!search.trim()) return entries;
    const q = search.trim().toLowerCase();
    return entries.filter((entry) => {
      const { line } = entry;
      return (
        line.title.toLowerCase().includes(q) ||
        line.code.toLowerCase().includes(q) ||
        (line.description?.toLowerCase().includes(q) ?? false) ||
        (line.deal_type?.toLowerCase().includes(q) ?? false) ||
        (line.jurisdiction?.toLowerCase().includes(q) ?? false)
      );
    });
  }, [entries, search]);

  const selectedEntry = useMemo(
    () => entries.find((e) => e.line.id === selectedId) ?? null,
    [entries, selectedId],
  );

  useEffect(() => {
    if (!selectedId && filteredEntries.length > 0) {
      setSelectedId(filteredEntries[0].line.id);
    }
    if (
      selectedId &&
      !filteredEntries.some((e) => e.line.id === selectedId) &&
      filteredEntries.length > 0
    ) {
      setSelectedId(filteredEntries[0].line.id);
    }
  }, [filteredEntries, selectedId]);

  const handleExportExcel = useCallback(() => {
    const csv = buildCsvExport(entries, checksMap);
    const stamp = new Date().toISOString().slice(0, 10);
    downloadFile(csv, `playbooks-registry-${stamp}.csv`, "text/csv;charset=utf-8");
  }, [entries, checksMap]);

  const handleExportWord = useCallback(() => {
    const html = buildWordExport(entries, checksMap);
    const stamp = new Date().toISOString().slice(0, 10);
    downloadFile(html, `playbooks-registry-${stamp}.doc`, "application/msword");
  }, [entries, checksMap]);

  const canExport = entries.length > 0;

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Шапка ───────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <button
                type="button"
                onClick={() => navigate("/admin/instructions")}
                className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Инструкции
              </button>

              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Реестр стандартных playbook
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Опубликованные playbook, доступные пользователям в проектах.
                Только просмотр и экспорт.
              </p>

              {!isLoading && !error && entries.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 text-[12px]">
                  <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[var(--text-secondary)]">
                    Playbook: {entries.length}
                  </span>
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleExportExcel}
                disabled={!canExport}
                leftIcon={<FileSpreadsheet className="h-3.5 w-3.5" />}
              >
                Excel
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleExportWord}
                disabled={!canExport}
                leftIcon={<FileText className="h-3.5 w-3.5" />}
              >
                Word
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void loadAll()}
                aria-label="Обновить реестр"
                leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
              >
                Обновить
              </Button>
            </div>
          </div>
        </header>

        {/* ── Alerts ───────────────────────────────────────────── */}
        {error && <InlineAlert tone="error" message={error} />}

        {/* ── Loading ──────────────────────────────────────────── */}
        {isLoading && (
          <LoadingBlock text="Загружаем реестр playbook…" rows={6} />
        )}

        {/* ── Empty ────────────────────────────────────────────── */}
        {!isLoading && !error && entries.length === 0 && (
          <EmptyState
            title="Реестр пуст"
            description="Пока нет опубликованных playbook. Создайте и опубликуйте playbook в Playbook Studio."
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate("/admin/instructions/playbook-studio")}
              >
                Открыть Playbook Studio
              </Button>
            }
          />
        )}

        {/* ── Main grid ────────────────────────────────────────── */}
        {!isLoading && !error && entries.length > 0 && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(300px,1fr)_2fr]">
            <SectionCard
              title="Playbook"
              rightSlot={
                <span className="text-[11px] text-[var(--text-muted)]">
                  {filteredEntries.length} / {entries.length}
                </span>
              }
            >
              <div className="mb-3">
                <SearchInput
                  value={search}
                  onChange={setSearch}
                  placeholder="Поиск по названию, коду…"
                />
              </div>

              {filteredEntries.length === 0 ? (
                <p className="rounded-lg border border-dashed border-[var(--border)] px-3 py-6 text-center text-xs text-[var(--text-muted)]">
                  Ничего не найдено.
                </p>
              ) : (
                <ul className="max-h-[36rem] space-y-1.5 overflow-y-auto overscroll-contain">
                  {filteredEntries.map((entry) => {
                    const { line, publishedVersion } = entry;
                    const isSelected = selectedId === line.id;
                    return (
                      <li key={line.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedId(line.id)}
                          className={[
                            "w-full rounded-xl border px-3 py-2.5 text-left text-xs transition-colors",
                            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
                            isSelected
                              ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                              : "border-[var(--border-soft)] hover:border-[var(--border-strong)]",
                          ].join(" ")}
                        >
                          <div className="flex items-start gap-2">
                            <BookOpen
                              className={[
                                "mt-0.5 h-3.5 w-3.5 shrink-0",
                                isSelected
                                  ? "text-[var(--accent-primary)]"
                                  : "text-[var(--text-muted)]",
                              ].join(" ")}
                              aria-hidden="true"
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="truncate font-semibold text-[var(--text-primary)]">
                                  {line.title}
                                </span>
                                {publishedVersion?.semver && (
                                  <span className="shrink-0 font-mono text-[10px] text-[var(--text-muted)]">
                                    v{publishedVersion.semver}
                                  </span>
                                )}
                              </div>
                              <div className="mt-0.5 truncate font-mono text-[10px] text-[var(--text-muted)]">
                                {line.code}
                              </div>
                            </div>
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </SectionCard>

            <SectionCard title="Детали playbook">
              {!selectedEntry ? (
                <EmptyState
                  title="Playbook не выбран"
                  description="Выберите playbook слева для просмотра деталей."
                />
              ) : (
                <PlaybookDetailView
                  entry={selectedEntry}
                  checksMap={checksMap}
                  onExportExcel={handleExportExcel}
                  onExportWord={handleExportWord}
                />
              )}
            </SectionCard>
          </div>
        )}
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// PlaybookDetailView
// ─────────────────────────────────────────────────────────────

interface PlaybookDetailViewProps {
  entry: RegistryEntry;
  checksMap: Map<string, GlobalCheckInfo>;
  onExportExcel: () => void;
  onExportWord: () => void;
}

const PlaybookDetailView: React.FC<PlaybookDetailViewProps> = ({
  entry,
  checksMap,
}) => {
  const { line, detail, publishedVersion } = entry;
  const items = detail?.items ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-[var(--text-primary)]">
              {line.title}
            </h3>
            {publishedVersion && (
              <VersionStatusBadge status={publishedVersion.status} size="xs" />
            )}
          </div>
          <div className="mt-0.5 font-mono text-xs text-[var(--text-muted)]">
            {line.code}
          </div>
        </div>
      </div>

      {line.description && (
        <p className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-3 text-xs leading-relaxed text-[var(--text-secondary)]">
          {line.description}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetaCell
          label="Версия"
          value={publishedVersion?.semver ? `v${publishedVersion.semver}` : "—"}
          mono
        />
        <MetaCell label="Тип сделки" value={line.deal_type ?? "—"} />
        <MetaCell label="Юрисдикция" value={line.jurisdiction ?? "—"} />
        <MetaCell label="Язык" value={line.language ?? "—"} />
      </div>

      <div className="space-y-3">
        <h4 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Состав playbook
          <span className="ml-1.5 normal-case tracking-normal text-[var(--text-faint)]">
            · {items.length}
          </span>
        </h4>

        {items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[var(--border)] px-3 py-6 text-center text-xs text-[var(--text-muted)]">
            Состав пуст.
          </p>
        ) : (
          <div className="rounded-xl border border-[var(--border)]">
            <div className="grid grid-cols-[2rem_1fr_auto] items-center gap-2 border-b border-[var(--border-soft)] px-3 py-2">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                #
              </div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                Инструкция
              </div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
                Severity
              </div>
            </div>
            <div className="divide-y divide-[var(--border-soft)]">
              {items.map((item, index) => {
                const check = checksMap.get(item.instruction_code);
                return (
                  <div
                    key={`${index}-${item.instruction_code}`}
                    className="grid grid-cols-[2rem_1fr_auto] items-center gap-2 px-3 py-2"
                  >
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">
                      {index + 1}
                    </span>
                    <div className="min-w-0">
                      <div className="truncate font-mono text-xs font-semibold text-[var(--text-primary)]">
                        {item.instruction_code}
                      </div>
                      {check && (
                        <div className="mt-0.5 flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
                          <span className="truncate">{check.name}</span>
                          {check.group && (
                            <>
                              <span>·</span>
                              <span className="truncate">{check.group}</span>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                    <span className="text-[10px] text-[var(--text-muted)]">
                      {check?.severity ?? "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// MetaCell
// ─────────────────────────────────────────────────────────────

const MetaCell: React.FC<{
  label: string;
  value: string;
  mono?: boolean;
}> = ({ label, value, mono }) => (
  <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-2.5">
    <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
      {label}
    </div>
    <div
      className={[
        "mt-0.5 text-xs text-[var(--text-primary)]",
        mono ? "font-mono" : "",
      ].join(" ")}
    >
      {value}
    </div>
  </div>
);

export default PlaybooksRegistryPage;


