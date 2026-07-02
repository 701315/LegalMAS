// frontend/src/components/admin/ExternalToolsBar.tsx

import { ExternalLink } from "lucide-react";
import { useExternalTools } from "../../api/alerts";

/**
 * Панель кнопок для быстрого перехода в Grafana / Prometheus / Alertmanager.
 * Показывается только superadmin.
 */
export function ExternalToolsBar() {
  const { data, isLoading } = useExternalTools();

  if (isLoading || !data) return null;
  if (!data.is_superadmin) return null;

  const tools: Array<{ label: string; url: string; color: string }> = [
    {
      label: "Grafana",
      url: data.grafana_url,
      color:
        "bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100",
    },
    {
      label: "Prometheus",
      url: data.prometheus_url,
      color: "bg-red-50 border-red-200 text-red-700 hover:bg-red-100",
    },
    {
      label: "Alertmanager",
      url: data.alertmanager_url,
      color: "bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100",
    },
  ];

  return (
    <div className="flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2">
      <span className="mr-2 text-[11px] font-medium text-[var(--text-muted)]">
        Внешние инструменты:
      </span>
      {tools.map((t) => (
        <a
          key={t.label}
          href={t.url}
          target="_blank"
          rel="noopener noreferrer"
          className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition ${t.color}`}
        >
          {t.label}
          <ExternalLink size={12} />
        </a>
      ))}
    </div>
  );
}

export default ExternalToolsBar;



