// frontend/src/pages/tenant-instructions/TenantInstructionsPage.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  BookOpen,
  FileText,
  GitBranch,
  Globe,
  Layers,
  Shield,
} from "lucide-react";

interface NavCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  onClick: () => void;
}

const NavCard: React.FC<NavCardProps> = ({
  icon,
  title,
  description,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={[
      "group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm",
      "transition-all duration-200",
      "hover:border-[var(--border-strong)] hover:shadow-md",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35",
      "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-elevated-soft)]",
    ].join(" ")}
  >
    <div className="flex items-start gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] transition-colors group-hover:bg-[var(--accent-muted)] group-hover:text-[var(--accent-primary)]">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
          {title}
        </p>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">
          {description}
        </p>
      </div>
    </div>
  </button>
);

const TenantInstructionsPage: React.FC = () => {
  const { t } = useTranslation("instructions");
  const navigate = useNavigate();

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* HEADER */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              {t("tenantInstructionsIndex.title")}
            </h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              {t("tenantInstructionsIndex.subtitle")}
            </p>
          </div>
        </header>

        {/* 2 COLUMNS */}
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">

          {/* LEFT COLUMN */}
          <div className="space-y-4">

            {/* Платформа */}
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  {t("tenantInstructionsIndex.platform.label")}
                </div>
                <h2 className="mt-2 text-base font-semibold text-[var(--text-primary)]">
                  {t("tenantInstructionsIndex.platform.title")}
                </h2>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {t("tenantInstructionsIndex.platform.description")}
                </p>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <NavCard
                  icon={<Shield className="h-4 w-4" aria-hidden="true" />}
                  title={t("tenantInstructionsIndex.platform.globalTitle")}
                  description={t("tenantInstructionsIndex.platform.globalDesc")}
                  onClick={() =>
                    navigate("/tenant-admin/instructions/base-global-checks")
                  }
                />
                <NavCard
                  icon={<FileText className="h-4 w-4" aria-hidden="true" />}
                  title={t("tenantInstructionsIndex.platform.docTypeTitle")}
                  description={t("tenantInstructionsIndex.platform.docTypeDesc")}
                  onClick={() =>
                    navigate("/tenant-admin/instructions/base-doc-types")
                  }
                />
              </div>
            </section>

            {/* Studio */}
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  {t("tenantInstructionsIndex.studio.label")}
                </div>
                <h2 className="mt-2 text-base font-semibold text-[var(--text-primary)]">
                  {t("tenantInstructionsIndex.studio.title")}
                </h2>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {t("tenantInstructionsIndex.studio.description")}
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2">
                <NavCard
                  icon={<BookOpen className="h-4 w-4" aria-hidden="true" />}
                  title={t("tenantInstructionsIndex.studio.cardTitle")}
                  description={t("tenantInstructionsIndex.studio.cardDesc")}
                  onClick={() =>
                    navigate("/tenant-admin/instructions/playbook-studio")
                  }
                />
              </div>
            </section>

            {/* Организация */}
            <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
              <div className="mb-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  {t("tenantInstructionsIndex.org.label")}
                </div>
                <h2 className="mt-2 text-base font-semibold text-[var(--text-primary)]">
                  {t("tenantInstructionsIndex.org.title")}
                </h2>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {t("tenantInstructionsIndex.org.description")}
                </p>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <NavCard
                  icon={<Globe className="h-4 w-4" aria-hidden="true" />}
                  title={t("tenantInstructionsIndex.org.globalTitle")}
                  description={t("tenantInstructionsIndex.org.globalDesc")}
                  onClick={() =>
                    navigate("/tenant-admin/instructions/overrides?tab=global")
                  }
                />
                <NavCard
                  icon={<GitBranch className="h-4 w-4" aria-hidden="true" />}
                  title={t("tenantInstructionsIndex.org.docTypeTitle")}
                  description={t("tenantInstructionsIndex.org.docTypeDesc")}
                  onClick={() =>
                    navigate("/tenant-admin/instructions/overrides?tab=doc-type")
                  }
                />
                <NavCard
                  icon={<Layers className="h-4 w-4" aria-hidden="true" />}
                  title={t("tenantInstructionsIndex.org.playbooksTitle")}
                  description={t("tenantInstructionsIndex.org.playbooksDesc")}
                  onClick={() =>
                    navigate("/tenant-admin/instructions/my-playbooks")
                  }
                />
              </div>
            </section>

          </div>

          {/* RIGHT COLUMN — EDITORIAL VISUAL */}
          <div className="hidden xl:block">
            <div className="relative h-full w-full overflow-hidden rounded-2xl">
              <img
                src="/instrcutionpicture.png"
                alt=""
                aria-hidden="true"
                className="h-full w-full object-cover"
              />
              {/* subtle gradient */}
              <div className="absolute inset-0 bg-gradient-to-t from-[var(--bg-base)]/10 to-transparent" />
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

export default TenantInstructionsPage;


