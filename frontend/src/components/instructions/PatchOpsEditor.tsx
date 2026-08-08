// src/components/instructions/PatchOpsEditor.tsx

import React, { useCallback, useEffect, useState } from "react";
import type { JsonPatchOperation } from "../../types/instructions";
import InlineAlert from "../InlineAlert";

interface PatchOpsEditorProps {
  value: JsonPatchOperation[];
  onChange: (ops: JsonPatchOperation[]) => void;
  disabled?: boolean;
  label?: string;
}

const textareaClassName =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 py-2 text-xs font-mono text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)] disabled:cursor-not-allowed disabled:opacity-60 resize-y";

const PatchOpsEditor: React.FC<PatchOpsEditorProps> = ({
  value,
  onChange,
  disabled = false,
  label = "Patch Operations (JSON Patch RFC 6902)",
}) => {
  const [raw, setRaw] = useState(() =>
    JSON.stringify(value, null, 2),
  );
  const [parseError, setParseError] = useState<string | null>(null);

  useEffect(() => {
    setRaw(JSON.stringify(value, null, 2));
  }, [value]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const text = e.target.value;
      setRaw(text);
      setParseError(null);

      try {
        const parsed = JSON.parse(text) as unknown;
        if (!Array.isArray(parsed)) {
          setParseError("Ожидается JSON массив операций [ {...}, ... ]");
          return;
        }
        onChange(parsed as JsonPatchOperation[]);
      } catch {
        setParseError("Некорректный JSON. Проверьте синтаксис.");
      }
    },
    [onChange],
  );

  return (
    <div className="space-y-2">
      <label className="block text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        {label}
      </label>

      {/* Quick reference */}
      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-2">
        <div className="text-[10px] text-[var(--text-muted)]">
          Примеры операций:
        </div>
        <pre className="mt-1 text-[10px] font-mono text-[var(--text-secondary)] leading-relaxed">{`[
  { "op": "replace", "path": "/severity", "value": "high" },
  { "op": "add", "path": "/checks/-", "value": { "id": "..." } },
  { "op": "remove", "path": "/checks/0" }
]`}</pre>
      </div>

      <textarea
        value={raw}
        onChange={handleChange}
        disabled={disabled}
        className={textareaClassName}
        rows={10}
        spellCheck={false}
        placeholder={`[\n  { "op": "replace", "path": "/key", "value": "new_value" }\n]`}
      />

      <InlineAlert tone="error" message={parseError} />

      <div className="text-[10px] text-[var(--text-muted)]">
        Текущих операций: {value.length}
      </div>
    </div>
  );
};

export default PatchOpsEditor;


