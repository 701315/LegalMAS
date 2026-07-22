// src/pages/instructions/PlaybookVersionDetailPage.tsx
// Detail страница версии global playbook.
// Read-only — global playbook versions управляются через playbook domain.
// Показывает метаданные версии и навигацию.

import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

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

const PlaybookVersionDetailPage: React.FC = () => {
  const { playbookId, versionId } = useParams<{
    playbookId: string;
    versionId: string;
  }>();
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

  const version = versions?.find((v) => v.id === versionId) ?? null;

  const isLoading = isPlaybooksLoading || isVersionsLoading;

  if (isLoading) {
    return (
      <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-4xl">
          <LoadingBlock text="Загружаем версию playbook..." rows={4} />
        </div>
      </div>
    );
  }

  if (isError || (!isLoading && !version)) {
    return (
      <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-4xl space-y-3">
          <InlineAlert
            tone="error"
            message="Версия не найдена или не удалось загрузить данные."
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(-1)}
          >
            ← Назад
          </Button>
        </div>
      </div>
    );
  }

  if (!version) {
    return (
      <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
        <div className="mx-auto max-w-4xl">
          <EmptyState
            title="Версия не найдена"
            description="Проверьте корректность ссылки."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        {/* Header */}
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Admin", to: "/admin" },
            { label: "Инструкции", to: "/admin/instructions" },
            {
              label: "Global Playbooks",
              to: "/admin/instructions/global-playbooks",
            },
            {
              label: playbook?.title ?? playbookId ?? "...",
              to: `/admin/instructions/global-playbooks/${playbookId}`,
            },
            { label: version.name },
          ]}
          title={version.name}
          subtitle={`Playbook: ${playbook?.title ?? playbookId}`}
          rightSlot={
            <div className="flex items-center gap-2">
              <VersionStatusBadge status={version.status} size="sm" />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refetch()}
                aria-label="Обновить"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </div>
          }
        />

        {/* Version meta */}
        <div className="grid grid-cols-2 gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-[11px] sm:grid-cols-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Playbook ID
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-[var(--text-primary)]">
              {version.playbook_id}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Version ID
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-[var(--text-primary)]">
              {version.id}
            </div>
          </div>
          {version.semver && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Semver
              </div>
              <div className="mt-0.5 font-mono font-semibold text-[var(--text-primary)]">
                v{version.semver}
              </div>
            </div>
          )}
        </div>

        {/* Info panel */}
        <PageSection title="Информация">
          <div className="space-y-3">
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3">
              <p className="text-[11px] text-[var(--text-secondary)]">
                Global playbook версии управляются через playbook domain и не
                редактируются напрямую в этом разделе. Для управления
                содержимым playbook используйте раздел{" "}
                <button
                  type="button"
                  onClick={() =>
                    navigate(
                      `/projects/${playbookId}/playbooks/admin`,
                    )
                  }
                  className="text-[var(--accent-primary)] hover:underline"
                >
                  Admin Playbook Lines
                </button>
                .
              </p>
            </div>

            {/* Other versions */}
            {versions && versions.length > 1 && (
              <div>
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Другие версии этого playbook
                </div>
                <ul className="space-y-1">
                  {versions
                    .filter((v) => v.id !== versionId)
                    .map((v) => (
                      <li key={v.id}>
                        <button
                          type="button"
                          onClick={() =>
                            navigate(
                              `/admin/instructions/global-playbooks/${playbookId}/versions/${v.id}`,
                            )
                          }
                          className="flex w-full items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-xs transition-colors hover:bg-[var(--bg-elevated-soft)]"
                        >
                          <span className="font-medium text-[var(--text-primary)]">
                            {v.name}
                          </span>
                          <VersionStatusBadge status={v.status} size="xs" />
                        </button>
                      </li>
                    ))}
                </ul>
              </div>
            )}
          </div>
        </PageSection>
      </div>
    </div>
  );
};

export default PlaybookVersionDetailPage;


