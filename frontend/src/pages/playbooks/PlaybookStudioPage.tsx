// src/pages/instructions/PlaybookStudioPage.tsx

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpen,
  GitBranch,
  Plus,
  RefreshCw,
  Settings,
  Trash2,
} from "lucide-react";

import client from "../../api/client";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export type PlaybookStudioScope = "admin" | "tenant";

interface PlaybookStudioPageProps {
  scope: PlaybookStudioScope;
}

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

interface PlaybookLineItemPayload {
  kind: string;
  instruction_code: string;
  order_index: number;
}

interface PlaybookLineDetail {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  deal_type?: string | null;
  jurisdiction?: string | null;
  language?: string | null;
  risk_profile?: string | null;
  items: PlaybookLineItemPayload[];
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
  category?: string | null;
  group?: string | null;
  severity?: string | null;
  doc_types?: string[] | null;
}

interface ModelConfig {
  id: string;
  name: string;
}

interface PlaybookVersionCreateResponse {
  id: string;
  name: string;
  semver?: string | null;
  status: string;
  playbook_id?: string | null;
}

// ─────────────────────────────────────────────────────────────
// Утилиты
// ─────────────────────────────────────────────────────────────

function extractApiErrorMessage(err: unknown, fallback: string): string {
  if (typeof err !== "object" || err === null) return fallback;
  const record = err as Record<string, unknown>;
  const detail = record["detail"];
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first && typeof first === "object") {
      const msg = (first as Record<string, unknown>)["msg"];
      const loc = (first as Record<string, unknown>)["loc"];
      const locText = Array.isArray(loc) ? loc.join(".") : "body";
      if (typeof msg === "string") return `${locText}: ${msg}`;
    }
    return "Ошибка валидации данных формы.";
  }
  return fallback;
}

function normalizeLineItems(
  items: PlaybookLineItemPayload[] | undefined,
): PlaybookLineItemPayload[] {
  if (!items || items.length === 0) return [];
  return items.map((item, index) => ({
    kind: item.kind || "check",
    instruction_code: item.instruction_code || "",
    order_index: index,
  }));
}

function buildLineItemsPayload(
  items: PlaybookLineItemPayload[],
): PlaybookLineItemPayload[] {
  return items
    .map((item, index) => ({
      kind: item.kind || "check",
      instruction_code: item.instruction_code.trim(),
      order_index: index,
    }))
    .filter((item) => item.instruction_code.length > 0);
}

// ─────────────────────────────────────────────────────────────
// Стили форм
// ─────────────────────────────────────────────────────────────

const inputClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60";

const textareaClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60";

const selectClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:cursor-not-allowed disabled:opacity-60";

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
// InstructionPicker
// ─────────────────────────────────────────────────────────────

interface InstructionPickerProps {
  globalChecks: GlobalCheckInfo[];
  alreadyAdded: Set<string>;
  disabled: boolean;
  onAdd: (code: string) => void;
}

