// frontend/src/components/admin/ExternalToolsBar.tsx

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ExternalLink, Wrench } from "lucide-react";
import { useExternalTools } from "../../api/alerts";

/**
 * Dropdown "Внешние инструменты метрик и логирования".
 *
 * Показывается только superadmin. Внутри:
 *   - секция Grafana Dashboards (deep links на конкретные дашборды)
 *   - секция Сервисы (Grafana, Prometheus, Alertmanager, MinIO, ...)
 *
 * Обоснование role check:
 * Grafana / Prometheus показывают cross-tenant данные. Tenant_admin
 * не должен иметь прямого доступа — он получает tenant-scoped данные
 * через ваш UI (Monitoring / Logs / Alerts вкладки).
 */
export function ExternalToolsBar() {
  const { data, isLoading } = useExternalTools();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Закрывать dropdown при клике вне него
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(target) &&
        buttonRef.current &&
        !buttonRef.current.contains(target)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  // Закрывать dropdown при Escape
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };

    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen]);

  if (isLoading || !data) return null;
  if (!data.is_superadmin) return null;

  const hasDashboards = data.dashboards.length > 0;
  const hasServices = data.services.length > 0;

  if (!hasDashboards && !hasServices) return null;

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition hover:bg-[var(--bg-elevated-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
        aria-expanded={isOpen}
        aria-haspopup="menu"
      >
        <Wrench size={12} />
        <span className="hidden sm:inline">
          Внешние инструменты метрик и логирования
        </span>
        <span className="sm:hidden">Инструменты</span>
        <ChevronDown
          size={12}
          className={`transition-transform ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {isOpen && (
        <div
          ref={dropdownRef}
          role="menu"
          className="absolute right-0 top-full z-50 mt-2 w-80 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] shadow-lg"
        >
          {hasDashboards && (
            <div className="px-3 py-2">
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                📊 Grafana Dashboards
              </p>
              <div className="space-y-0.5">
                {data.dashboards.map((d) => (
                  <a
                    key={d.uid}
                    href={d.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setIsOpen(false)}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-xs transition hover:bg-[var(--bg-elevated-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
                    role="menuitem"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-[var(--text-primary)]">
                        {d.label}
                      </p>
                      <p className="truncate text-[10px] text-[var(--text-muted)]">
                        {d.description}
                      </p>
                    </div>
                    <ExternalLink
                      size={11}
                      className="shrink-0 text-[var(--text-muted)]"
                    />
                  </a>
                ))}
              </div>
            </div>
          )}

          {hasDashboards && hasServices && (
            <div className="border-t border-[var(--border-subtle)]" />
          )}

          {hasServices && (
            <div className="px-3 py-2">
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                🛠 Сервисы
              </p>
              <div className="space-y-0.5">
                {data.services.map((s) => (
                  <a
                    key={s.key}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setIsOpen(false)}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-xs transition hover:bg-[var(--bg-elevated-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
                    role="menuitem"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-[var(--text-primary)]">
                        {s.label}
                      </p>
                      <p className="truncate text-[10px] text-[var(--text-muted)]">
                        {s.description}
                      </p>
                    </div>
                    <ExternalLink
                      size={11}
                      className="shrink-0 text-[var(--text-muted)]"
                    />
                  </a>
                ))}
              </div>
            </div>
          )}

          <div className="border-t border-[var(--border-subtle)] px-3 py-2">
            <p className="text-[10px] text-[var(--text-muted)]">
              Виден только суперадмину · открывается в новой вкладке
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default ExternalToolsBar;


