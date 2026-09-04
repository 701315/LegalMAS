// =============================================================
// src/pages/tabs/SettingsTab.tsx
// Вкладка «Настройки проекта».
// Внутри поддерживает subviews:
// - overview
// - members
// - playbook
// - templates
// Управление участниками, playbook и конструктором шаблонов
// открывается в рабочей зоне таба, а не отдельными full-page страницами.
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  BookOpen,
  FolderCog,
  Shield,
  Users,
} from "lucide-react";

import Button from "../../components/ui/Button";
import PageSection from "../../components/ui/PageSection";
import ProjectMembersPanel from "../../components/settings/ProjectMembersPanel";
import DealPlaybookSelectorPanel from "../../components/playbook/DealPlaybookSelectorPanel";
import AdminPlaybookLinesPage from "../AdminPlaybookLinesPage";

interface SettingsTabProps {
  dealId: string;
  canManageProject: boolean;
}

type SettingsSubview = "overview" | "members" | "playbook" | "playbook_template_editor" | "templates";

const SettingsCard: React.FC<{
  eyebrow: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  actions: React.ReactNode;
}> = ({ eyebrow, title, description, icon, actions }) => {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="flex items-start gap-4 px-5 py-5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]">
          {icon}
        </div>

        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
            {eyebrow}
          </p>

          <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
            {title}
          </h3>

          <p className="mt-1.5 max-w-2xl text-sm text-[var(--text-muted)]">
            {description}
          </p>

          <div className="mt-4 flex flex-wrap gap-2">{actions}</div>
        </div>
      </div>
    </section>
  );
};

const SettingsTab: React.FC<SettingsTabProps> = ({
  dealId,
  canManageProject,
}) => {
  const { t } = useTranslation("projects");
  const [activeSubview, setActiveSubview] =
    React.useState<SettingsSubview>("overview");

  const handleBackToSettings = React.useCallback(() => {
    setActiveSubview("overview");
  }, []);

  const [editingTemplateId, setEditingTemplateId] =
    React.useState<string | null>(null);

  const handleEditTemplate = React.useCallback((templateId: string) => {
    setEditingTemplateId(templateId);
    setActiveSubview("playbook_template_editor");
  }, []);

  const handleBackToPlaybook = React.useCallback(() => {
    setEditingTemplateId(null);
    setActiveSubview("playbook");
  }, []);

  const headerActions = (
    <Button
      type="button"
      size="sm"
      variant="secondary"
      leftIcon={<ArrowLeft size={14} />}
      onClick={handleBackToSettings}
    >
      {t("settingsTab.backToSettings")}
    </Button>
  );

  if (!canManageProject) {
    return (
      <PageSection
        title={t("settingsTab.title")}
        subtitle={t("settingsTab.subtitleNoPerms")}
      >
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 shadow-sm">
          <div className="flex min-h-[280px] flex-col items-center justify-center text-center">
            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
              <Shield size={28} className="text-[var(--text-muted)]" />
            </div>

            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              {t("settingsTab.noAccess.title")}
            </h2>

            <p className="mt-2 max-w-md text-sm text-[var(--text-muted)]">
              {t("settingsTab.noAccess.description")}
            </p>
          </div>
        </div>
      </PageSection>
    );
  }

  if (activeSubview === "members") {
    return (
      <ProjectMembersPanel
        dealId={dealId}
        onBack={handleBackToSettings}
        backButton={headerActions}
      />
    );
  }

  if (activeSubview === "playbook_template_editor") {
    return (
      <AdminPlaybookLinesPage
        mode="embedded"
        initialPlaybookId={editingTemplateId}
        headerActions={
          <Button
            type="button"
            size="sm"
            variant="secondary"
            leftIcon={<ArrowLeft size={14} />}
            onClick={handleBackToPlaybook}
          >
            {t("settingsTab.backToPlaybook")}
          </Button>
        }
        onCancel={handleBackToPlaybook}
        onDeleted={undefined}
      />
    );
  }

  if (activeSubview === "playbook") {
    return (
      <DealPlaybookSelectorPanel
        dealId={dealId}
        mode="embedded"
        onCancel={handleBackToSettings}
        onFinished={handleBackToSettings}
        onEditTemplate={handleEditTemplate}
        headerActions={headerActions}
      />
    );
  }

  if (activeSubview === "templates") {
    return (
      <AdminPlaybookLinesPage
        mode="embedded"
        onCancel={handleBackToSettings}
        headerActions={headerActions}
      />
    );
  }

  return (
    <PageSection
      title={t("settingsTab.title")}
      subtitle={t("settingsTab.subtitleWithPerms")}
    >
      <div className="grid gap-4 xl:grid-cols-2">
        <SettingsCard
          eyebrow={t("settingsTab.cards.team.eyebrow")}
          title={t("settingsTab.cards.team.title")}
          description={t("settingsTab.cards.team.description")}
          icon={<Users size={18} />}
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setActiveSubview("members")}
            >
              {t("settingsTab.cards.team.action")}
            </Button>
          }
        />

        <SettingsCard
          eyebrow={t("settingsTab.cards.methodology.eyebrow")}
          title={t("settingsTab.cards.methodology.title")}
          description={t("settingsTab.cards.methodology.description")}
          icon={<BookOpen size={18} />}
          actions={
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setActiveSubview("playbook")}
              >
                {t("settingsTab.cards.methodology.actions.open")}
              </Button>

              <Button
                variant="secondary"
                size="sm"
                onClick={() => setActiveSubview("templates")}
              >
                {t("settingsTab.cards.methodology.actions.builder")}
              </Button>
            </>
          }
        />

        <section className="xl:col-span-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
          <div className="flex items-start gap-4 px-5 py-5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]">
              <FolderCog size={18} />
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
                {t("settingsTab.cards.workspace.eyebrow")}
              </p>

              <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                {t("settingsTab.cards.workspace.title")}
              </h3>

              <p className="mt-1.5 max-w-3xl text-sm text-[var(--text-muted)]">
                {t("settingsTab.cards.workspace.description")}
              </p>
            </div>
          </div>
        </section>
      </div>
    </PageSection>
  );
};

export default SettingsTab;


