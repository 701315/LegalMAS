// src/components/instructions/GlobalInstructionEditor.tsx
//
// Визуальный редактор для global instruction.
// Редактирует structured state → генерирует source_yaml.
//
// Архитектура:
// - Принимает sourceYaml: string, вызывает onChange(newYaml)
// - Внутри: parse YAML → EditorState → секции с полями
// - При каждом изменении поля — сериализует обратно в YAML
// - Секции сгруппированы в внутренние tabs (Basic / Detection / LLM / Retrieval / Extraction / Evidence)
//
// Важный инвариант:
// - Нельзя вызывать onChange() внутри setState-updater или прямо во время render.
//   Иначе React выдаёт warning:
//   "Cannot update a component while rendering a different component".
// - Поэтому локальный state меняется отдельно, а сериализация и onChange(newYaml)
//   выполняются в useEffect после commit.
//
// Зависимости: js-yaml (должен быть в проекте вместе с @types/js-yaml)

import React, { useCallback, useEffect, useRef, useState } from "react";
import * as jsyaml from "js-yaml";
import { AlertCircle, Plus, Trash2 } from "lucide-react";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../ui/Tabs";
import Field from "../ui/Field";
import Button from "../ui/Button";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

interface ExtractionField {
  name: string;
  type: string;
  presentation: string;
  label: string;
  description: string;
  allowed_values: string[];
}

interface EditorState {
  // Basic
  id: string;
  name: string;
  group: string;
  description: string;
  doc_types: string[];
  severity: string;
  severity_if_fail: string;
  severity_if_pass: string;
  severity_if_unclear: string;
  ui_mode: string;

  // Detection
  detector_type: string;
  keyword_mode: string;
  keywords_high: string[];
  keywords_medium: string[];
  keywords_low: string[];
  regex_patterns: string[];

  // LLM
  llm_prompt_file: string;
  llm_context_k: number;
  llm_temperature: number;
  llm_max_tokens: number;

  // Retrieval
  retrieval_context_k: number;
  retrieval_max_chunks: number;
  retrieval_query: string;
  boost_keywords: string[];
  negative_keywords: string[];
  preferred_unit_types: string[];
  excluded_unit_types: string[];
  preferred_clause_functions: string[];
  rerank: boolean;

  // Evidence
  evidence_required: boolean;
  evidence_min_snippet_length: number;
  evidence_max_snippet_length: number;

  // Extraction
  extraction_enabled: boolean;
  extraction_mode: string;
  extraction_llm_max_tokens: number;
  extraction_prompt: string;
  extraction_fields: ExtractionField[];
  extraction_store_payload: boolean;
}

// ─────────────────────────────────────────────────────────────
// YAML parse / serialize
// ─────────────────────────────────────────────────────────────

