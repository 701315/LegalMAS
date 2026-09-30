// =============================================================
// src/components/shared/ResultsLocaleSelector.tsx
// Controlled dropdown for choosing the results output locale.
//
// The value + onChange are owned by the caller. Persistence is
// typically handled by the caller (e.g. useDDGridV1UIStore's
// setOutputLocale writes to localStorage), so this component
// stays presentation-only and does not depend on any store.
//
// Extracted from DDGridV1ViewSettings to allow reuse on the
// Requests tab and any future result-bearing surface.
// =============================================================

import React from "react";
import { Globe } from "lucide-react";

import { getEnabledResultLocales } from "../../i18n/resultLocaleRegistry";

export interface ResultsLocaleSelectorProps {
  value: string;
  onChange: (locale: string) => void;
}

export const ResultsLocaleSelector: React.FC<
  ResultsLocaleSelectorProps
> = ({ value, onChange }) => {
  const resultLocales = getEnabledResultLocales();

  if (resultLocales.length === 0) {
    return null;
  }

  return (
    <div className="relative inline-flex items-center">
      <Globe
        className="absolute left-3.5 h-3.5 w-3.5 text-[var(--text-muted)] pointer-events-none"
        aria-hidden="true"
      />
      <select
        aria-label="Results Language"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-[170px] cursor-pointer rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] py-2 pl-9 pr-8 text-xs font-medium text-[var(--text-primary)] hover:border-[var(--border-strong)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        style={{
          appearance: "none",
          backgroundImage: `url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e")`,
          backgroundRepeat: "no-repeat",
          backgroundPosition: "right 10px center",
          backgroundSize: "14px",
        }}
      >
        {resultLocales.map((loc) => (
          <option key={loc.code} value={loc.code}>
            {loc.nativeName} ({loc.englishName})
          </option>
        ))}
      </select>
    </div>
  );
};

export default ResultsLocaleSelector;
