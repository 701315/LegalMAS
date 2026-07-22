// src/pages/instructions/GlobalPlaybooksPage.tsx
// Список global playbooks с версиями.
//
// Показывает:
// - список логических playbooks (PlaybookLineShort через facade)
// - для выбранного playbook — список его версий
// - статус каждой версии
// - кнопка перехода к detail версии

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { BookOpen, GitBranch, RefreshCw } from "lucide-react";

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
import type { GlobalPlaybookItem } from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Вспомогательный компонент: карточка playbook в списке
// ─────────────────────────────────────────────────────────────

interface PlaybookListItemProps {
  playbook: GlobalPlaybookItem;
  isSelected: boolean;
  onClick: () => void;
}

const PlaybookListItem: React.FC<PlaybookListItemProps> = ({
  playbook,
  isSelected,
  onClick,
}) => {
  const meta = [
    playbook.deal_type && `Type: ${playbook.deal_type}`,
    playbook.jurisdiction && `Jurisdiction: ${playbook.jurisdiction}`,
    playbook.language && `Lang: ${playbook.language}`,
    playbook.risk_profile && `Risk: ${playbook.risk_profile}`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "w-full rounded-xl border px-3 py-2.5 text-left text-xs transition-colors",
        isSelected
          ? "border-[var(--accent-primary)]/40 bg-[var(--accent-muted)] text-[var(--text-primary)]"
          : "border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
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
          {meta && (
            <div className="mt-1 truncate text-[10px] text-[var(--text-muted)]">
              {meta}
            </div>
          )}
          {playbook.description && (
            <div className="mt-1 line-clamp-2 text-[11px] text-[var(--text-secondary)]">
              {playbook.description}
            </div>
          )}
        </div>
      </div>
    </button>
  );
};

// ─────────────────────────────────────────────────────────────
// Вспомогательный компонент: панель версий выбранного playbook
// ─────────────────────────────────────────────────────────────

interface PlaybookVersionsPanelProps {
  playbook: GlobalPlaybookItem;
}

const PlaybookVersionsPanel: React.FC<PlaybookVersionsPanelProps> = ({
  playbook,
}) => {
  const navigate = useNavigate();
  const { data: versions, isLoading, isError, refetch } =
    useGlobalPlaybookVersions(playbook.id);

  const handleOpenVersion = (versionId: string) => {
    navigate(
      `/admin/instructions/global-playbooks/${playbook.id}/versions/${versionId}`,
    );
  };

  return (
    <div className="space-y-3">
      {/* Playbook meta */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-3">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--text-muted)]">
          Playbook
        </div>
        <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
          {playbook.title}
        </div>
        <div className="mt-0.5 font-mono text-[11px] text-[var(--text-muted)]">
          {playbook.code}
        </div>
        {playbook.description && (
          <div className="mt-1.5 text-xs text-[var(--text-secondary)]">
            {playbook.description}
          </div>
        )}
        <div className="mt-2 flex flex-wrap gap-2">
          {playbook.deal_type && (
            <span className="rounded-md border border-[var(--border)] bg-[var(--bg-card)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
              {playbook.deal_type}
            </span>
          )}
          {playbook.jurisdiction && (
            <span className="rounded-md border border-[var(--border)] bg-[var(--bg-card)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
              {playbook.jurisdiction}
            </span>
          )}
          {playbook.language && (
            <span className="rounded-md border border-[var(--border)] bg-[var(--bg-card)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
              {playbook.language}
            </span>
          )}
          {playbook.risk_profile && (
            <span className="rounded-md border border-[var(--border)] bg-[var(--bg-card)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
              risk: {playbook.risk_profile}
            </span>
          )}
        </div>
      </div>

      {/* Versions list */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <GitBranch
              className="h-3.5 w-3.5 text-[var(--text-muted)]"
              aria-hidden="true"
            />
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
              Версии
            </span>
          </div>
          <button
            type="button"
            onClick={() => void refetch()}
            className="rounded-lg p-1 text-[var(--text-muted)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)] transition-colors"
            aria-label="Обновить список версий"
          >
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
          </button>
        </div>

        {isLoading && (
          <LoadingBlock text="Загружаем версии..." rows={3} />
        )}

        {isError && (
          <InlineAlert
            tone="error"
            message="Не удалось загрузить версии playbook."
          />
        )}

        {!isLoading && !isError && versions && versions.length === 0 && (
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
                        <span className="truncate font-semibold text-[var(--text-primary)]">
                          {version.name}
                        </span>
                        {version.semver && (
                          <span className="shrink-0 font-mono text-[10px] text-[var(--text-muted)]">
                            v{version.semver}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                        {version.id}
                      </div>
                    </div>
                    <VersionStatusBadge
                      status={version.status}
                      size="xs"
                    />
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Главная страница
// ─────────────────────────────────────────────────────────────

const GlobalPlaybooksPage: React.FC = () => {
  const [selectedPlaybookId, setSelectedPlaybookId] = useState<string | null>(
    null,
  );

  const {
    data: playbooks,
    isLoading,
    isError,
    refetch,
  } = useGlobalPlaybooks();

  const selectedPlaybook =
    playbooks?.find((p) => p.id === selectedPlaybookId) ?? null;

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-6xl space-y-4">
        {/* Header */}
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Admin", to: "/admin" },
            { label: "Инструкции", to: "/admin/instructions" },
            { label: "Global Playbooks" },
          ]}
          title="Global Playbooks"
          subtitle="Базовые playbooks для всех tenant. Выберите playbook чтобы просмотреть версии."
          rightSlot={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refetch()}
              aria-label="Обновить список playbooks"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          }
        />

        {/* Content */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          {/* Левая колонка: список playbooks */}
          <div className="lg:col-span-2">
            <PageSection title="Playbooks">
              {isLoading && (
                <LoadingBlock text="Загружаем playbooks..." rows={5} />
              )}

              {isError && (
                <InlineAlert
                  tone="error"
                  message="Не удалось загрузить список playbooks."
                />
              )}

              {!isLoading && !isError && (!playbooks || playbooks.length === 0) && (
                <EmptyState
                  title="Playbooks не найдены"
                  description="Global playbooks ещё не созданы или недоступны."
                />
              )}

              {!isLoading && !isError && playbooks && playbooks.length > 0 && (
                <ul className="space-y-1.5">
                  {playbooks.map((playbook) => (
                    <li key={playbook.id}>
                      <PlaybookListItem
                        playbook={playbook}
                        isSelected={selectedPlaybookId === playbook.id}
                        onClick={() => setSelectedPlaybookId(playbook.id)}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </PageSection>
          </div>

          {/* Правая колонка: версии выбранного playbook */}
          <div className="lg:col-span-3">
            <PageSection title="Версии">
              {!selectedPlaybook ? (
                <EmptyState
                  title="Playbook не выбран"
                  description="Выберите playbook слева чтобы просмотреть его версии."
                />
              ) : (
                <PlaybookVersionsPanel playbook={selectedPlaybook} />
              )}
            </PageSection>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GlobalPlaybooksPage;