function parseYamlToState(yaml: string): EditorState | null {
  try {
    const doc = jsyaml.load(yaml) as Record<string, unknown>;
    if (!doc || typeof doc !== "object") return null;

    const rules = (doc.rules as Record<string, unknown>) ?? {};
    const kwRaw = (rules.keywords as Record<string, unknown>) ?? {};
    const llm = (doc.llm as Record<string, unknown>) ?? {};
    const retrieval = (doc.retrieval as Record<string, unknown>) ?? {};
    const evidence = (doc.evidence as Record<string, unknown>) ?? {};
    const extraction = (doc.extraction as Record<string, unknown>) ?? {};

    const toStringArray = (v: unknown): string[] => {
      if (!Array.isArray(v)) return [];
      return v.map(String);
    };

    const rawFields = Array.isArray(extraction.fields)
      ? (extraction.fields as Record<string, unknown>[])
      : [];

    return {
      // Basic
      id: String(doc.id ?? ""),
      name: String(doc.name ?? ""),
      group: String(doc.group ?? ""),
      description: String(doc.description ?? ""),
      doc_types: toStringArray(doc.doc_types),
      severity: String(doc.severity ?? "medium"),
      severity_if_fail: String(doc.severity_if_fail ?? ""),
      severity_if_pass: String(doc.severity_if_pass ?? ""),
      severity_if_unclear: String(doc.severity_if_unclear ?? ""),
      ui_mode: String(doc.ui_mode ?? ""),

      // Detection
      detector_type: String(doc.detector_type ?? "hybrid"),
      keyword_mode: String(rules.keyword_mode ?? "any"),
      keywords_high: toStringArray(kwRaw.high),
      keywords_medium: toStringArray(kwRaw.medium),
      keywords_low: toStringArray(kwRaw.low),
      regex_patterns: toStringArray(rules.regex_patterns),

      // LLM
      llm_prompt_file: String(llm.prompt_file ?? ""),
      llm_context_k: Number(llm.context_k ?? 5),
      llm_temperature: Number(llm.temperature ?? 0.0),
      llm_max_tokens: Number(llm.max_tokens ?? 700),

      // Retrieval
      retrieval_context_k: Number(retrieval.context_k ?? 6),
      retrieval_max_chunks: Number(retrieval.max_chunks ?? 10),
      retrieval_query: String(retrieval.retrieval_query ?? ""),
      boost_keywords: toStringArray(retrieval.boost_keywords),
      negative_keywords: toStringArray(retrieval.negative_keywords),
      preferred_unit_types: toStringArray(retrieval.preferred_unit_types),
      excluded_unit_types: toStringArray(retrieval.excluded_unit_types),
      preferred_clause_functions: toStringArray(
        retrieval.preferred_clause_functions,
      ),
      rerank: Boolean(retrieval.rerank ?? true),

      // Evidence
      evidence_required: Boolean(evidence.required ?? true),
      evidence_min_snippet_length: Number(evidence.min_snippet_length ?? 20),
      evidence_max_snippet_length: Number(evidence.max_snippet_length ?? 600),

      // Extraction
      extraction_enabled: Boolean(extraction.enabled ?? false),
      extraction_mode: String(extraction.mode ?? "hybrid"),
      extraction_llm_max_tokens: Number(extraction.llm_max_tokens ?? 380),
      extraction_prompt: String(extraction.llm_prompt_extraction ?? ""),
      extraction_fields: rawFields.map((f) => ({
        name: String(f.name ?? ""),
        type: String(f.type ?? "string"),
        presentation: String(f.presentation ?? "fact"),
        label: String(f.label ?? ""),
        description: String(f.description ?? ""),
        allowed_values: toStringArray(f.allowed_values),
      })),
      extraction_store_payload: Boolean(extraction.store_payload ?? false),
    };
  } catch {
    return null;
  }
}

function serializeStateToYaml(state: EditorState): string {
  const hasKeywords =
    state.keywords_high.length > 0 ||
    state.keywords_medium.length > 0 ||
    state.keywords_low.length > 0;

  const doc: Record<string, unknown> = {
    id: state.id,
    name: state.name,
    group: state.group || undefined,
    description: state.description || undefined,
    doc_types: state.doc_types,
    severity: state.severity,
    ...(state.severity_if_fail && { severity_if_fail: state.severity_if_fail }),
    ...(state.severity_if_pass && { severity_if_pass: state.severity_if_pass }),
    ...(state.severity_if_unclear && {
      severity_if_unclear: state.severity_if_unclear,
    }),
    ...(state.ui_mode && { ui_mode: state.ui_mode }),

    detector_type: state.detector_type,

    ...(hasKeywords || state.regex_patterns.length > 0
      ? {
          rules: {
            keyword_mode: state.keyword_mode,
            ...(hasKeywords && {
              keywords: {
                ...(state.keywords_high.length > 0 && {
                  high: state.keywords_high,
                }),
                ...(state.keywords_medium.length > 0 && {
                  medium: state.keywords_medium,
                }),
                ...(state.keywords_low.length > 0 && { low: state.keywords_low }),
              },
            }),
            ...(state.regex_patterns.length > 0 && {
              regex_patterns: state.regex_patterns,
            }),
          },
        }
      : {}),

    llm: {
      prompt_file: state.llm_prompt_file || undefined,
      context_k: state.llm_context_k,
      temperature: state.llm_temperature,
      max_tokens: state.llm_max_tokens,
    },

    evidence: {
      required: state.evidence_required,
      min_snippet_length: state.evidence_min_snippet_length,
      max_snippet_length: state.evidence_max_snippet_length,
    },

    retrieval: {
      context_k: state.retrieval_context_k,
      max_chunks: state.retrieval_max_chunks,
      ...(state.retrieval_query && { retrieval_query: state.retrieval_query }),
      ...(state.boost_keywords.length > 0 && {
        boost_keywords: state.boost_keywords,
      }),
      ...(state.negative_keywords.length > 0 && {
        negative_keywords: state.negative_keywords,
      }),
      ...(state.preferred_unit_types.length > 0 && {
        preferred_unit_types: state.preferred_unit_types,
      }),
      ...(state.excluded_unit_types.length > 0 && {
        excluded_unit_types: state.excluded_unit_types,
      }),
      ...(state.preferred_clause_functions.length > 0 && {
        preferred_clause_functions: state.preferred_clause_functions,
      }),
      rerank: state.rerank,
    },

    ...(state.extraction_enabled && {
      extraction: {
        enabled: true,
        mode: state.extraction_mode,
        llm_max_tokens: state.extraction_llm_max_tokens,
        ...(state.extraction_prompt && {
          llm_prompt_extraction: state.extraction_prompt,
        }),
        fields: state.extraction_fields.map((f) => ({
          name: f.name,
          type: f.type,
          presentation: f.presentation,
          ...(f.label && { label: f.label }),
          ...(f.description && { description: f.description }),
          ...(f.allowed_values.length > 0 && {
            allowed_values: f.allowed_values,
          }),
        })),
        store_payload: state.extraction_store_payload,
      },
    }),
  };

  return jsyaml.dump(doc, {
    indent: 2,
    lineWidth: 120,
    noRefs: true,
  });
}

