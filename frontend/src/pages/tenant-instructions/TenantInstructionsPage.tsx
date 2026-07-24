// frontend/src/pages/tenant-instructions/TenantInstructionsPage.tsx

import React from "react";
import { useNavigate } from "react-router-dom";
import {
  BookOpen,
  FileText,
  GitBranch,
  Globe,
  Layers,
  Shield,
} from "lucide-react";

const sectionTitleCls =
  "text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]";

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
    className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md"
  >
    <div className="flex items-start gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {title}
        </p>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          {description}
        </p>
      </div>
    </div>
  </button>
);

const TenantInstructionsPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-8">
        <header>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            Инструкции
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Базовые инструкции платформы, playbook studio и переопределения
            для вашей организации
          </p>
        </header>

        {/* Section 1: Base */}
        <div className="space-y-3">
          <h2 className={sectionTitleCls}>
            Базовые инструкции платформы
          </h2>
          <p className="text-xs text-[var(--text-muted)]">
            Управляются superadmin. Доступны вам для просмотра и как основа
            для создания overrides.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <NavCard
              icon={
                <Shield
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              }
              title="Базовые Global Instructions"
              description="Универсальные проверки, применимые к любым документам. Конфиденциальность, юрисдикция, сроки действия."
              onClick={() =>
                navigate("/tenant-admin/instructions/base-global-checks")
              }
            />
            <NavCard
              icon={
                <FileText
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              }
              title="Базовые Doc-Type Instructions"
              description="Инструкции для конкретных типов документов: NDA, SPA, Employment Agreement и др."
              onClick={() =>
                navigate("/tenant-admin/instructions/base-doc-types")
              }
            />
          </div>
        </div>

        {/* Section 2: Playbook Studio */}
        <div className="space-y-3">
          <h2 className={sectionTitleCls}>Playbook Studio</h2>
          <p className="text-xs text-[var(--text-muted)]">
            Сборка playbooks из базовых инструкций и подготовка версий для
            применения в проектах.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <NavCard
              icon={
                <BookOpen
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              }
              title="Playbook Studio"
              description="Создание шаблонов, сборка версий playbook, подготовка к применению в проектах."
              onClick={() =>
                navigate("/tenant-admin/instructions/playbook-studio")
              }
            />
          </div>
        </div>

        {/* Section 3: Tenant-scoped */}
        <div className="space-y-3">
          <h2 className={sectionTitleCls}>
            Переопределения вашей организации
          </h2>
          <p className="text-xs text-[var(--text-muted)]">
            Настройки уровня tenant. Global и Doc-Type overrides применяются
            поверх базовых published-версий. Собственные playbooks видны
            только вашей организации.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <NavCard
              icon={
                <Globe
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              }
              title="Global Overrides"
              description="Переопределения базовых global instructions: severity, wording, пороговые значения."
              onClick={() =>
                navigate("/tenant-admin/instructions/overrides?tab=global")
              }
            />
            <NavCard
              icon={
                <GitBranch
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              }
              title="Doc-Type Overrides"
              description="Переопределения doc-type instructions под специфику вашего бизнеса."
              onClick={() =>
                navigate("/tenant-admin/instructions/overrides?tab=doc-type")
              }
            />
            <NavCard
              icon={
                <Layers
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              }
              title="Playbooks организации"
              description="Собственные playbooks вашей организации. Видны только вам, не доступны другим клиентам платформы."
              onClick={() =>
                navigate("/tenant-admin/instructions/my-playbooks")
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default TenantInstructionsPage;


