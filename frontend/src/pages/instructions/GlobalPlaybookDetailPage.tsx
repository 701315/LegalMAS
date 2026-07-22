// src/pages/instructions/GlobalPlaybookDetailPage.tsx
// Detail страница global playbook — список версий + переход к версии.
// Дублирует логику PlaybookVersionsPanel, но как самостоятельная страница.

import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { GitBranch, RefreshCw } from "lucide-react";

import {
  useGlobalPlaybooks,
  useGlobalPlaybookVersions,
} from "../../hooks/instructions/useInstructionVersions";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import PageSection from "../../components/ui/PageSection";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";

const GlobalPlaybookDetailPage: React.FC = () => {
  const { playbookId } = useParams<{ playbookId: string }>();
  const navigate = useNavigate();

  const { data: playbooks, isLoading: isPlaybooksLoading } = useGlobalPlaybooks();
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
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Admin", to: "/admin" },
            { label: "Инструкции", to: "/admin/instructions" },
            { label: "Global Playbooks", to: "/admin/instructions/global-playbooks" },
            { label: playbook?.title ?? playbookId ?? "..." },
          ]}
          title={playbook?.title ?? "Playbook"}
          subtitle={playbook?.description ?? undefined}
          rightSlot={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refetch()}
              aria-label="Обновить версии"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          }
        />

        <PageSection
          title="Версии"
          rightSlot={
            <div className="flex items-center gap-1.5">
              <GitBranch
                className="h-3.5 w-3.5 text-[var(--text-muted)]"
                aria-hidden="true"
              />
              <span className="text-[11px] text-[var(--text-muted)]">
                {versions?.length ?? 0}
              </span>
            </div>
          }
        >
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
                    className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5 text-left text-xs transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
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
        </PageSection>
      </div>
    </div>
  );
};

export default GlobalPlaybookDetailPage;