// ─────────────────────────────────────────────────────────────
// Shared input styles
// ─────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] disabled:opacity-60";

const textareaCls =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs font-mono text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] resize-y disabled:opacity-60";

const selectCls =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)]";

// ─────────────────────────────────────────────────────────────
// Reusable sub-components
// ─────────────────────────────────────────────────────────────

/** Редактируемый список строк (keywords, boost_keywords, etc.) */
interface StringListEditorProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  hint?: string;
  mono?: boolean;
}

const StringListEditor: React.FC<StringListEditorProps> = ({
  label,
  values,
  onChange,
  placeholder = "Добавить...",
  hint,
  mono = false,
}) => {
  const [draft, setDraft] = useState("");

  const handleAdd = useCallback(() => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    onChange([...values, trimmed]);
    setDraft("");
  }, [draft, onChange, values]);

  const handleRemove = useCallback(
    (idx: number) => {
      onChange(values.filter((_, i) => i !== idx));
    },
    [onChange, values],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleAdd();
      }
    },
    [handleAdd],
  );

  return (
    <Field label={label} hint={hint}>
      <div className="space-y-2">
        {values.length > 0 && (
          <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--bg-base)] p-2">
            {values.map((v, idx) => (
              <div
                key={idx}
                className="flex items-start gap-2 rounded px-2 py-1 hover:bg-[var(--bg-elevated-soft)]"
              >
                <span
                  className={[
                    "flex-1 break-all text-xs text-[var(--text-primary)]",
                    mono ? "font-mono" : "",
                  ].join(" ")}
                >
                  {v}
                </span>
                <button
                  type="button"
                  onClick={() => handleRemove(idx)}
                  className="shrink-0 text-[var(--text-muted)] hover:text-[var(--color-error)]"
                  aria-label={`Удалить: ${v}`}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            className={[inputCls, mono ? "font-mono" : "", "flex-1"].join(" ")}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleAdd}
            leftIcon={<Plus />}
          >
            Добавить
          </Button>
        </div>
      </div>
    </Field>
  );
};

/** Секция-заголовок внутри редактора */
const SectionTitle: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => (
  <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
    {children}
  </h3>
);

/** Сетка полей 2 колонки */
const FieldGrid: React.FC<{
  children: React.ReactNode;
  cols?: 1 | 2 | 3;
}> = ({ children, cols = 2 }) => {
  const colClass =
    cols === 1 ? "" : cols === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2";
  return (
    <div className={["grid grid-cols-1 gap-3", colClass].join(" ")}>
      {children}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Section components
// ─────────────────────────────────────────────────────────────

interface SectionProps {
  state: EditorState;
  onChange: (patch: Partial<EditorState>) => void;
}

const BasicSection: React.FC<SectionProps> = ({ state, onChange }) => (
  <div className="space-y-4">
    <SectionTitle>Идентификация</SectionTitle>
    <FieldGrid>
      <Field label="ID инструкции" required>
        <input
          type="text"
          value={state.id}
          onChange={(e) => onChange({ id: e.target.value })}
          className={inputCls}
          placeholder="confidentiality_and_trade_secrets"
        />
      </Field>
      <Field label="Группа (group)">
        <input
          type="text"
          value={state.group}
          onChange={(e) => onChange({ group: e.target.value })}
          className={inputCls}
          placeholder="Confidentiality"
        />
      </Field>
    </FieldGrid>

    <Field label="Название" required>
      <input
        type="text"
        value={state.name}
        onChange={(e) => onChange({ name: e.target.value })}
        className={inputCls}
        placeholder="Конфиденциальность и коммерческая тайна"
      />
    </Field>

    <Field
      label="Описание"
      hint="Подробное описание того, что проверяет инструкция"
    >
      <textarea
        value={state.description}
        onChange={(e) => onChange({ description: e.target.value })}
        className={textareaCls}
        rows={4}
        placeholder="Screening-check: определяет наличие режима конфиденциальности..."
      />
    </Field>

    <SectionTitle>Применимость</SectionTitle>
    <StringListEditor
      label="Типы документов (doc_types)"
      values={state.doc_types}
      onChange={(v) => onChange({ doc_types: v })}
      placeholder="contract_nda, contract_spa..."
      hint="Оставьте пустым — применяется ко всем типам"
    />

    <SectionTitle>Severity</SectionTitle>
    <FieldGrid cols={2}>
      <Field label="Базовый severity">
        <select
          value={state.severity}
          onChange={(e) => onChange({ severity: e.target.value })}
          className={selectCls}
        >
          {["critical", "high", "medium", "low", "info"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </Field>
      <Field label="UI режим">
        <select
          value={state.ui_mode}
          onChange={(e) => onChange({ ui_mode: e.target.value })}
          className={selectCls}
        >
          <option value="">— не задан —</option>
          <option value="field_extraction">field_extraction</option>
          <option value="clause_presence">clause_presence</option>
          <option value="risk_detection">risk_detection</option>
        </select>
      </Field>
    </FieldGrid>

    <FieldGrid cols={3}>
      <Field label="severity_if_fail" hint="Severity при fail">
        <select
          value={state.severity_if_fail}
          onChange={(e) => onChange({ severity_if_fail: e.target.value })}
          className={selectCls}
        >
          <option value="">— наследует базовый —</option>
          {["critical", "high", "medium", "low", "info", "pass"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </Field>
      <Field label="severity_if_pass" hint="Severity при pass">
        <select
          value={state.severity_if_pass}
          onChange={(e) => onChange({ severity_if_pass: e.target.value })}
          className={selectCls}
        >
          <option value="">— наследует базовый —</option>
          {["critical", "high", "medium", "low", "info", "pass"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </Field>
      <Field label="severity_if_unclear" hint="Severity при unclear">
        <select
          value={state.severity_if_unclear}
          onChange={(e) => onChange({ severity_if_unclear: e.target.value })}
          className={selectCls}
        >
          <option value="">— наследует базовый —</option>
          {["critical", "high", "medium", "low", "info", "pass"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </Field>
    </FieldGrid>
  </div>
);

const DetectionSection: React.FC<SectionProps> = ({ state, onChange }) => (
  <div className="space-y-4">
    <SectionTitle>Детектор</SectionTitle>
    <FieldGrid>
      <Field label="Тип детектора">
        <select
          value={state.detector_type}
          onChange={(e) => onChange({ detector_type: e.target.value })}
          className={selectCls}
        >
          <option value="hybrid">hybrid</option>
          <option value="rules">rules</option>
          <option value="llm">llm</option>
        </select>
      </Field>
      <Field label="Режим keywords">
        <select
          value={state.keyword_mode}
          onChange={(e) => onChange({ keyword_mode: e.target.value })}
          className={selectCls}
        >
          <option value="any">any</option>
          <option value="all">all</option>
        </select>
      </Field>
    </FieldGrid>

    <SectionTitle>Keywords</SectionTitle>

    <StringListEditor
      label="High priority keywords"
      values={state.keywords_high}
      onChange={(v) => onChange({ keywords_high: v })}
      placeholder="(?i)confidential\\s+information"
      hint="Regex паттерны с высоким приоритетом"
      mono
    />

    <StringListEditor
      label="Medium priority keywords"
      values={state.keywords_medium}
      onChange={(v) => onChange({ keywords_medium: v })}
      placeholder="(?i)confidentiality\\s+period"
      mono
    />

    <StringListEditor
      label="Low priority keywords"
      values={state.keywords_low}
      onChange={(v) => onChange({ keywords_low: v })}
      placeholder="(?i)confidential"
      mono
    />

    <SectionTitle>Regex patterns</SectionTitle>
    <StringListEditor
      label="Regex patterns"
      values={state.regex_patterns}
      onChange={(v) => onChange({ regex_patterns: v })}
      placeholder="(?i)pattern..."
      mono
    />
  </div>
);

const LlmSection: React.FC<SectionProps> = ({ state, onChange }) => (
  <div className="space-y-4">
    <SectionTitle>LLM конфигурация</SectionTitle>
    <Field
      label="Prompt file"
      hint="Путь к файлу промпта относительно playbooks/"
    >
      <input
        type="text"
        value={state.llm_prompt_file}
        onChange={(e) => onChange({ llm_prompt_file: e.target.value })}
        className={inputCls}
        placeholder="detection/generic_presence.txt"
      />
    </Field>

    <FieldGrid cols={3}>
      <Field label="Context K" hint="Кол-во чанков контекста">
        <input
          type="number"
          value={state.llm_context_k}
          min={1}
          max={20}
          onChange={(e) => onChange({ llm_context_k: Number(e.target.value) })}
          className={inputCls}
        />
      </Field>
      <Field label="Temperature">
        <input
          type="number"
          value={state.llm_temperature}
          min={0}
          max={2}
          step={0.1}
          onChange={(e) =>
            onChange({ llm_temperature: Number(e.target.value) })
          }
          className={inputCls}
        />
      </Field>
      <Field label="Max tokens">
        <input
          type="number"
          value={state.llm_max_tokens}
          min={100}
          max={4000}
          step={50}
          onChange={(e) => onChange({ llm_max_tokens: Number(e.target.value) })}
          className={inputCls}
        />
      </Field>
    </FieldGrid>
  </div>
);

const RetrievalSection: React.FC<SectionProps> = ({ state, onChange }) => (
  <div className="space-y-4">
    <SectionTitle>Параметры retrieval</SectionTitle>
    <FieldGrid>
      <Field label="Context K" hint="Кол-во релевантных чанков">
        <input
          type="number"
          value={state.retrieval_context_k}
          min={1}
          max={20}
          onChange={(e) =>
            onChange({ retrieval_context_k: Number(e.target.value) })
          }
          className={inputCls}
        />
      </Field>
      <Field label="Max chunks">
        <input
          type="number"
          value={state.retrieval_max_chunks}
          min={1}
          max={50}
          onChange={(e) =>
            onChange({ retrieval_max_chunks: Number(e.target.value) })
          }
          className={inputCls}
        />
      </Field>
    </FieldGrid>

    <Field
      label="Retrieval query"
      hint="Семантический запрос для поиска релевантных фрагментов"
    >
      <textarea
        value={state.retrieval_query}
        onChange={(e) => onChange({ retrieval_query: e.target.value })}
        className={textareaCls}
        rows={3}
        placeholder="конфиденциальная информация NDA..."
      />
    </Field>

    <Field label="Rerank">
      <label className="inline-flex cursor-pointer items-center gap-2">
        <input
          type="checkbox"
          checked={state.rerank}
          onChange={(e) => onChange({ rerank: e.target.checked })}
          className="h-3.5 w-3.5 rounded border-[var(--border)] accent-[var(--accent-primary)]"
        />
        <span className="text-xs text-[var(--text-secondary)]">
          Включить reranking результатов
        </span>
      </label>
    </Field>

    <SectionTitle>Boost / Negative keywords</SectionTitle>
    <StringListEditor
      label="Boost keywords"
      values={state.boost_keywords}
      onChange={(v) => onChange({ boost_keywords: v })}
      placeholder="конфиденциальная информация"
      hint="Повышают релевантность чанков"
    />
    <StringListEditor
      label="Negative keywords"
      values={state.negative_keywords}
      onChange={(v) => onChange({ negative_keywords: v })}
      placeholder="означает"
      hint="Снижают релевантность чанков"
    />

    <SectionTitle>Фильтры по типам</SectionTitle>
    <FieldGrid>
      <StringListEditor
        label="Preferred unit types"
        values={state.preferred_unit_types}
        onChange={(v) => onChange({ preferred_unit_types: v })}
        placeholder="confidentiality"
      />
      <StringListEditor
        label="Excluded unit types"
        values={state.excluded_unit_types}
        onChange={(v) => onChange({ excluded_unit_types: v })}
        placeholder="definition"
      />
    </FieldGrid>
    <StringListEditor
      label="Preferred clause functions"
      values={state.preferred_clause_functions}
      onChange={(v) => onChange({ preferred_clause_functions: v })}
      placeholder="obligations"
    />
  </div>
);

const EvidenceSection: React.FC<SectionProps> = ({ state, onChange }) => (
  <div className="space-y-4">
    <SectionTitle>Evidence настройки</SectionTitle>

    <Field label="Required">
      <label className="inline-flex cursor-pointer items-center gap-2">
        <input
          type="checkbox"
          checked={state.evidence_required}
          onChange={(e) => onChange({ evidence_required: e.target.checked })}
          className="h-3.5 w-3.5 rounded border-[var(--border)] accent-[var(--accent-primary)]"
        />
        <span className="text-xs text-[var(--text-secondary)]">
          Evidence обязательна для вывода результата
        </span>
      </label>
    </Field>

    <FieldGrid>
      <Field
        label="Min snippet length"
        hint="Минимальная длина фрагмента (символы)"
      >
        <input
          type="number"
          value={state.evidence_min_snippet_length}
          min={5}
          max={500}
          onChange={(e) =>
            onChange({ evidence_min_snippet_length: Number(e.target.value) })
          }
          className={inputCls}
        />
      </Field>
      <Field
        label="Max snippet length"
        hint="Максимальная длина фрагмента (символы)"
      >
        <input
          type="number"
          value={state.evidence_max_snippet_length}
          min={50}
          max={2000}
          onChange={(e) =>
            onChange({ evidence_max_snippet_length: Number(e.target.value) })
          }
          className={inputCls}
        />
      </Field>
    </FieldGrid>
  </div>
);

// ── Extraction section ─────────────────────────────────────────

const FIELD_TYPES = ["string", "number", "boolean", "date", "array"];
const PRESENTATIONS = ["fact", "signal", "diagnostic"];

const ExtractionFieldEditor: React.FC<{
  field: ExtractionField;
  index: number;
  onChange: (patch: Partial<ExtractionField>) => void;
  onRemove: () => void;
}> = ({ field, index, onChange, onRemove }) => (
  <div className="space-y-3 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-3">
    <div className="flex items-center justify-between">
      <span className="text-[11px] font-semibold text-[var(--text-muted)]">
        Поле #{index + 1}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="text-[var(--text-muted)] hover:text-[var(--color-error)]"
        aria-label="Удалить поле"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>

    <FieldGrid>
      <Field label="name" required>
        <input
          type="text"
          value={field.name}
          onChange={(e) => onChange({ name: e.target.value })}
          className={inputCls}
          placeholder="confidentiality_status"
        />
      </Field>
      <Field label="label">
        <input
          type="text"
          value={field.label}
          onChange={(e) => onChange({ label: e.target.value })}
          className={inputCls}
          placeholder="Статус конфиденциальности"
        />
      </Field>
    </FieldGrid>

    <FieldGrid>
      <Field label="type">
        <select
          value={field.type}
          onChange={(e) => onChange({ type: e.target.value })}
          className={selectCls}
        >
          {FIELD_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </Field>
      <Field label="presentation">
        <select
          value={field.presentation}
          onChange={(e) => onChange({ presentation: e.target.value })}
          className={selectCls}
        >
          {PRESENTATIONS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </Field>
    </FieldGrid>

    <Field label="description">
      <input
        type="text"
        value={field.description}
        onChange={(e) => onChange({ description: e.target.value })}
        className={inputCls}
        placeholder="Краткое описание поля"
      />
    </Field>

    <StringListEditor
      label="allowed_values"
      values={field.allowed_values}
      onChange={(v) => onChange({ allowed_values: v })}
      placeholder="present"
      hint="Оставьте пустым если значения произвольные"
    />
  </div>
);

const ExtractionSection: React.FC<SectionProps> = ({ state, onChange }) => {
  const handleFieldChange = useCallback(
    (idx: number, patch: Partial<ExtractionField>) => {
      const updated = state.extraction_fields.map((f, i) =>
        i === idx ? { ...f, ...patch } : f,
      );
      onChange({ extraction_fields: updated });
    },
    [onChange, state.extraction_fields],
  );

  const handleFieldRemove = useCallback(
    (idx: number) => {
      onChange({
        extraction_fields: state.extraction_fields.filter((_, i) => i !== idx),
      });
    },
    [onChange, state.extraction_fields],
  );

  const handleAddField = useCallback(() => {
    onChange({
      extraction_fields: [
        ...state.extraction_fields,
        {
          name: "",
          type: "string",
          presentation: "fact",
          label: "",
          description: "",
          allowed_values: [],
        },
      ],
    });
  }, [onChange, state.extraction_fields]);

  return (
    <div className="space-y-4">
      <SectionTitle>Extraction</SectionTitle>

      <Field label="Включить extraction">
        <label className="inline-flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={state.extraction_enabled}
            onChange={(e) => onChange({ extraction_enabled: e.target.checked })}
            className="h-3.5 w-3.5 rounded border-[var(--border)] accent-[var(--accent-primary)]"
          />
          <span className="text-xs text-[var(--text-secondary)]">Enabled</span>
        </label>
      </Field>

      {state.extraction_enabled && (
        <>
          <FieldGrid>
            <Field label="Режим extraction">
              <select
                value={state.extraction_mode}
                onChange={(e) => onChange({ extraction_mode: e.target.value })}
                className={selectCls}
              >
                <option value="hybrid">hybrid</option>
                <option value="llm">llm</option>
                <option value="rules">rules</option>
              </select>
            </Field>
            <Field label="LLM max tokens">
              <input
                type="number"
                value={state.extraction_llm_max_tokens}
                min={100}
                max={4000}
                step={50}
                onChange={(e) =>
                  onChange({ extraction_llm_max_tokens: Number(e.target.value) })
                }
                className={inputCls}
              />
            </Field>
          </FieldGrid>

          <Field label="Store payload">
            <label className="inline-flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={state.extraction_store_payload}
                onChange={(e) =>
                  onChange({ extraction_store_payload: e.target.checked })
                }
                className="h-3.5 w-3.5 rounded border-[var(--border)] accent-[var(--accent-primary)]"
              />
              <span className="text-xs text-[var(--text-secondary)]">
                Сохранять extraction payload в результате
              </span>
            </label>
          </Field>

          <Field
            label="LLM prompt (extraction)"
            hint="Промпт для LLM extraction. Используйте {context} как placeholder"
          >
            <textarea
              value={state.extraction_prompt}
              onChange={(e) => onChange({ extraction_prompt: e.target.value })}
              className={textareaCls}
              rows={10}
              placeholder="<role>&#10;Ты — юрист...&#10;</role>&#10;&#10;<context>&#10;{context}&#10;</context>"
              spellCheck={false}
            />
          </Field>

          <SectionTitle>Поля extraction</SectionTitle>

          <div className="space-y-3">
            {state.extraction_fields.map((f, idx) => (
              <ExtractionFieldEditor
                key={idx}
                field={f}
                index={idx}
                onChange={(patch) => handleFieldChange(idx, patch)}
                onRemove={() => handleFieldRemove(idx)}
              />
            ))}
          </div>

          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleAddField}
            leftIcon={<Plus />}
          >
            Добавить поле
          </Button>
        </>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────

interface GlobalInstructionEditorProps {
  sourceYaml: string;
  onChange: (newYaml: string) => void;
  disabled?: boolean;
}

export const GlobalInstructionEditor: React.FC<GlobalInstructionEditorProps> = ({
  sourceYaml,
  onChange,
  disabled = false,
}) => {
  const [section, setSection] = useState("basic");
  const [parseError, setParseError] = useState<string | null>(null);

  // Parse YAML → state при монтировании
  const [state, setState] = useState<EditorState | null>(() =>
    parseYamlToState(sourceYaml),
  );

  // Храним последнее YAML-значение, которое:
  // - либо пришло снаружи через props
  // - либо было отправлено наружу через onChange
  //
  // Это позволяет:
  // - не зациклиться между editor state ↔ parent sourceYaml
  // - не эмитить onChange повторно для того же самого YAML
  const lastYamlRef = useRef(sourceYaml);

  // При изменении sourceYaml снаружи (например переключение YAML→Editor
  // или приход новых данных после refetch) пересчитываем editor state.
  useEffect(() => {
    if (lastYamlRef.current === sourceYaml) return;

    lastYamlRef.current = sourceYaml;

    const parsed = parseYamlToState(sourceYaml);
    if (parsed) {
      setParseError(null);
      setState(parsed);
    } else {
      setParseError(
        "Не удалось разобрать YAML. Проверьте синтаксис на вкладке YAML.",
      );
    }
  }, [sourceYaml]);

  // Любое локальное изменение structured state сериализуем обратно в YAML
  // ПОСЛЕ render. Это важно: onChange нельзя вызывать внутри setState-updater.
  useEffect(() => {
    if (!state) return;

    try {
      const newYaml = serializeStateToYaml(state);

      if (newYaml === lastYamlRef.current) {
        return;
      }

      lastYamlRef.current = newYaml;
      onChange(newYaml);
    } catch {
      // Не блокируем UI если сериализация временно упала.
      // Пользователь может продолжить редактирование, а YAML вкладка
      // останется источником диагностики.
    }
  }, [state, onChange]);

  // Обновить одно или несколько полей editor state.
  // Без side effects: только меняем local state.
  const handleChange = useCallback((patch: Partial<EditorState>) => {
    setState((prev) => {
      if (!prev) return prev;
      return { ...prev, ...patch };
    });
  }, []);

  // Если YAML не парсится — показываем ошибку
  if (parseError || !state) {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-[var(--color-error)]/30 bg-[var(--color-error)]/8 p-4 text-xs text-[var(--color-error)]">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="space-y-1">
          <div className="font-semibold">Ошибка разбора YAML</div>
          <div className="text-[var(--text-secondary)]">
            {parseError ??
              "Не удалось инициализировать редактор. Переключитесь на вкладку YAML и проверьте синтаксис."}
          </div>
        </div>
      </div>
    );
  }

  const sectionProps: SectionProps = { state, onChange: handleChange };

  return (
    <div className={disabled ? "pointer-events-none opacity-60" : ""}>
      <Tabs value={section} onChange={setSection}>
        <TabsList aria-label="Секции редактора">
          <TabsTrigger value="basic">Basic</TabsTrigger>
          <TabsTrigger value="detection">Detection</TabsTrigger>
          <TabsTrigger value="llm">LLM</TabsTrigger>
          <TabsTrigger value="retrieval">Retrieval</TabsTrigger>
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
          <TabsTrigger value="extraction">Extraction</TabsTrigger>
        </TabsList>

        <TabsContent value="basic">
          <BasicSection {...sectionProps} />
        </TabsContent>

        <TabsContent value="detection">
          <DetectionSection {...sectionProps} />
        </TabsContent>

        <TabsContent value="llm">
          <LlmSection {...sectionProps} />
        </TabsContent>

        <TabsContent value="retrieval">
          <RetrievalSection {...sectionProps} />
        </TabsContent>

        <TabsContent value="evidence">
          <EvidenceSection {...sectionProps} />
        </TabsContent>

        <TabsContent value="extraction">
          <ExtractionSection {...sectionProps} />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default GlobalInstructionEditor;



