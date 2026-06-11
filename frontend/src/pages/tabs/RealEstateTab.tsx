// =============================================================
// src/pages/tabs/RealEstateTab.tsx
// Вкладка «Анализ выявленного недвижимого имущества».
//
// Статус: Preview / Coming soon.
//
// TODO при наполнении:
// - подключить useRealEstate(dealId, currentRunId)
// - убрать <ComingSoonBanner />
// - раскомментировать фильтры, реальную таблицу, detail-панель
// =============================================================

import React from "react";

// ---------------------------------------------------------------------------
// Types — вынести в ../../types при подключении API
// ---------------------------------------------------------------------------

export type RealEstateObjectType =
  | "land"
  | "building"
  | "premises"
  | "construction"
  | "unfinished"
  | "unknown";

export type RealEstateRisk = "high" | "medium" | "low" | "unknown";

export interface RealEstateObject {
  id: string;
  address?: string | null;
  cadastral_number?: string | null;
  object_type: RealEstateObjectType;
  risk: RealEstateRisk;
  document_count: number;
  area_sqm?: number | null;
  encumbrance?: boolean | null;
  first_mentioned_at?: string | null;
}

interface RealEstateTabProps {
  dealId: string;
  currentRunId: string | null;
}

// ---------------------------------------------------------------------------
// CardShell — единый паттерн с OverviewTab / CounterpartiesTab
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
        Автоматическое выявление объектов недвижимого имущества из документов
        сделки — функциональность появится в ближайшем обновлении. Ниже
        показана структура раздела.
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
    {hint && (
      <p className="text-[11px] leading-5 text-[var(--text-muted)]">{hint}</p>
    )}
  </div>
);

// ---------------------------------------------------------------------------
// ObjectListPlaceholder
// ---------------------------------------------------------------------------

const SkeletonRow: React.FC<{ index: number }> = ({ index }) => {
  const addrWidths = ["w-56", "w-64", "w-48", "w-60", "w-52", "w-72"];
  return (
    <div className="flex items-center gap-4 border-b border-[var(--border-subtle)] px-5 py-3 last:border-0">
      {/* иконка типа объекта */}
      <div className="h-8 w-8 shrink-0 animate-pulse rounded-lg bg-[var(--bg-elevated-soft)]" />
      {/* адрес / кадастровый номер */}
      <div className={`h-3 animate-pulse rounded bg-[var(--bg-elevated-soft)] ${addrWidths[index % addrWidths.length]}`} />
      {/* тип объекта */}
      <div className="ml-auto h-5 w-24 animate-pulse rounded-full bg-[var(--bg-elevated-soft)]" />
      {/* обременение */}
      <div className="h-5 w-16 animate-pulse rounded-full bg-[var(--bg-elevated-soft)]" />
      {/* площадь */}
      <div className="h-3 w-10 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
    </div>
  );
};

const ObjectListPlaceholder: React.FC<{ hasRun: boolean }> = ({ hasRun }) => {
  if (!hasRun) {
    return (
      <div className="px-5 py-10 text-center">
        <p className="text-sm font-medium text-[var(--text-primary)]">
          Данные пока недоступны
        </p>
        <p className="mt-1.5 text-sm leading-6 text-[var(--text-secondary)]">
          Запустите анализ проекта — объекты недвижимости будут выявлены
          автоматически на основе документов сделки.
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

const IconBuilding = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="5" width="14" height="13" rx="1" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 8h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M7 18v-5h6v5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M7 11.5h1.5M11.5 11.5H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M10 2v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const IconCadaster = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="3" width="14" height="14" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 10h14M10 3v14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <rect x="5.5" y="5.5" width="3" height="3" rx="0.5" stroke="currentColor" strokeWidth="1" />
    <rect x="11.5" y="11.5" width="3" height="3" rx="0.5" stroke="currentColor" strokeWidth="1" />
  </svg>
);

const IconEncumbrance = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path
      d="M10 2L3.5 5v4.5c0 3.86 2.75 7.47 6.5 8.5 3.75-1.03 6.5-4.64 6.5-8.5V5L10 2z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"
    />
    <path d="M7.5 10.5l1.5 1.5 3.5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const IconMap = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path
      d="M3 5.5l4.5-2 5 2 4.5-2V15l-4.5 2-5-2-4.5 2V5.5z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"
    />
    <path d="M7.5 3.5v11.5M12.5 5.5V17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const RealEstateTab: React.FC<RealEstateTabProps> = ({
  dealId: _dealId,
  currentRunId,
}) => {
  const hasRun = currentRunId !== null;

  return (
    <div className="space-y-4 overflow-y-auto">

      <ComingSoonBanner />

      {/* ── KPI row ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Объектов выявлено"
          value="—"
          hint="После первого анализа"
        />
        <StatCard label="Земельных участков"  value="—" />
        <StatCard label="Зданий и помещений"  value="—" />
        <StatCard
          label="С обременениями"
          value="—"
          accentValue={false}
        />
      </div>

      {/* ── Object list ── */}
      <CardShell
        eyebrow="Реестр объектов"
        title="Недвижимое имущество, выявленное в документах сделки"
        rightSlot={
          <span className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-medium text-[var(--text-muted)]">
            Нет данных
          </span>
        }
      >
        {/* future: строка фильтров — тип объекта / обременение / поиск по адресу / кадастровому номеру */}
        <ObjectListPlaceholder hasRun={hasRun} />
      </CardShell>

      {/* ── Feature preview ── */}
      <section>
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Что будет в этом разделе
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <FeatureCard
            icon={<IconBuilding />}
            title="Автоматическое выявление"
            description="NLP-пайплайн извлекает упоминания объектов недвижимости — адреса, кадастровые номера, описания."
          />
          <FeatureCard
            icon={<IconCadaster />}
            title="Кадастровая верификация"
            description="Сопоставление выявленных объектов с данными ЕГРН и публичной кадастровой картой."
          />
          <FeatureCard
            icon={<IconEncumbrance />}
            title="Анализ обременений"
            description="Автоматическое выявление залогов, арестов, сервитутов и иных ограничений права из документов."
          />
          <FeatureCard
            icon={<IconMap />}
            title="Карта и реестр"
            description="Сводный реестр объектов с привязкой к документам и разделам, где они упоминаются."
          />
        </div>
      </section>

    </div>
  );
};

export default RealEstateTab;



