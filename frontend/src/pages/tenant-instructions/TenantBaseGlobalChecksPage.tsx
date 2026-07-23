import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Shield } from "lucide-react";

import client from "../../api/client";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";

interface GlobalCheckInfo {
  id: string;
  name: string;
  description?: string | null;
  category?: string | null;
  group?: string | null;
  severity?: string | null;
  doc_types?: string[] | null;
}

const TenantBaseGlobalChecksPage: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");

  const checksQuery = useQuery({
    queryKey: ["tenant-base-global-checks"],
    queryFn: async () => {
      const res = await client.get<GlobalCheckInfo[]>("/api/v1/playbooks/checks");
      return res.data;
    },
  });

  const checks = checksQuery.data ?? [];

  const filteredChecks = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return checks;

    return checks.filter((item) => {
      return (
        item.id.toLowerCase().includes(q) ||
        item.name.toLowerCase().includes(q) ||
        (item.group?.toLowerCase().includes(q) ?? false) ||
        (item.category?.toLowerCase().includes(q) ?? false)
      );
    });
  }, [checks, search]);

  const groupedChecks = useMemo(() => {
    const groups = new Map<string, GlobalCheckInfo[]>();

    for (const item of filteredChecks) {
      const key = item.group || "Без группы";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(item);
    }

    return Array.from(groups.entries()).sort(([a], [b]) =>
      a.localeCompare(b),
    );
  }, [filteredChecks]);

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Tenant Admin", to: "/tenant-admin" },
            { label: "Инструкции", to: "/tenant-admin/instructions" },
            { label: "Base Global Checks" },
          ]}
          title="Base Global Checks"
          subtitle="Read-only каталог базовых глобальных проверок платформы. Используйте его как основу при работе с playbooks."
          rightSlot={
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void checksQuery.refetch()}
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate("/tenant-admin/instructions/playbook-versions")}
              >
                Playbook Versions
              </Button>
            </div>
          }
        />

        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-xs text-[var(--text-secondary)]">
          Рабочий поток: изучите базовые global checks, затем откройте{" "}
          <span className="font-semibold text-[var(--text-primary)]">
            Playbook Versions
          </span>
          , а затем примените выбранную версию в проекте через вкладку{" "}
          <span className="font-semibold text-[var(--text-primary)]">
            Playbook
          </span>.
        </div>

        <div className="flex items-center gap-2">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по коду, названию, группе, категории..."
            className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)]"
          />
        </div>

        <PageSection title="Каталог">
          {checksQuery.isLoading && (
            <LoadingBlock text="Загружаем базовые global checks..." rows={6} />
          )}

          {checksQuery.isError && (
            <InlineAlert
              tone="error"
              message="Не удалось загрузить базовые global checks."
            />
          )}

          {!checksQuery.isLoading && !checksQuery.isError && checks.length === 0 && (
            <EmptyState
              title="Global checks не найдены"
              description="Каталог базовых global checks пока недоступен."
            />
          )}

          {!checksQuery.isLoading && !checksQuery.isError && checks.length > 0 && filteredChecks.length === 0 && (
            <EmptyState
              title="Ничего не найдено"
              description="Попробуйте изменить поисковый запрос."
            />
          )}

          {!checksQuery.isLoading && !checksQuery.isError && filteredChecks.length > 0 && (
            <div className="space-y-6">
              {groupedChecks.map(([groupName, items]) => (
                <div key={groupName}>
                  <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    {groupName} ({items.length})
                  </div>
                  <ul className="space-y-1.5">
                    {items.map((item) => (
                      <li key={item.id}>
                        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-xs">
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                              <Shield
                                className="h-4 w-4 text-[var(--accent-primary)]"
                                aria-hidden="true"
                              />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-semibold text-[var(--text-primary)]">
                                  {item.name}
                                </span>
                                {item.severity && (
                                  <span className="rounded border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                                    {item.severity}
                                  </span>
                                )}
                              </div>
                              <div className="mt-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                                {item.id}
                              </div>
                              {item.description && (
                                <div className="mt-1 text-[11px] text-[var(--text-secondary)]">
                                  {item.description}
                                </div>
                              )}
                              <div className="mt-1.5 flex flex-wrap gap-2 text-[10px] text-[var(--text-muted)]">
                                {item.category && <span>category: {item.category}</span>}
                                {item.doc_types && item.doc_types.length > 0 && (
                                  <span>doc types: {item.doc_types.join(", ")}</span>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </PageSection>
      </div>
    </div>
  );
};

export default TenantBaseGlobalChecksPage;