const InstructionPicker: React.FC<InstructionPickerProps> = ({
  globalChecks,
  alreadyAdded,
  disabled,
  onAdd,
}) => {
  const [selectedGroup, setSelectedGroup] = useState<string>("__all__");
  const [selectedCode, setSelectedCode] = useState<string>("");

  const groups = useMemo(() => {
    const set = new Set<string>();
    for (const c of globalChecks) {
      if (c.group) set.add(c.group);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b, "ru"));
  }, [globalChecks]);

  const filteredChecks = useMemo(() => {
    const filtered =
      selectedGroup === "__all__"
        ? globalChecks
        : globalChecks.filter((c) => c.group === selectedGroup);
    return filtered.filter((c) => !alreadyAdded.has(c.id));
  }, [globalChecks, selectedGroup, alreadyAdded]);

  useEffect(() => {
    if (selectedCode && !filteredChecks.some((c) => c.id === selectedCode)) {
      setSelectedCode(filteredChecks[0]?.id ?? "");
    }
  }, [filteredChecks, selectedCode]);

  useEffect(() => {
    if (!selectedCode && filteredChecks.length > 0) {
      setSelectedCode(filteredChecks[0].id);
    }
  }, [filteredChecks, selectedCode]);

  const handleAdd = () => {
    if (!selectedCode) return;
    onAdd(selectedCode);
    setSelectedCode(
      filteredChecks.find((c) => c.id !== selectedCode)?.id ?? "",
    );
  };

  const selectedCheckInfo = globalChecks.find((c) => c.id === selectedCode);

  return (
    <div className="space-y-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        Добавить инструкцию
      </h3>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
            Группа
          </label>
          <select
            className={selectClassName}
            value={selectedGroup}
            onChange={(e) => setSelectedGroup(e.target.value)}
            disabled={disabled}
          >
            <option value="__all__">Все группы</option>
            {groups.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
            Инструкция
          </label>
          <select
            className={selectClassName}
            value={selectedCode}
            onChange={(e) => setSelectedCode(e.target.value)}
            disabled={disabled || filteredChecks.length === 0}
          >
            {filteredChecks.length === 0 ? (
              <option value="">Все добавлены</option>
            ) : (
              filteredChecks.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name || c.id}
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      {selectedCheckInfo && (
        <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
            <span className="font-mono font-semibold text-[var(--text-primary)]">
              {selectedCheckInfo.id}
            </span>
            {selectedCheckInfo.group && (
              <span className="text-[var(--text-muted)]">
                {selectedCheckInfo.group}
              </span>
            )}
            {selectedCheckInfo.severity && (
              <span className="text-[var(--text-muted)]">
                {selectedCheckInfo.severity}
              </span>
            )}
          </div>
          {selectedCheckInfo.description && (
            <p className="mt-1 line-clamp-2 text-[var(--text-muted)]">
              {selectedCheckInfo.description}
            </p>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <Button
          variant="secondary"
          size="sm"
          onClick={handleAdd}
          disabled={disabled || !selectedCode || filteredChecks.length === 0}
          leftIcon={<Plus className="h-3.5 w-3.5" />}
        >
          Добавить
        </Button>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// TemplateItemsTable
// ─────────────────────────────────────────────────────────────

interface TemplateItemsTableProps {
  items: PlaybookLineItemPayload[];
  globalChecks: GlobalCheckInfo[];
  disabled: boolean;
  onRemove: (index: number) => void;
}

const TemplateItemsTable: React.FC<TemplateItemsTableProps> = ({
  items,
  globalChecks,
  disabled,
  onRemove,
}) => {
  const checksMap = useMemo(() => {
    const map = new Map<string, GlobalCheckInfo>();
    for (const c of globalChecks) map.set(c.id, c);
    return map;
  }, [globalChecks]);

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-[var(--border)] px-3 py-6 text-center text-xs text-[var(--text-muted)]">
        Состав пуст. Используйте блок выше чтобы добавить инструкции.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--border)]">
      <div className="grid grid-cols-[2rem_1fr_auto] items-center gap-2 border-b border-[var(--border-soft)] px-3 py-2">
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
          #
        </div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-faint)]">
          Инструкция
        </div>
        <div />
      </div>
      <div className="divide-y divide-[var(--border-soft)]">
        {items.map((item, index) => {
          const checkInfo = item.instruction_code
            ? checksMap.get(item.instruction_code)
            : null;
          return (
            <div
              key={`${index}-${item.instruction_code}`}
              className="group grid grid-cols-[2rem_1fr_auto] items-center gap-2 px-3 py-2 transition-colors hover:bg-[var(--bg-elevated-soft)]"
            >
              <span className="text-[10px] font-mono text-[var(--text-muted)]">
                {index + 1}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-mono text-xs font-semibold text-[var(--text-primary)]">
                    {item.instruction_code}
                  </span>
                  {checkInfo?.severity && (
                    <span className="shrink-0 text-[10px] text-[var(--text-muted)]">
                      {checkInfo.severity}
                    </span>
                  )}
                </div>
                {checkInfo && (
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
                    <span className="truncate">{checkInfo.name}</span>
                    {checkInfo.group && (
                      <>
                        <span>·</span>
                        <span className="truncate">{checkInfo.group}</span>
                      </>
                    )}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => onRemove(index)}
                disabled={disabled}
                className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-muted)] opacity-0 transition-all hover:bg-rose-50 hover:text-rose-500 group-hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-30"
                aria-label={`Удалить ${item.instruction_code}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// PlaybookStudioPage
// ─────────────────────────────────────────────────────────────

const PlaybookStudioPage: React.FC<PlaybookStudioPageProps> = ({ scope }) => {
  const navigate = useNavigate();

  const [selectedPlaybookId, setSelectedPlaybookId] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [isNewTemplateMode, setIsNewTemplateMode] = useState(false);
  const [templateEtag, setTemplateEtag] = useState<string | null>(null);
  const [templateTitle, setTemplateTitle] = useState("");
  const [templateDescription, setTemplateDescription] = useState("");
  const [templateDealType, setTemplateDealType] = useState("");
  const [templateJurisdiction, setTemplateJurisdiction] = useState("");
  const [templateLanguage, setTemplateLanguage] = useState("");
  const [templateItems, setTemplateItems] = useState<PlaybookLineItemPayload[]>([]);
  const [newVersionName, setNewVersionName] = useState("");
  const [newVersionSemver, setNewVersionSemver] = useState("0.1.0");
  const [selectedModelConfigId, setSelectedModelConfigId] = useState("");
  const [isCreatingVersion, setIsCreatingVersion] = useState(false);
  const [isPublishingVersion, setIsPublishingVersion] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [successText, setSuccessText] = useState<string | null>(null);

  // ── Queries ─────────────────────────────────────────────
  const playbooksQuery = useQuery({
    queryKey: ["playbook-studio", scope, "lines"],
    queryFn: async () => {
      const res = await client.get<PlaybookLineShort[]>("/api/v1/playbooks/lines");
      return res.data;
    },
  });

  const versionsQuery = useQuery({
    queryKey: ["playbook-studio", scope, "versions"],
    queryFn: async () => {
      const res = await client.get<PlaybookVersionShort[]>("/api/v1/playbooks");
      return res.data;
    },
  });

  const checksQuery = useQuery({
    queryKey: ["playbook-studio", scope, "global-checks"],
    queryFn: async () => {
      const res = await client.get<GlobalCheckInfo[]>("/api/v1/playbooks/checks");
      return res.data;
    },
  });

  const modelConfigsQuery = useQuery({
    queryKey: ["playbook-studio", scope, "model-configs"],
    queryFn: async () => {
      const res = await client.get<ModelConfig[]>("/api/v1/model-configs");
      return res.data;
    },
  });

  const playbooks = playbooksQuery.data ?? [];
  const versions = versionsQuery.data ?? [];
  const globalChecks = checksQuery.data ?? [];
  const modelConfigs = modelConfigsQuery.data ?? [];

  const selectedPlaybook =
    playbooks.find((item) => item.id === selectedPlaybookId) ?? null;

  const visibleVersions = useMemo(() => {
    if (!selectedPlaybookId) return [];
    return versions.filter(
      (v) => v.playbook_id === selectedPlaybookId && v.status !== "archived",
    );
  }, [versions, selectedPlaybookId]);

  const alreadyAddedCodes = useMemo(
    () => new Set(templateItems.map((i) => i.instruction_code).filter(Boolean)),
    [templateItems],
  );

  // ── Effects ─────────────────────────────────────────────
  useEffect(() => {
    if (!selectedPlaybookId && playbooks.length > 0 && !isNewTemplateMode) {
      setSelectedPlaybookId(playbooks[0].id);
    }
  }, [playbooks, selectedPlaybookId, isNewTemplateMode]);

  useEffect(() => {
    if (!selectedVersionId && visibleVersions.length > 0) {
      setSelectedVersionId(visibleVersions[0].id);
      return;
    }
    if (selectedVersionId && !visibleVersions.some((v) => v.id === selectedVersionId)) {
      setSelectedVersionId(visibleVersions[0]?.id ?? null);
    }
  }, [visibleVersions, selectedVersionId]);

  useEffect(() => {
    if (modelConfigs.length > 0 && !selectedModelConfigId) {
      setSelectedModelConfigId(modelConfigs[0].id);
    }
  }, [modelConfigs, selectedModelConfigId]);

  useEffect(() => {
    let cancelled = false;

    async function loadTemplateDetail(playbookId: string) {
      try {
        const res = await client.get<PlaybookLineDetail>(
          `/api/v1/playbooks/lines/${playbookId}`,
        );
        if (cancelled) return;
        const etag =
          (res.headers["etag"] as string | undefined) ??
          (res.headers["ETag"] as string | undefined) ??
          null;
        setTemplateEtag(etag);
        setTemplateTitle(res.data.title ?? "");
        setTemplateDescription(res.data.description ?? "");
        setTemplateDealType(res.data.deal_type ?? "");
        setTemplateJurisdiction(res.data.jurisdiction ?? "");
        setTemplateLanguage(res.data.language ?? "");
        setTemplateItems(normalizeLineItems(res.data.items));
        setIsNewTemplateMode(false);
      } catch {
        if (!cancelled) {
          setErrorText("Не удалось загрузить детали шаблона.");
        }
      }
    }

    if (selectedPlaybookId && !isNewTemplateMode) {
      void loadTemplateDetail(selectedPlaybookId);
    }
    return () => {
      cancelled = true;
    };
  }, [selectedPlaybookId, isNewTemplateMode]);

  useEffect(() => {
    if (selectedPlaybook && !isNewTemplateMode) {
      setNewVersionName(`${selectedPlaybook.title} Draft`);
      setNewVersionSemver("0.1.0");
    }
  }, [selectedPlaybook, isNewTemplateMode]);

  // ── Config ──────────────────────────────────────────────
  const scopeConfig =
    scope === "admin"
      ? {
          backPath: "/admin/instructions",
          backLabel: "Инструкции",
          title: "Playbook Studio",
          subtitle: "Создание и управление шаблонами playbook и их версиями.",
          modelConfigsPath: "/admin/model-configs",
        }
      : {
          backPath: "/tenant-admin/instructions",
          backLabel: "Инструкции",
          title: "Playbook Studio",
          subtitle: "Создание и управление шаблонами playbook и их версиями.",
          modelConfigsPath: "/admin/model-configs",
        };

  // ── Handlers ────────────────────────────────────────────
  const resetMessages = () => {
    setErrorText(null);
    setSuccessText(null);
  };

  const handleRefresh = async () => {
    await Promise.all([
      playbooksQuery.refetch(),
      versionsQuery.refetch(),
      checksQuery.refetch(),
      modelConfigsQuery.refetch(),
    ]);
  };

  const handleStartNewTemplate = () => {
    resetMessages();
    setIsNewTemplateMode(true);
    setSelectedPlaybookId(null);
    setSelectedVersionId(null);
    setTemplateEtag(null);
    setTemplateTitle("");
    setTemplateDescription("");
    setTemplateDealType("");
    setTemplateJurisdiction("");
    setTemplateLanguage("");
    setTemplateItems([]);
  };

  const handleSelectExistingTemplate = (playbookId: string) => {
    resetMessages();
    setIsNewTemplateMode(false);
    setSelectedPlaybookId(playbookId);
  };

  const handleAddInstruction = (code: string) => {
    if (alreadyAddedCodes.has(code)) return;
    setTemplateItems((prev) => [
      ...prev,
      { kind: "check", instruction_code: code, order_index: prev.length },
    ]);
  };

  const handleRemoveTemplateItem = (index: number) => {
    setTemplateItems((prev) =>
      prev
        .filter((_, i) => i !== index)
        .map((item, idx) => ({ ...item, order_index: idx })),
    );
  };

  /**
   * Сохраняет template на сервер (create или update).
   * Возвращает playbook_id для последующего создания version.
   */
  const saveTemplateFirst = async (): Promise<string | null> => {
    const normalizedTitle = templateTitle.trim();
    const itemsPayload = buildLineItemsPayload(templateItems);

    if (!normalizedTitle) {
      setErrorText("Укажите название шаблона playbook.");
      return null;
    }
    if (itemsPayload.length === 0) {
      setErrorText("Добавьте хотя бы одну инструкцию в состав шаблона.");
      return null;
    }

    const payload = {
      title: normalizedTitle,
      description: templateDescription.trim() || null,
      deal_type: templateDealType.trim() || null,
      jurisdiction: templateJurisdiction.trim() || null,
      language: templateLanguage.trim() || null,
      items: itemsPayload,
    };

    if (isNewTemplateMode) {
      const res = await client.post<PlaybookLineDetail>(
        "/api/v1/playbooks/lines",
        payload,
      );
      await playbooksQuery.refetch();
      setSelectedPlaybookId(res.data.id);
      setIsNewTemplateMode(false);
      return res.data.id;
    }

    if (!selectedPlaybookId) {
      setErrorText("Не выбран шаблон для сохранения.");
      return null;
    }
    if (!templateEtag) {
      setErrorText("Не удалось определить версию шаблона. Обновите страницу.");
      return null;
    }

    const res = await client.put<PlaybookLineDetail>(
      `/api/v1/playbooks/lines/${selectedPlaybookId}`,
      payload,
      { headers: { "If-Match": templateEtag } },
    );

    setTemplateEtag(
      (res.headers["etag"] as string | undefined) ??
        (res.headers["ETag"] as string | undefined) ??
        null,
    );
    await playbooksQuery.refetch();
    return selectedPlaybookId;
  };

  /**
   * Единая функция: сохраняет template → создаёт version → опционально публикует.
   */
  const handleCreateVersion = async (andPublish: boolean) => {
    resetMessages();

    if (!selectedModelConfigId) {
      setErrorText("Выберите конфигурацию модели.");
      return;
    }

    andPublish ? setIsPublishingVersion(true) : setIsCreatingVersion(true);

    try {
      // Шаг 1: сохраняем template
      const playbookId = await saveTemplateFirst();
      if (!playbookId) {
        // saveTemplateFirst уже установил errorText
        return;
      }

      // Шаг 2: создаём draft version
      const res = await client.post<PlaybookVersionCreateResponse>(
        "/api/v1/playbooks",
        {
          name: newVersionName.trim() || "Playbook Draft",
          bundles: [],
          include_ids: [],
          exclude_ids: [],
          profile: null,
          semver: newVersionSemver.trim() || "0.1.0",
          status: "draft",
          playbook_id: playbookId,
          from_line_id: playbookId,
          model_config_id: selectedModelConfigId,
        },
      );

      const newVersionId = res.data.id;

      if (andPublish) {
        // Шаг 3: публикуем
        try {
          await client.post(`/api/v1/playbooks/${newVersionId}/publish`);
          setSuccessText("Шаблон сохранён. Версия playbook создана и опубликована.");
        } catch (publishErr) {
          setErrorText(
            extractApiErrorMessage(
              publishErr,
              "Шаблон сохранён, черновик создан, но публикация не удалась.",
            ),
          );
        }
      } else {
        setSuccessText("Шаблон сохранён. Черновик версии playbook создан.");
      }

      await versionsQuery.refetch();
      setSelectedVersionId(newVersionId);
    } catch (err) {
      setErrorText(
        extractApiErrorMessage(err, "Не удалось создать версию playbook."),
      );
    } finally {
      setIsCreatingVersion(false);
      setIsPublishingVersion(false);
    }
  };

  const isBusy = isCreatingVersion || isPublishingVersion;

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">
        {/* ── Back-link ────────────────────────────────────── */}
        <button
          type="button"
          onClick={() => navigate(scopeConfig.backPath)}
          className="flex shrink-0 items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {scopeConfig.backLabel}
        </button>

        {/* ── Header ───────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-4">
          <header>
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              {scopeConfig.title}
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {scopeConfig.subtitle}
            </p>
          </header>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handleRefresh()}
            aria-label="Обновить"
            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
          />
        </div>

        {/* ── Alerts ───────────────────────────────────────── */}
        {errorText && <InlineAlert tone="error" message={errorText} />}
        {successText && <InlineAlert tone="success" message={successText} />}

        {/* ── Main 3-column grid ───────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
          {/* ── Левая: Шаблоны ────────────────────────────── */}
          <div className="xl:col-span-3">
            <SectionCard
              title="Шаблоны"
              rightSlot={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleStartNewTemplate}
                  disabled={isBusy}
                  leftIcon={<Plus className="h-3.5 w-3.5" />}
                >
                  Новый
                </Button>
              }
            >
              {playbooksQuery.isLoading && (
                <LoadingBlock text="Загружаем шаблоны…" rows={6} />
              )}

              {playbooksQuery.isError && (
                <InlineAlert tone="error" message="Не удалось загрузить шаблоны." />
              )}

              {!playbooksQuery.isLoading &&
                !playbooksQuery.isError &&
                playbooks.length === 0 && (
                  <EmptyState
                    title="Шаблонов нет"
                    description="Создайте первый шаблон playbook."
                  />
                )}

              {!playbooksQuery.isLoading &&
                !playbooksQuery.isError &&
                playbooks.length > 0 && (
                  <ul className="space-y-1.5">
                    {playbooks.map((playbook) => {
                      const isSelected =
                        !isNewTemplateMode && selectedPlaybookId === playbook.id;
                      return (
                        <li key={playbook.id}>
                          <button
                            type="button"
                            onClick={() => handleSelectExistingTemplate(playbook.id)}
                            disabled={isBusy}
                            className={[
                              "w-full rounded-xl border px-3 py-2.5 text-left text-xs transition-colors",
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
                                <div className="truncate font-semibold text-[var(--text-primary)]">
                                  {playbook.title}
                                </div>
                                <div className="mt-0.5 truncate font-mono text-[10px] text-[var(--text-muted)]">
                                  {playbook.code}
                                </div>
                                {playbook.description && (
                                  <div className="mt-1 line-clamp-2 text-[11px] text-[var(--text-secondary)]">
                                    {playbook.description}
                                  </div>
                                )}
                              </div>
                            </div>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
            </SectionCard>
          </div>

          {/* ── Центральная: Редактор шаблона ─────────────── */}
          <div className="xl:col-span-5">
            <SectionCard
              title={isNewTemplateMode ? "Новый шаблон" : "Редактор шаблона"}
            >
              {!isNewTemplateMode && !selectedPlaybookId ? (
                <EmptyState
                  title="Шаблон не выбран"
                  description="Выберите существующий шаблон слева или создайте новый."
                />
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="sm:col-span-2">
                      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Название
                      </label>
                      <input
                        type="text"
                        className={inputClassName}
                        value={templateTitle}
                        onChange={(e) => setTemplateTitle(e.target.value)}
                        disabled={isBusy}
                        placeholder="Например: Real Estate DD RU"
                      />
                    </div>

                    <div className="sm:col-span-2">
                      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Описание
                      </label>
                      <textarea
                        className={textareaClassName}
                        rows={2}
                        value={templateDescription}
                        onChange={(e) => setTemplateDescription(e.target.value)}
                        disabled={isBusy}
                        placeholder="Короткое описание назначения шаблона…"
                      />
                    </div>

                    <div>
                      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Тип сделки
                      </label>
                      <input
                        type="text"
                        className={inputClassName}
                        value={templateDealType}
                        onChange={(e) => setTemplateDealType(e.target.value)}
                        disabled={isBusy}
                        placeholder="mna / real_estate / nda …"
                      />
                    </div>

                    <div>
                      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Юрисдикция
                      </label>
                      <input
                        type="text"
                        className={inputClassName}
                        value={templateJurisdiction}
                        onChange={(e) => setTemplateJurisdiction(e.target.value)}
                        disabled={isBusy}
                        placeholder="RU / EN / DE …"
                      />
                    </div>

                    <div>
                      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Язык
                      </label>
                      <input
                        type="text"
                        className={inputClassName}
                        value={templateLanguage}
                        onChange={(e) => setTemplateLanguage(e.target.value)}
                        disabled={isBusy}
                        placeholder="ru / en / de …"
                      />
                    </div>
                  </div>

                  {/* Picker */}
                  <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] p-4">
                    <InstructionPicker
                      globalChecks={globalChecks}
                      alreadyAdded={alreadyAddedCodes}
                      disabled={isBusy}
                      onAdd={handleAddInstruction}
                    />
                  </div>

                  {/* Таблица состава */}
                  <div>
                    <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      Состав шаблона
                      <span className="ml-1.5 normal-case tracking-normal text-[var(--text-faint)]">
                        · {templateItems.length}
                      </span>
                    </h3>
                    <TemplateItemsTable
                      items={templateItems}
                      globalChecks={globalChecks}
                      disabled={isBusy}
                      onRemove={handleRemoveTemplateItem}
                    />
                  </div>
                </div>
              )}
            </SectionCard>
          </div>

          {/* ── Правая: Версия playbook ────────────────────── */}
          <div className="xl:col-span-4">
            <SectionCard
              title="Версия playbook"
              subtitle="Сохранение шаблона и создание версии — одним действием."
            >
              {!selectedPlaybookId && !isNewTemplateMode ? (
                <EmptyState
                  title="Шаблон не выбран"
                  description="Чтобы создать версию, сначала выберите или создайте шаблон."
                />
              ) : (
                <div className="space-y-4">
                  {/* Template context */}
                  {selectedPlaybook && !isNewTemplateMode && (
                    <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-3">
                      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Шаблон
                      </div>
                      <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                        {selectedPlaybook.title}
                      </div>
                      <div className="mt-0.5 font-mono text-[11px] text-[var(--text-muted)]">
                        {selectedPlaybook.code}
                      </div>
                    </div>
                  )}

                  {isNewTemplateMode && (
                    <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-3">
                      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Шаблон
                      </div>
                      <div className="mt-1 text-sm text-[var(--text-secondary)]">
                        Новый шаблон (будет создан автоматически)
                      </div>
                    </div>
                  )}

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      Название версии
                    </label>
                    <input
                      type="text"
                      className={inputClassName}
                      value={newVersionName}
                      onChange={(e) => setNewVersionName(e.target.value)}
                      disabled={isBusy}
                      placeholder="Например: Real Estate DD RU v1"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                      Номер версии
                    </label>
                    <input
                      type="text"
                      className={inputClassName}
                      value={newVersionSemver}
                      onChange={(e) => setNewVersionSemver(e.target.value)}
                      disabled={isBusy}
                      placeholder="0.1.0"
                    />
                  </div>

                  <div>
                    <div className="mb-1 flex items-center justify-between">
                      <label className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                        Конфигурация модели
                      </label>
                      <button
                        type="button"
                        onClick={() => navigate(scopeConfig.modelConfigsPath)}
                        className="flex items-center gap-1 text-[10px] text-[var(--accent-primary)] transition-colors hover:text-[var(--text-primary)]"
                      >
                        <Settings className="h-3 w-3" />
                        Настроить
                      </button>
                    </div>
                    {modelConfigsQuery.isLoading ? (
                      <LoadingBlock text="Загружаем…" rows={2} />
                    ) : modelConfigs.length === 0 ? (
                      <div className="space-y-2">
                        <p className="text-xs text-[var(--text-muted)]">
                          Конфигурации моделей не найдены.
                        </p>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => navigate(scopeConfig.modelConfigsPath)}
                          leftIcon={<Settings className="h-3.5 w-3.5" />}
                        >
                          Создать конфигурацию
                        </Button>
                      </div>
                    ) : (
                      <select
                        className={selectClassName}
                        value={selectedModelConfigId}
                        onChange={(e) => setSelectedModelConfigId(e.target.value)}
                        disabled={isBusy}
                      >
                        {modelConfigs.map((config) => (
                          <option key={config.id} value={config.id}>
                            {config.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>

                  {/* Две кнопки */}
                  <div className="flex flex-col gap-2 border-t border-[var(--border-soft)] pt-3 sm:flex-row sm:items-center sm:justify-end">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void handleCreateVersion(false)}
                      disabled={isBusy || !selectedModelConfigId}
                      isLoading={isCreatingVersion}
                    >
                      Сохранить черновик
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => void handleCreateVersion(true)}
                      disabled={isBusy || !selectedModelConfigId}
                      isLoading={isPublishingVersion}
                    >
                      Опубликовать
                    </Button>
                  </div>

                  {/* Список существующих версий */}
                  {visibleVersions.length > 0 && (
                    <div className="border-t border-[var(--border-soft)] pt-3">
                      <div className="mb-2 flex items-center gap-1.5">
                        <GitBranch
                          className="h-3.5 w-3.5 text-[var(--text-muted)]"
                          aria-hidden="true"
                        />
                        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                          Существующие версии
                        </span>
                      </div>

                      <ul className="space-y-1.5">
                        {visibleVersions.map((version) => (
                          <li
                            key={version.id}
                            className="flex items-center justify-between gap-2 rounded-xl border border-[var(--border-soft)] px-3 py-2.5 text-xs"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="truncate font-semibold text-[var(--text-primary)]">
                                  {version.name}
                                </span>
                                {version.semver && (
                                  <span className="shrink-0 font-mono text-[10px] text-[var(--text-muted)]">
                                    v{version.semver}
                                  </span>
                                )}
                              </div>
                            </div>
                            <VersionStatusBadge status={version.status} size="xs" />
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </SectionCard>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PlaybookStudioPage;



