// =============================================================
// src/pages/tabs/CounterpartiesTab.tsx
// Вкладка «Анализ выявленных контрагентов».
//
// Статус: Preview / Coming soon.
//
// TODO при наполнении:
// - подключить useCounterparties(dealId, currentRunId)
// - убрать <ComingSoonBanner />
// - раскомментировать фильтры, реальную таблицу, detail-панель
// =============================================================

import React from "react";

// ---------------------------------------------------------------------------
// Types — вынести в ../../types при подключении API
// ---------------------------------------------------------------------------

export type CounterpartyType = "legal_entity" | "individual" | "unknown";
export type CounterpartyRisk = "high" | "medium" | "low" | "unknown";

export interface Counterparty {
  id: string;
  name: string;
  type: CounterpartyType;
  risk: CounterpartyRisk;
  document_count: number;
  inn?: string | null;
  ogrn?: string | null;
  first_mentioned_at?: string | null;
}

interface CounterpartiesTabProps {
  dealId: string;
  currentRunId: string | null;
}

// ---------------------------------------------------------------------------
// CardShell — точная копия паттерна из OverviewTab
// ---------------------------------------------------------------------------

const CardShell: React.FC<{
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  rightSlot?: React.ReactNode;
}> = ({ title, eyebrow, children, rightSlot }) => (
  <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
    <div className="px-5">
      <div className="flex items-start justify-between gap-4 py-4">
        <div className="min-w-0">
          {eyebrow ? (
            <>
              <h2 className="text-base font-semibold text-[var(--text-primary)]">
                {eyebrow}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">{title}</p>
            </>
          ) : (
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              {title}
            </h2>
          )}
        </div>
        {rightSlot}
      </div>
      <div className="border-t border-[var(--border-subtle)]" />
    </div>
    <div className="px-5 py-4">{children}</div>
  </section>
);

// ---------------------------------------------------------------------------
// ComingSoonBanner
// ---------------------------------------------------------------------------

const ComingSoonBanner: React.FC = () => (
  <div className="flex items-start gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-4 shadow-sm">
    <div className="mt-0.5 shrink-0 text-[var(--accent-primary)]">
      <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="10" r="8.5" stroke="currentColor" strokeWidth="1.5" />
        <path d="M10 6.5V10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="10" cy="13.5" r="0.75" fill="currentColor" />
      </svg>
    </div>
    <div>
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        Раздел находится в разработке
      </p>
      <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
        Автоматическое выявление и анализ контрагентов из документов сделки —
        функциональность появится в ближайшем обновлении. Ниже показана
        структура раздела.
      </p>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// StatCard
// ---------------------------------------------------------------------------

const StatCard: React.FC<{
  label: string;
  value: string;
  hint?: string;
  accentValue?: boolean;
}> = ({ label, value, hint, accentValue = false }) => (
  <div className="flex flex-col gap-1 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
    <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
      {label}
    </p>
    <p className={[
      "text-2xl font-semibold tabular-nums",
      accentValue ? "text-[var(--color-error)]" : "text-[var(--text-primary)]",
    ].join(" ")}>
      {value}
    </p>
    {hint && <p className="text-[11px] leading-5 text-[var(--text-muted)]">{hint}</p>}
  </div>
);

// ---------------------------------------------------------------------------
// EntityListPlaceholder
// ---------------------------------------------------------------------------

const SkeletonRow: React.FC<{ index: number }> = ({ index }) => {
  const widths = ["w-44", "w-52", "w-36", "w-48", "w-40", "w-56"];
  return (
    <div className="flex items-center gap-4 border-b border-[var(--border-subtle)] px-5 py-3 last:border-0">
      <div className="h-8 w-8 shrink-0 animate-pulse rounded-full bg-[var(--bg-elevated-soft)]" />
      <div className={`h-3 animate-pulse rounded bg-[var(--bg-elevated-soft)] ${widths[index % widths.length]}`} />
      <div className="ml-auto h-5 w-20 animate-pulse rounded-full bg-[var(--bg-elevated-soft)]" />
      <div className="h-5 w-12 animate-pulse rounded-full bg-[var(--bg-elevated-soft)]" />
      <div className="h-3 w-6 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
    </div>
  );
};

const EntityListPlaceholder: React.FC<{ hasRun: boolean }> = ({ hasRun }) => {
  if (!hasRun) {
    return (
      <div className="px-5 py-10 text-center">
        <p className="text-sm font-medium text-[var(--text-primary)]">
          Данные пока недоступны
        </p>
        <p className="mt-1.5 text-sm leading-6 text-[var(--text-secondary)]">
          Запустите анализ проекта — контрагенты будут выявлены автоматически
          на основе документов сделки.
        </p>
      </div>
    );
  }
  return (
    <>
      {Array.from({ length: 6 }).map((_, i) => (
        <SkeletonRow key={i} index={i} />
      ))}
    </>
  );
};

// ---------------------------------------------------------------------------
// FeatureCard
// ---------------------------------------------------------------------------

const FeatureCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  description: string;
}> = ({ icon, title, description }) => (
  <div className="flex flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
    <div className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--accent-primary)]">
      {icon}
    </div>
    <div>
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{description}</p>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

