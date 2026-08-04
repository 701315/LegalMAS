// src/pages/instructions/GlobalPlaybookDetailPage.tsx
// Detail страница global playbook — список версий + переход к версии.

import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, GitBranch, RefreshCw } from "lucide-react";

import {
  useGlobalPlaybooks,
  useGlobalPlaybookVersions,
} from "../../hooks/instructions/useInstructionVersions";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";

const GlobalPlaybookDetailPage: React.FC = () => {
  const { playbookId } = useParams<{ playbookId: string }>();
  const navigate = useNavigate();

  const { data: playbooks, isLoading: isPlaybooksLoading } =
    useGlobalPlaybooks();
  const playbook = playbooks?.find((p) => p.id === playbookId) ?? null;

  const {
    data: versions,
    isLoading: isVersionsLoading,
    isError,
    refetch,
  } = useGlobalPlaybookVersions(playbookId ?? null);

  const handleOpenVersion = (versionId: string) => {
    navigate(
      `/admin/instructions/global-playbooks/${playbookId}/versions/${versionId}`,
    );
  };

  const isLoading = isPlaybooksLoading || isVersionsLoading;

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Шапка ───────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <button
                type="button"
                onClick={() => navigate("/admin/instructions/global-playbooks")}
                className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Global Playbooks
              </button>

              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                {playbook?.title ?? playbookId ?? "Playbook"}
              </h1>

              {playbook?.description && (
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {playbook.description}
                </p>
              )}
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refetch()}
              aria-label="Обновить версии"
              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            >
              Обновить
            </Button>
          </div>
        </header>

        {/* ── Секция версий ────────────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Версии
            </h2>
            <div className="flex items-center gap-1.5">
              <GitBranch
                className="h-3.5 w-3.5 text-[var(--text-muted)]"
                aria-hidden="true"
              />
              <span className="text-[11px] text-[var(--text-muted)]">
                {versions?.length ?? 0}
              </span>
            </div>
          </div>

          {isLoading && (
            <LoadingBlock text="Загружаем версии..." rows={4} />
          )}

          {isError && (
            <InlineAlert
              tone="error"
              message="Не удалось загрузить версии playbook."
            />
          )}

          {!isLoading && !isError && (!versions || versions.length === 0) && (
            <EmptyState
              title="Версий нет"
              description="Для этого playbook ещё не создано ни одной версии."
            />
          )}

          {!isLoading && !isError && versions && versions.length > 0 && (
            <ul className="space-y-1.5">
              {versions.map((version) => (
                <li key={version.id}>
                  <button
                    type="button"
                    onClick={() => handleOpenVersion(version.id)}
                    className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-2.5 text-left text-xs transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--bg-card)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-[var(--text-primary)]">
                            {version.name}
                          </span>
                          {version.semver && (
                            <span className="font-mono text-[10px] text-[var(--text-muted)]">
                              v{version.semver}
                            </span>
                          )}
                        </div>
                        <div className="mt-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                          {version.id}
                        </div>
                      </div>
                      <VersionStatusBadge status={version.status} size="xs" />
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

      </div>
    </div>
  );
};

export default GlobalPlaybookDetailPage;