const IconSearch = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.5" />
    <path d="M13.5 13.5L17 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const IconGraph = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="5"  cy="10"   r="2.5" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="15" cy="4.5"  r="2.5" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="15" cy="15.5" r="2.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7.2 9l5.6-3.5M7.2 11l5.6 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const IconShield = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2L3.5 5v4.5c0 3.86 2.75 7.47 6.5 8.5 3.75-1.03 6.5-4.64 6.5-8.5V5L10 2z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M7 10l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const IconLink = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M8.5 11.5a4.243 4.243 0 006 0l2-2a4.243 4.243 0 00-6-6L9 5"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M11.5 8.5a4.243 4.243 0 00-6 0l-2 2a4.243 4.243 0 006 6L11 15"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const CounterpartiesTab: React.FC<CounterpartiesTabProps> = ({
  dealId: _dealId,
  currentRunId,
}) => {
  const hasRun = currentRunId !== null;

  return (
    <div className="space-y-4 overflow-y-auto">

      <ComingSoonBanner />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Выявлено всего"   value="—" hint="После первого анализа" />
        <StatCard label="Юридических лиц"  value="—" />
        <StatCard label="Физических лиц"   value="—" />
        <StatCard label="Высокий риск"     value="—" />
      </div>

      <CardShell
        eyebrow="Список контрагентов"
        title="Юридические и физические лица, выявленные в документах"
        rightSlot={
          <span className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-medium text-[var(--text-muted)]">
            Нет данных
          </span>
        }
      >
        {/* future: строка фильтров — тип / риск / поиск */}
        <EntityListPlaceholder hasRun={hasRun} />
      </CardShell>

      <section>
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Что будет в этом разделе
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <FeatureCard
            icon={<IconSearch />}
            title="Автоматическое выявление"
            description="NLP-пайплайн извлекает наименования контрагентов из всех документов и нормализует их."
          />
          <FeatureCard
            icon={<IconGraph />}
            title="Граф связей"
            description="Визуализация взаимосвязей между сторонами, аффилированными лицами и корпоративными структурами."
          />
          <FeatureCard
            icon={<IconShield />}
            title="Оценка рисков"
            description="Автоматические флаги по санкционным спискам, судебным делам и реестрам ФНС / ЕГРЮЛ."
          />
          <FeatureCard
            icon={<IconLink />}
            title="Перекрёстные ссылки"
            description="Каждый контрагент привязан к конкретным документам, разделам и пунктам, где упоминается."
          />
        </div>
      </section>

    </div>
  );
};

export default CounterpartiesTab;


