// =============================================================
// src/pages/tabs/RealEstateTab.tsx
// Вкладка «Анализ выявленного недвижимого имущества».
//
// Preview flow:
// 1) Intro screen — короткое описание раздела
// 2) Demo screen  — overview + shared split-view workspace
//
// TODO при подключении API:
// - подключить useRealEstate(dealId, currentRunId)
// - заменить demo-данные на backend DTO
// - привязать summary / table / detail panel к реальному enrichment
// - заменить alert() на реальный export flow
// =============================================================

import React from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RealEstateObjectType =
  | "land"
  | "building"
  | "premises"
  | "construction"
  | "unfinished"
  | "unknown";

export type RealEstateRisk = "high" | "medium" | "low" | "unknown";

type PreviewMode = "intro" | "demo";
type DrilldownKind = "geography" | "encumbrances" | "area_top" | "critical" | null;
type ExportMenuKind = "list" | null;
type ExportFormat = "excel" | "docx" | "pdf";
type SortDirection = "asc" | "desc";
type SortKey =
  | "index"
  | "address"
  | "region"
  | "objectType"
  | "area"
  | "documentCount"
  | "encumbrance"
  | "risk";

interface SortState {
  key: SortKey;
  direction: SortDirection;
}

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

export interface RealEstateObjectAggregate extends RealEstateObject {
  region: string;
  market: "RU" | "UAE" | "EU";
  ownership_status: "registered" | "review" | "not_confirmed";
  usage_type: "office" | "warehouse" | "land_plot" | "industrial" | "retail" | "mixed";
}

interface MentionedDocument {
  id: string;
  title: string;
  documentType: string;
  section: string;
  mentionRole: string;
}

interface RealEstateObjectDetail {
  id: string;
  shortDescription: string;
  documents: MentionedDocument[];
  registry: {
    registrySource: string;
    ownershipStatus: string;
    ownerName: string;
    cadastralNumber: string;
    objectTypeLabel: string;
    areaLabel: string;
    addressLabel: string;
  };
  encumbrances: {
    hasEncumbrances: "yes" | "no" | "review";
    mortgage: "yes" | "no" | "review";
    arrest: "yes" | "no" | "review";
    easement: "yes" | "no" | "review";
    notes: string[];
  };
  legalChecks: {
    titleChain: "ok" | "review" | "issue";
    registryMatch: "ok" | "review" | "issue";
    zoning: "ok" | "review" | "issue";
    notes: string[];
  };
  mapContext: {
    region: string;
    district: string;
    geoNote: string;
  };
}

interface CoverageRow {
  jurisdiction: string;
  registrySources: string;
  whatChecked: string;
  remarks: string;
}

interface RealEstateTabProps {
  dealId: string;
  currentRunId: string | null;
}

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------

const COVERAGE_ROWS: CoverageRow[] = [
  {
    jurisdiction: "Россия",
    registrySources: "ЕГРН, публичная кадастровая карта",
    whatChecked: "Право, кадастровый номер, площадь, обременения",
    remarks: "Основной сценарий для RU real estate due diligence",
  },
  {
    jurisdiction: "UAE",
    registrySources: "Dubai Land Department / emirate land registries",
    whatChecked: "Title, ownership, plot/building registration",
    remarks: "По эмирату требуется отдельный локальный источник",
  },
  {
    jurisdiction: "Европа",
    registrySources: "Национальные land / property registries",
    whatChecked: "Ownership, encumbrances, title data",
    remarks: "Источник зависит от страны и локального регистра",
  },
  {
    jurisdiction: "Внутренние базы компании",
    registrySources: "Asset register, lease register, legal archive",
    whatChecked: "Внутренний статус актива, исторические документы, usage",
    remarks: "Используется для cross-check с внешними регистрами",
  },
];

const BASE_OBJECTS: RealEstateObjectAggregate[] = [
  {
    id: "1",
    address: "Москва, ул. Лесная, д. 12, стр. 3",
    cadastral_number: "77:01:0004012:1456",
    object_type: "building",
    risk: "medium",
    document_count: 6,
    area_sqm: 12450,
    encumbrance: true,
    first_mentioned_at: "SPA § 2.1",
    region: "Москва",
    market: "RU",
    ownership_status: "registered",
    usage_type: "office",
  },
  {
    id: "2",
    address: "Московская область, Химки, Логистический проезд, 8",
    cadastral_number: "50:10:0010203:884",
    object_type: "building",
    risk: "low",
    document_count: 4,
    area_sqm: 28700,
    encumbrance: false,
    first_mentioned_at: "Disclosure Letter § 4",
    region: "Московская область",
    market: "RU",
    ownership_status: "registered",
    usage_type: "warehouse",
  },
  {
    id: "3",
    address: "Санкт-Петербург, Пулковское шоссе, участок 17",
    cadastral_number: "78:14:0007689:31",
    object_type: "land",
    risk: "high",
    document_count: 5,
    area_sqm: 45200,
    encumbrance: true,
    first_mentioned_at: "Asset Schedule #3",
    region: "Санкт-Петербург",
    market: "RU",
    ownership_status: "review",
    usage_type: "land_plot",
  },
  {
    id: "4",
    address: "Казань, ул. Техническая, 25",
    cadastral_number: "16:50:090201:442",
    object_type: "premises",
    risk: "low",
    document_count: 3,
    area_sqm: 3180,
    encumbrance: false,
    first_mentioned_at: "Lease Memo",
    region: "Татарстан",
    market: "RU",
    ownership_status: "registered",
    usage_type: "industrial",
  },
  {
    id: "5",
    address: "Dubai Industrial City, Plot A-114",
    cadastral_number: "DLD-IC-22119",
    object_type: "land",
    risk: "medium",
    document_count: 4,
    area_sqm: 19100,
    encumbrance: null,
    first_mentioned_at: "Regional Asset Note",
    region: "Dubai",
    market: "UAE",
    ownership_status: "review",
    usage_type: "land_plot",
  },
  {
    id: "6",
    address: "Варшава, ul. Prosta 18",
    cadastral_number: "PL-WA-77821",
    object_type: "premises",
    risk: "medium",
    document_count: 2,
    area_sqm: 2140,
    encumbrance: false,
    first_mentioned_at: "Subsidiary Property Note",
    region: "Warsaw",
    market: "EU",
    ownership_status: "review",
    usage_type: "office",
  },
  {
    id: "7",
    address: "Екатеринбург, ул. Промышленная, 41",
    cadastral_number: "66:41:0203004:778",
    object_type: "construction",
    risk: "high",
    document_count: 5,
    area_sqm: 16800,
    encumbrance: true,
    first_mentioned_at: "Capex Addendum",
    region: "Свердловская область",
    market: "RU",
    ownership_status: "review",
    usage_type: "industrial",
  },
  {
    id: "8",
    address: "Новосибирск, ул. Станционная, 59",
    cadastral_number: "54:35:101235:64",
    object_type: "building",
    risk: "low",
    document_count: 4,
    area_sqm: 9800,
    encumbrance: false,
    first_mentioned_at: "Property Register",
    region: "Новосибирская область",
    market: "RU",
    ownership_status: "registered",
    usage_type: "warehouse",
  },
];

const EXTRA_OBJECTS: RealEstateObjectAggregate[] = Array.from({ length: 20 }).map((_, index) => {
  const regions = [
    "Москва",
    "Московская область",
    "Санкт-Петербург",
    "Татарстан",
    "Краснодарский край",
    "Свердловская область",
    "Самарская область",
    "Dubai",
    "Abu Dhabi",
    "Warsaw",
  ];
  const objectTypes: RealEstateObjectType[] = [
    "land",
    "building",
    "premises",
    "construction",
    "unfinished",
  ];
  const usageTypes: RealEstateObjectAggregate["usage_type"][] = [
    "office",
    "warehouse",
    "land_plot",
    "industrial",
    "retail",
    "mixed",
  ];

  const id = String(index + 9);
  const region = regions[index % regions.length];
  const object_type = objectTypes[index % objectTypes.length];
  const area = 1200 + index * 850;
  const hasEncumbrance = index % 4 === 0 ? true : index % 5 === 0 ? null : false;
  const risk: RealEstateRisk =
    hasEncumbrance === true ? "high" : index % 3 === 0 ? "medium" : "low";

  return {
    id,
    address: `${region}, Demo Property ${id}`,
    cadastral_number: `DEMO-RE-${id}`,
    object_type,
    risk,
    document_count: 2 + (index % 5),
    area_sqm: area,
    encumbrance: hasEncumbrance,
    first_mentioned_at: "Demo Asset Register",
    region,
    market:
      region === "Dubai" || region === "Abu Dhabi"
        ? "UAE"
        : region === "Warsaw"
          ? "EU"
          : "RU",
    ownership_status:
      index % 6 === 0 ? "review" : index % 11 === 0 ? "not_confirmed" : "registered",
    usage_type: usageTypes[index % usageTypes.length],
  };
});

export const DEMO_OBJECTS: RealEstateObjectAggregate[] = [...BASE_OBJECTS, ...EXTRA_OBJECTS];

const BASE_DETAILS: Record<string, RealEstateObjectDetail> = {
  "1": {
    id: "1",
    shortDescription:
      "Офисное здание, выявленное в основном пакете документов сделки; присутствуют признаки залога и требуется сопоставление с регистрационными записями.",
    documents: [
      {
        id: "d-1",
        title: "SPA",
        documentType: "Transaction agreement",
        section: "§ 2.1 / Property perimeter",
        mentionRole: "Core asset",
      },
      {
        id: "d-2",
        title: "Disclosure Letter",
        documentType: "Disclosure",
        section: "Real estate schedule",
        mentionRole: "Disclosed encumbered asset",
      },
      {
        id: "d-3",
        title: "Mortgage Agreement",
        documentType: "Security document",
        section: "Object description",
        mentionRole: "Pledged property",
      },
    ],
    registry: {
      registrySource: "ЕГРН",
      ownershipStatus: "Право зарегистрировано",
      ownerName: "ООО «Демо Недвижимость»",
      cadastralNumber: "77:01:0004012:1456",
      objectTypeLabel: "Здание",
      areaLabel: "12 450 кв. м",
      addressLabel: "Москва, ул. Лесная, д. 12, стр. 3",
    },
    encumbrances: {
      hasEncumbrances: "yes",
      mortgage: "yes",
      arrest: "no",
      easement: "review",
      notes: [
        "В документах сделки присутствует ипотечный документ.",
        "Требуется проверить объём обеспеченного обязательства и актуальный статус записи.",
        "По сервитуту требуется ручная верификация по реестровой выписке.",
      ],
    },
    legalChecks: {
      titleChain: "review",
      registryMatch: "ok",
      zoning: "review",
      notes: [
        "Цепочка титула требует проверки по историческим документам.",
        "Параметры объекта по площади и адресу в целом совпадают с раскрытием.",
      ],
    },
    mapContext: {
      region: "Москва",
      district: "ЦАО",
      geoNote: "Актив находится в деловом районе, используется как офисный объект.",
    },
  },
  "2": {
    id: "2",
    shortDescription:
      "Складской объект с понятным профилем использования и без явных признаков зарегистрированных ограничений в demo-сценарии.",
    documents: [
      {
        id: "d-4",
        title: "Asset Schedule",
        documentType: "Annex",
        section: "Warehouse assets",
        mentionRole: "Owned asset",
      },
      {
        id: "d-5",
        title: "Operational Memo",
        documentType: "Internal memo",
        section: "Logistics footprint",
        mentionRole: "Distribution center",
      },
    ],
    registry: {
      registrySource: "ЕГРН",
      ownershipStatus: "Право зарегистрировано",
      ownerName: "ООО «Логистика Парк»",
      cadastralNumber: "50:10:0010203:884",
      objectTypeLabel: "Здание",
      areaLabel: "28 700 кв. м",
      addressLabel: "Московская область, Химки, Логистический проезд, 8",
    },
    encumbrances: {
      hasEncumbrances: "no",
      mortgage: "no",
      arrest: "no",
      easement: "no",
      notes: [
        "В раскрытии сделки не выявлены явные указания на ограничения права.",
        "Для production-проверки требуется подтверждение по реестровой выписке.",
      ],
    },
    legalChecks: {
      titleChain: "ok",
      registryMatch: "ok",
      zoning: "ok",
      notes: [
        "Основные атрибуты объекта согласуются между disclosure и реестровым контуром.",
      ],
    },
    mapContext: {
      region: "Московская область",
      district: "Химки",
      geoNote: "Объект относится к логистической инфраструктуре компании.",
    },
  },
  "3": {
    id: "3",
    shortDescription:
      "Земельный участок с повышенным уровнем риска: требуется отдельная проверка ограничений права и полноты правоустанавливающих документов.",
    documents: [
      {
        id: "d-6",
        title: "Asset Schedule #3",
        documentType: "Asset annex",
        section: "Land plots",
        mentionRole: "Land asset",
      },
      {
        id: "d-7",
        title: "Encumbrance Note",
        documentType: "Legal note",
        section: "Registry remarks",
        mentionRole: "Potentially encumbered plot",
      },
    ],
    registry: {
      registrySource: "ЕГРН",
      ownershipStatus: "Требуется верификация",
      ownerName: "АО «Северный Девелопмент»",
      cadastralNumber: "78:14:0007689:31",
      objectTypeLabel: "Земельный участок",
      areaLabel: "45 200 кв. м",
      addressLabel: "Санкт-Петербург, Пулковское шоссе, участок 17",
    },
    encumbrances: {
      hasEncumbrances: "review",
      mortgage: "review",
      arrest: "no",
      easement: "yes",
      notes: [
        "Есть признаки ограничений использования участка.",
        "Требуется проверить сервитуты и допустимое использование по градостроительному контуру.",
      ],
    },
    legalChecks: {
      titleChain: "review",
      registryMatch: "review",
      zoning: "issue",
      notes: [
        "По категории и разрешённому использованию нужен отдельный юридический анализ.",
        "В описании объекта есть риск неполного совпадения с реестровой записью.",
      ],
    },
    mapContext: {
      region: "Санкт-Петербург",
      district: "Московский район",
      geoNote: "Участок связан с развитием производственной площадки.",
    },
  },
};

const generateFallbackDetail = (
  object: RealEstateObjectAggregate
): RealEstateObjectDetail => ({
  id: object.id,
  shortDescription:
    "Демонстрационная карточка объекта недвижимости. В production-режиме здесь будет собираться описание из документов сделки, реестровых данных и внутренних баз компании.",
  documents: [
    {
      id: `doc-${object.id}-1`,
      title: "Asset Register",
      documentType: "Internal register",
      section: "Property list",
      mentionRole: "Identified object",
    },
    {
      id: `doc-${object.id}-2`,
      title: "Disclosure Note",
      documentType: "Disclosure",
      section: "Property references",
      mentionRole: "Referenced asset",
    },
  ],
  registry: {
    registrySource:
      object.market === "RU"
        ? "ЕГРН"
        : object.market === "UAE"
          ? "Local land registry"
          : "National property registry",
    ownershipStatus:
      object.ownership_status === "registered"
        ? "Право подтверждено"
        : object.ownership_status === "review"
          ? "Требуется верификация"
          : "Не подтверждено",
    ownerName: "Demo Property Owner",
    cadastralNumber: object.cadastral_number ?? "—",
    objectTypeLabel:
      object.object_type === "land"
        ? "Земельный участок"
        : object.object_type === "building"
          ? "Здание"
          : object.object_type === "premises"
            ? "Помещение"
            : object.object_type === "construction"
              ? "Сооружение"
              : object.object_type === "unfinished"
                ? "Объект незавершённого строительства"
                : "Неопределённый объект",
    areaLabel: object.area_sqm ? `${object.area_sqm.toLocaleString("ru-RU")} кв. м` : "—",
    addressLabel: object.address ?? "—",
  },
  encumbrances: {
    hasEncumbrances:
      object.encumbrance === true ? "yes" : object.encumbrance === false ? "no" : "review",
    mortgage: object.encumbrance === true ? "review" : "no",
    arrest: "no",
    easement: object.object_type === "land" ? "review" : "no",
    notes: [
      "Карточка сформирована из demo-данных для проверки split-view и внутреннего скролла.",
      "В боевом режиме здесь будут результаты реестровой проверки и анализ ограничений права.",
    ],
  },
  legalChecks: {
    titleChain: object.risk === "high" ? "review" : "ok",
    registryMatch: object.ownership_status === "registered" ? "ok" : "review",
    zoning:
      object.object_type === "land" || object.object_type === "unfinished" ? "review" : "ok",
    notes: [
      "Требуется сопоставление данных disclosure с внешним registry source и внутренним реестром активов.",
    ],
  },
  mapContext: {
    region: object.region,
    district: object.region,
    geoNote:
      "Демо-геоконтекст. В production-режиме может использоваться карта, кластеризация и сверка по адресным данным.",
  },
});

const DEMO_DETAILS: Record<string, RealEstateObjectDetail> = DEMO_OBJECTS.reduce(
  (acc, item) => {
    acc[item.id] = BASE_DETAILS[item.id] ?? generateFallbackDetail(item);
    return acc;
  },
  {} as Record<string, RealEstateObjectDetail>
);

// ---------------------------------------------------------------------------
// Shared UI
// ---------------------------------------------------------------------------

const CardShell: React.FC<{
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  rightSlot?: React.ReactNode;
  bodyClassName?: string;
  className?: string;
}> = ({ title, eyebrow, children, rightSlot, bodyClassName = "", className = "" }) => (
  <section
    className={[
      "flex min-h-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm",
      className,
    ].join(" ")}
  >
    <div className="shrink-0 px-5">
      <div className="flex items-start justify-between gap-4 py-4">
        <div className="min-w-0">
          {eyebrow ? (
            <>
              <h2 className="text-base font-semibold text-[var(--text-primary)]">{eyebrow}</h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">{title}</p>
            </>
          ) : (
            <h2 className="text-base font-semibold text-[var(--text-primary)]">{title}</h2>
          )}
        </div>
        {rightSlot}
      </div>
      <div className="border-t border-[var(--border-subtle)]" />
    </div>

    <div className={["min-h-0 flex-1 px-5 py-4", bodyClassName].join(" ")}>
      {children}
    </div>
  </section>
);

const FeatureCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  description: string;
}> = ({ icon, title, description }) => (
  <div className="flex h-full flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
    <div className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--accent-primary)]">
      {icon}
    </div>
    <div>
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{description}</p>
    </div>
  </div>
);

const Badge: React.FC<{
  children: React.ReactNode;
  tone?: "neutral" | "success" | "high" | "medium" | "low";
}> = ({ children, tone = "neutral" }) => {
  const toneClass = {
    neutral:
      "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
    success:
      "border-[color:color-mix(in_srgb,var(--accent-primary)_24%,transparent)] bg-[color:color-mix(in_srgb,var(--accent-primary)_10%,transparent)] text-[var(--accent-primary)]",
    high:
      "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]",
    medium:
      "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]",
    low:
      "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
  }[tone];

  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
        toneClass,
      ].join(" ")}
    >
      {children}
    </span>
  );
};

const PrimaryButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({
  className = "",
  children,
  ...props
}) => (
  <button
    {...props}
    className={[
      "inline-flex items-center justify-center rounded-xl bg-[var(--accent-primary)] px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-95",
      className,
    ].join(" ")}
  >
    {children}
  </button>
);

const SecondaryButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({
  className = "",
  children,
  ...props
}) => (
  <button
    {...props}
    className={[
      "inline-flex items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-2.5 text-sm font-medium text-[var(--text-primary)] transition hover:bg-[var(--bg-elevated-soft)]",
      className,
    ].join(" ")}
  >
    {children}
  </button>
);

const KpiCard: React.FC<{
  label: string;
  value: string;
  hint?: string;
  accent?: boolean;
  onClick?: () => void;
}> = ({ label, value, hint, accent = false, onClick }) => {
  const isInteractive = typeof onClick === "function";

  const content = (
    <>
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        {label}
      </p>
      <p
        className={[
          "mt-1 text-2xl font-semibold tabular-nums",
          accent ? "text-[var(--color-error-text)]" : "text-[var(--text-primary)]",
          isInteractive
            ? "underline decoration-transparent transition group-hover:decoration-current"
            : "",
        ].join(" ")}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">{hint}</p>
      ) : null}
    </>
  );

  if (!isInteractive) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className="group rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 text-left shadow-sm transition hover:bg-[var(--bg-elevated-soft)]"
    >
      {content}
    </button>
  );
};

const RankedListCard: React.FC<{
  title: string;
  items: Array<{
    name: string;
    subtitle: string;
    value: string;
  }>;
}> = ({ title, items }) => (
  <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
    <div className="border-b border-[var(--border-subtle)] px-4 py-3">
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
    </div>
    <div className="divide-y divide-[var(--border-subtle)]">
      {items.map((item, index) => (
        <div key={`${item.name}-${index}`} className="flex items-center gap-3 px-4 py-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)] text-[12px] font-semibold text-[var(--text-primary)]">
            {index + 1}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-[var(--text-primary)]">{item.name}</p>
            <p className="text-[12px] text-[var(--text-muted)]">{item.subtitle}</p>
          </div>
          <div className="shrink-0 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {item.value}
          </div>
        </div>
      ))}
    </div>
  </div>
);

const RegionStructureCard: React.FC<{
  items: Array<{
    region: string;
    count: number;
  }>;
}> = ({ items }) => {
  const total = items.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="space-y-3 px-4 py-4">
        {items.map((item) => {
          const share = total > 0 ? Math.round((item.count / total) * 100) : 0;
          return (
            <div key={item.region}>
              <div className="mb-1 flex items-center justify-between gap-3">
                <p className="text-sm text-[var(--text-primary)]">{item.region}</p>
                <p className="text-[12px] font-medium tabular-nums text-[var(--text-muted)]">
                  {item.count} · {share}%
                </p>
              </div>
              <div className="h-2 rounded-full bg-[var(--bg-elevated-soft)]">
                <div
                  className="h-2 rounded-full bg-[var(--accent-primary)]"
                  style={{ width: `${share}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const CriticalObjectsTable: React.FC<{
  items: Array<{
    name: string;
    region: string;
    reasons: string[];
  }>;
}> = ({ items }) => (
  <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-[var(--bg-elevated-soft)]">
          <tr>
            <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Объект</th>
            <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Регион</th>
            <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
              Основания критичности
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.name} className="border-t border-[var(--border-subtle)] align-top">
              <td className="px-4 py-3 font-medium text-[var(--text-primary)]">{item.name}</td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">{item.region}</td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">
                <ul className="space-y-1">
                  {item.reasons.map((reason) => (
                    <li key={reason} className="flex gap-2">
                      <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-error)]" />
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

const DrilldownModal: React.FC<{
  title: string;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}> = ({ title, open, onClose, children }) => {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6">
      <div className="max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">
        <div className="flex items-center justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-[var(--text-primary)]">{title}</h3>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Демонстрационный drilldown по выбранному показателю
            </p>
          </div>
          <SecondaryButton onClick={onClose}>Закрыть</SecondaryButton>
        </div>
        <div className="max-h-[calc(85vh-84px)] overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
};

const ExportMenuButton: React.FC<{
  label: string;
  open: boolean;
  onToggle: () => void;
  onSelect: (format: ExportFormat) => void;
}> = ({ label, open, onToggle, onSelect }) => (
  <div className="relative">
    <SecondaryButton onClick={onToggle} className="gap-2">
      <span>{label}</span>
      <span className="text-[10px] text-[var(--text-muted)]">▼</span>
    </SecondaryButton>

    {open ? (
      <div className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[160px] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl">
        <div className="border-b border-[var(--border-subtle)] px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Формат сохранения
          </p>
        </div>
        <div className="p-2">
          {[
            { key: "excel", label: "Excel" },
            { key: "docx", label: "Docx" },
            { key: "pdf", label: "Pdf" },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => onSelect(item.key as ExportFormat)}
              className="flex w-full items-center rounded-xl px-3 py-2 text-left text-sm text-[var(--text-primary)] transition hover:bg-[var(--bg-elevated-soft)]"
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
    ) : null}
  </div>
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const objectTypeLabel = (value: RealEstateObjectType): string => {
  switch (value) {
    case "land":
      return "Земельный участок";
    case "building":
      return "Здание";
    case "premises":
      return "Помещение";
    case "construction":
      return "Сооружение";
    case "unfinished":
      return "Незавершённое строительство";
    default:
      return "Неопределённо";
  }
};

const objectTypeShortLabel = (value: RealEstateObjectType): string => {
  switch (value) {
    case "land":
      return "Земля";
    case "building":
      return "Здание";
    case "premises":
      return "Помещение";
    case "construction":
      return "Сооружение";
    case "unfinished":
      return "Незавершёнка";
    default:
      return "Unknown";
  }
};

const riskBadgeTone = (value: "yes" | "no" | "review"): "high" | "low" | "medium" => {
  if (value === "yes") return "high";
  if (value === "review") return "medium";
  return "low";
};

const riskBadgeLabel = (value: "yes" | "no" | "review"): string => {
  if (value === "yes") return "Yes";
  if (value === "review") return "Review";
  return "No";
};

const buildRiskMeta = (
  item: RealEstateObjectAggregate
): { label: string; tone: "high" | "medium" | "low"; rank: number } => {
  if (
    item.risk === "high" ||
    item.encumbrance === true ||
    item.ownership_status === "not_confirmed"
  ) {
    return { label: "Высокий", tone: "high", rank: 3 };
  }

  if (item.risk === "medium" || item.ownership_status === "review") {
    return { label: "Средний", tone: "medium", rank: 2 };
  }

  return { label: "Низкий", tone: "low", rank: 1 };
};

const checkTone = (value: "ok" | "review" | "issue"): "low" | "medium" | "high" => {
  if (value === "issue") return "high";
  if (value === "review") return "medium";
  return "low";
};

const checkLabel = (value: "ok" | "review" | "issue"): string => {
  if (value === "issue") return "Issue";
  if (value === "review") return "Review";
  return "OK";
};

const getAriaSort = (
  sort: SortState,
  key: SortKey
): "ascending" | "descending" | "none" => {
  if (sort.key !== key) return "none";
  return sort.direction === "asc" ? "ascending" : "descending";
};

const sortIcon = (sort: SortState, key: SortKey): string => {
  if (sort.key !== key) return "↕";
  return sort.direction === "asc" ? "↑" : "↓";
};

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
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    <path
      d="M7.5 10.5l1.5 1.5 3.5-3.5"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

// ---------------------------------------------------------------------------
// Intro screen
// ---------------------------------------------------------------------------

const IntroScreen: React.FC<{
  onOpenDemo: () => void;
}> = ({ onOpenDemo }) => {
  return (
    <div className="flex min-h-0 flex-col lg:h-full lg:overflow-hidden">
      {/* Internal scroll на desktop (lg+), на mobile tabpanel скроллит */}
      <div className="min-h-0 flex-1 lg:overflow-y-auto pr-1">
        <div className="space-y-4">
          <CardShell
            eyebrow="Демонстрационный сценарий работы раздела"
            title="Как будет выглядеть анализ недвижимого имущества"
            rightSlot={<Badge tone="success">Preview</Badge>}
          >
            <p className="max-w-4xl text-sm leading-6 text-[var(--text-secondary)]">
              Этот раздел будет автоматически выявлять объекты недвижимого имущества в документах
              сделки, сопоставлять их с реестровыми и внутренними источниками, а затем формировать
              рабочую область для юридического анализа прав, обременений и реестрового статуса.
            </p>
          </CardShell>

          <CardShell eyebrow="Как это будет работать" title="Основной сценарий обработки объектов">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <FeatureCard
                icon={<IconBuilding />}
                title="Выявление объектов"
                description="Система извлекает адреса, кадастровые номера, площади и описания объектов из документов сделки."
              />
              <FeatureCard
                icon={<IconCadaster />}
                title="Реестровая верификация"
                description="Выявленные объекты сопоставляются с внешними registry sources и внутренним реестром активов."
              />
              <FeatureCard
                icon={<IconEncumbrance />}
                title="Юридическая проверка"
                description="Интерфейс показывает ownership status, encumbrances, title issues и документные ссылки по каждому объекту."
              />
            </div>
          </CardShell>

          <CardShell eyebrow="Источники данных" title="Внешние и внутренние источники по недвижимости">
            <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-[var(--bg-elevated-soft)]">
                    <tr>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                        Юрисдикция
                      </th>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                        Источники
                      </th>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                        Что проверяется
                      </th>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                        Комментарий
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {COVERAGE_ROWS.map((row) => (
                      <tr
                        key={row.jurisdiction}
                        className="border-t border-[var(--border-subtle)] align-top"
                      >
                        <td className="px-4 py-3 text-[var(--text-primary)]">
                          {row.jurisdiction}
                        </td>
                        <td className="px-4 py-3 text-[var(--text-secondary)]">
                          {row.registrySources}
                        </td>
                        <td className="px-4 py-3 text-[var(--text-secondary)]">
                          {row.whatChecked}
                        </td>
                        <td className="px-4 py-3 text-[var(--text-secondary)]">
                          {row.remarks}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </CardShell>
        </div>
      </div>

      <div className="mt-4 shrink-0 border-t border-[var(--border-subtle)] pt-4">
        <PrimaryButton onClick={onOpenDemo} className="w-full sm:w-auto">
          Перейти на демостраницу работы блока
        </PrimaryButton>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Table header
// ---------------------------------------------------------------------------

const SortableHeader: React.FC<{
  label: string;
  sortKey: SortKey;
  currentSort: SortState;
  onSort: (key: SortKey) => void;
  className?: string;
}> = ({ label, sortKey, currentSort, onSort, className = "" }) => (
  <th
    scope="col"
    className={["px-4 py-3 font-semibold text-[var(--text-primary)]", className].join(" ")}
    aria-sort={getAriaSort(currentSort, sortKey)}
  >
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      className="inline-flex items-center gap-2 text-left transition hover:text-[var(--accent-primary)]"
      title={`Сортировать по колонке ${label}`}
    >
      <span>{label}</span>
      <span className="text-[11px] text-[var(--text-muted)]" aria-hidden="true">
        {sortIcon(currentSort, sortKey)}
      </span>
    </button>
  </th>
);

// ---------------------------------------------------------------------------
// Registry table
// ---------------------------------------------------------------------------

const RealEstateTable: React.FC<{
  items: RealEstateObjectAggregate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  sort: SortState;
  onSort: (key: SortKey) => void;
}> = ({ items, selectedId, onSelect, sort, onSort }) => (
  // Dual-mode scroll contract:
  // Mobile (<lg): content-driven height, таблица в потоке, tabpanel скроллит
  // Desktop (lg+): h-full + overflow-auto, internal scroll внутри таблицы
  <div className="rounded-2xl border border-[var(--border)] lg:h-full lg:min-h-0 lg:overflow-auto">
    <table className="min-w-full text-left text-sm">
      <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
        <tr>
          <SortableHeader
            label="№"
            sortKey="index"
            currentSort={sort}
            onSort={onSort}
            className="w-14"
          />
          <SortableHeader
            label="Адрес / объект"
            sortKey="address"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Регион"
            sortKey="region"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Тип"
            sortKey="objectType"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Площадь"
            sortKey="area"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Документы"
            sortKey="documentCount"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Обременение"
            sortKey="encumbrance"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Риск"
            sortKey="risk"
            currentSort={sort}
            onSort={onSort}
          />
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => {
          const isSelected = item.id === selectedId;
          const risk = buildRiskMeta(item);

          return (
            <tr
              key={item.id}
              className={[
                "border-t border-[var(--border-subtle)] transition",
                isSelected
                  ? "bg-[color:color-mix(in_srgb,var(--accent-primary)_7%,var(--bg-card))]"
                  : "hover:bg-[var(--bg-elevated-soft)]",
              ].join(" ")}
            >
              <td className="px-4 py-3 tabular-nums text-[var(--text-muted)]">{index + 1}</td>
              <td className="px-4 py-3">
                <button type="button" onClick={() => onSelect(item.id)} className="text-left">
                  <span className="block text-sm font-medium text-[var(--accent-primary)] underline decoration-transparent transition hover:decoration-current">
                    {item.address ?? "Без адреса"}
                  </span>
                  <span className="mt-1 block text-[12px] text-[var(--text-muted)]">
                    {item.cadastral_number ?? "Кадастровый номер не указан"}
                  </span>
                </button>
              </td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">{item.region}</td>
              <td className="px-4 py-3 text-[var(--text-secondary)]">
                {objectTypeShortLabel(item.object_type)}
              </td>
              <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                {item.area_sqm ? `${item.area_sqm.toLocaleString("ru-RU")} м²` : "—"}
              </td>
              <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                {item.document_count}
              </td>
              <td className="px-4 py-3">
                <Badge
                  tone={
                    item.encumbrance === true
                      ? "high"
                      : item.encumbrance === false
                        ? "low"
                        : "medium"
                  }
                >
                  {item.encumbrance === true ? "Да" : item.encumbrance === false ? "Нет" : "Проверка"}
                </Badge>
              </td>
              <td className="px-4 py-3">
                <Badge tone={risk.tone}>{risk.label}</Badge>
              </td>
            </tr>
          );
        })}
        <tr aria-hidden="true">
          <td colSpan={8} className="h-2 bg-transparent" />
        </tr>
      </tbody>
    </table>
  </div>
);

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

const RealEstateDetailPanel: React.FC<{
  object: RealEstateObjectAggregate;
  detail: RealEstateObjectDetail;
  onClose: () => void;
}> = ({ object, detail, onClose }) => (
  <div className="space-y-4 pb-2">
    <CardShell
      eyebrow="Карточка объекта"
      title="Детальная информация по объекту недвижимости"
      rightSlot={
        <div className="flex items-center gap-2">
          <Badge tone={buildRiskMeta(object).tone}>{buildRiskMeta(object).label}</Badge>
          <SecondaryButton onClick={onClose} className="px-3 py-2">
            Закрыть
          </SecondaryButton>
        </div>
      }
    >
      <div className="space-y-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-semibold text-[var(--text-primary)]">
              {detail.registry.addressLabel}
            </p>
            <Badge>{object.region}</Badge>
            <Badge>{objectTypeLabel(object.object_type)}</Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            {detail.shortDescription}
          </p>
        </div>
      </div>
    </CardShell>

    <CardShell
      eyebrow="Упоминания в документах"
      title="Документы сделки, в которых фигурирует объект"
    >
      <div className="space-y-3">
        {detail.documents.map((doc) => (
          <div
            key={doc.id}
            className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-[var(--text-primary)]">{doc.title}</p>
              <Badge>{doc.documentType}</Badge>
              <Badge>{doc.section}</Badge>
            </div>
            <div className="mt-2 text-sm text-[var(--text-secondary)]">
              <span className="font-medium text-[var(--text-primary)]">Role:</span> {doc.mentionRole}
            </div>
          </div>
        ))}
      </div>
    </CardShell>

    <CardShell
      eyebrow="Registry snapshot"
      title="Ключевые атрибуты объекта по реестровому и документному контуру"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Registry source
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {detail.registry.registrySource}
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {detail.registry.ownershipStatus}
          </p>
        </div>

        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Owner
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {detail.registry.ownerName}
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {detail.registry.cadastralNumber}
          </p>
        </div>

        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Object type
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {detail.registry.objectTypeLabel}
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{detail.registry.areaLabel}</p>
        </div>

        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Address
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-primary)]">
            {detail.registry.addressLabel}
          </p>
        </div>
      </div>
    </CardShell>

    <CardShell eyebrow="Обременения" title="Ипотека, аресты, сервитуты и иные ограничения">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Encumbrances
          </p>
          <div className="mt-2">
            <Badge tone={riskBadgeTone(detail.encumbrances.hasEncumbrances)}>
              {riskBadgeLabel(detail.encumbrances.hasEncumbrances)}
            </Badge>
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Mortgage
          </p>
          <div className="mt-2">
            <Badge tone={riskBadgeTone(detail.encumbrances.mortgage)}>
              {riskBadgeLabel(detail.encumbrances.mortgage)}
            </Badge>
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Arrest
          </p>
          <div className="mt-2">
            <Badge tone={riskBadgeTone(detail.encumbrances.arrest)}>
              {riskBadgeLabel(detail.encumbrances.arrest)}
            </Badge>
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Easement
          </p>
          <div className="mt-2">
            <Badge tone={riskBadgeTone(detail.encumbrances.easement)}>
              {riskBadgeLabel(detail.encumbrances.easement)}
            </Badge>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
        <p className="text-sm font-semibold text-[var(--text-primary)]">Encumbrance notes</p>
        <ul className="mt-2 space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
          {detail.encumbrances.notes.map((note) => (
            <li key={note} className="flex gap-2">
              <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-warning)]" />
              <span>{note}</span>
            </li>
          ))}
        </ul>
      </div>
    </CardShell>

    <CardShell eyebrow="Legal checks" title="Title chain, registry match и zoning / land use">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Title chain
          </p>
          <div className="mt-2">
            <Badge tone={checkTone(detail.legalChecks.titleChain)}>
              {checkLabel(detail.legalChecks.titleChain)}
            </Badge>
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Registry match
          </p>
          <div className="mt-2">
            <Badge tone={checkTone(detail.legalChecks.registryMatch)}>
              {checkLabel(detail.legalChecks.registryMatch)}
            </Badge>
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Zoning / use
          </p>
          <div className="mt-2">
            <Badge tone={checkTone(detail.legalChecks.zoning)}>
              {checkLabel(detail.legalChecks.zoning)}
            </Badge>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
        <p className="text-sm font-semibold text-[var(--text-primary)]">Legal notes</p>
        <ul className="mt-2 space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
          {detail.legalChecks.notes.map((note) => (
            <li key={note} className="flex gap-2">
              <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-primary)]" />
              <span>{note}</span>
            </li>
          ))}
        </ul>
      </div>
    </CardShell>

    <CardShell eyebrow="Карта / контекст" title="Региональный и географический контур объекта">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Region
          </p>
          <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {detail.mapContext.region}
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {detail.mapContext.district}
          </p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Geo note
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            {detail.mapContext.geoNote}
          </p>
        </div>
      </div>
    </CardShell>
  </div>
);

// ---------------------------------------------------------------------------
// Demo screen
// ---------------------------------------------------------------------------

const DemoScreen: React.FC<{
  onBack: () => void;
}> = ({ onBack }) => {
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [drilldown, setDrilldown] = React.useState<DrilldownKind>(null);
  const [openExportMenu, setOpenExportMenu] = React.useState<ExportMenuKind>(null);
  const [sort, setSort] = React.useState<SortState>({
    key: "index",
    direction: "asc",
  });

  const totalObjects = DEMO_OBJECTS.length;
  const totalLand = DEMO_OBJECTS.filter((item) => item.object_type === "land").length;
  const totalBuildingsAndPremises = DEMO_OBJECTS.filter(
    (item) => item.object_type === "building" || item.object_type === "premises"
  ).length;
  const totalEncumbered = DEMO_OBJECTS.filter((item) => item.encumbrance === true).length;

  const topByArea = [...DEMO_OBJECTS]
    .sort((a, b) => (b.area_sqm ?? 0) - (a.area_sqm ?? 0))
    .slice(0, 5)
    .map((item) => ({
      name: item.address ?? "Без адреса",
      subtitle: item.region,
      value: item.area_sqm ? `${item.area_sqm.toLocaleString("ru-RU")} м²` : "—",
    }));

  const encumberedObjects = DEMO_OBJECTS.filter((item) => item.encumbrance === true).map((item) => ({
    name: item.address ?? "Без адреса",
    subtitle: item.cadastral_number ?? "Нет номера",
    value: buildRiskMeta(item).label,
  }));

  const regionMap = new Map<string, number>();
  for (const item of DEMO_OBJECTS) {
    regionMap.set(item.region, (regionMap.get(item.region) ?? 0) + 1);
  }

  const regionStructure = [...regionMap.entries()]
    .map(([region, count]) => ({ region, count }))
    .sort((a, b) => b.count - a.count);

  const criticalObjects = DEMO_OBJECTS
    .map((item) => {
      const reasons: string[] = [];
      if (item.encumbrance === true) reasons.push("Выявлены признаки обременения.");
      if (item.risk === "high") reasons.push("Объект имеет высокий уровень риска.");
      if (item.ownership_status === "not_confirmed") {
        reasons.push("Право собственности не подтверждено.");
      }
      if (item.object_type === "unfinished") {
        reasons.push("Объект незавершённого строительства требует отдельной проверки.");
      }

      return reasons.length > 0
        ? {
            name: item.address ?? "Без адреса",
            region: item.region,
            reasons,
          }
        : null;
    })
    .filter(Boolean) as Array<{ name: string; region: string; reasons: string[] }>;

  const sortedObjects = React.useMemo(() => {
    const withIndex = DEMO_OBJECTS.map((item, index) => ({
      ...item,
      originalIndex: index + 1,
      riskMeta: buildRiskMeta(item),
    }));

    const sorted = [...withIndex].sort((a, b) => {
      let comparison = 0;

      switch (sort.key) {
        case "index":
          comparison = a.originalIndex - b.originalIndex;
          break;
        case "address":
          comparison = (a.address ?? "").localeCompare(b.address ?? "");
          break;
        case "region":
          comparison = a.region.localeCompare(b.region);
          break;
        case "objectType":
          comparison = objectTypeLabel(a.object_type).localeCompare(objectTypeLabel(b.object_type));
          break;
        case "area":
          comparison = (a.area_sqm ?? 0) - (b.area_sqm ?? 0);
          break;
        case "documentCount":
          comparison = a.document_count - b.document_count;
          break;
        case "encumbrance":
          comparison = Number(a.encumbrance === true) - Number(b.encumbrance === true);
          break;
        case "risk":
          comparison = a.riskMeta.rank - b.riskMeta.rank;
          break;
        default:
          comparison = 0;
      }

      return sort.direction === "asc" ? comparison : -comparison;
    });

    return sorted.map(({ originalIndex: _originalIndex, riskMeta: _riskMeta, ...item }) => item);
  }, [sort]);

  const selectedObject = selectedId
    ? DEMO_OBJECTS.find((item) => item.id === selectedId) ?? null
    : null;

  const selectedDetail = selectedObject ? DEMO_DETAILS[selectedObject.id] : null;

  const handleExport = (format: ExportFormat) => {
    setOpenExportMenu(null);
    window.alert(`Сохранить список объектов недвижимости: ${format.toUpperCase()}`);
  };

  const handleSort = (key: SortKey) => {
    setSort((prev) => {
      if (prev.key === key) {
        return {
          key,
          direction: prev.direction === "asc" ? "desc" : "asc",
        };
      }

      return {
        key,
        direction: "asc",
      };
    });
  };

  return (
    <div className="flex min-h-0 flex-col lg:h-full lg:overflow-hidden">
      <div className="mb-4 shrink-0 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            Выявленные объекты недвижимости
          </h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Реестр активов, выявленных в документах сделки, с верификацией по реестровому и
            юридическому контуру
          </p>
        </div>
        <SecondaryButton onClick={onBack}>Назад к описанию</SecondaryButton>
      </div>

      <div className="mb-4 shrink-0 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Объектов выявлено"
          value={`${totalObjects}`}
          hint="Нажмите, чтобы открыть географию"
          onClick={() => setDrilldown("geography")}
        />
        <KpiCard label="Земельных участков" value={`${totalLand}`} hint="В составе реестра" />
        <KpiCard
          label="Зданий и помещений"
          value={`${totalBuildingsAndPremises}`}
          hint="Нажмите, чтобы открыть топ по площади"
          onClick={() => setDrilldown("area_top")}
        />
        <KpiCard
          label="С обременениями"
          value={`${totalEncumbered}`}
          hint="Нажмите, чтобы открыть список"
          accent
          onClick={() => setDrilldown("encumbrances")}
        />
      </div>

      <div className="min-h-0 flex-1">
        {selectedObject && selectedDetail ? (
          <CardShell
            eyebrow="Рабочая область анализа"
            title="Реестр объектов и карточка выбранного объекта"
            rightSlot={
              <div className="flex items-center gap-2">
                <ExportMenuButton
                  label="Сохранить список объектов"
                  open={openExportMenu === "list"}
                  onToggle={() => setOpenExportMenu((prev) => (prev === "list" ? null : "list"))}
                  onSelect={handleExport}
                />
                <SecondaryButton onClick={() => setSelectedId(null)}>
                  Закрыть карточку
                </SecondaryButton>
              </div>
            }
            bodyClassName="min-h-0 flex-1 overflow-hidden p-0"
            className="h-full min-h-0"
          >
            <div className="grid h-full min-h-0 grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1.1fr)_minmax(420px,560px)]">
              <div className="min-h-0 lg:overflow-hidden border-b border-[var(--border-subtle)] xl:border-b-0 xl:border-r">                <div className="flex h-full min-h-0 flex-col p-5">
                  <div className="mb-4 shrink-0">
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      Реестр объектов
                    </p>
                    <p className="mt-1 text-sm text-[var(--text-muted)]">
                      Выберите объект в таблице, чтобы просмотреть детальную карточку справа
                    </p>
                  </div>

                  {/* overflow-hidden на desktop для internal scroll, на mobile таблица в потоке */}
                  <div className="min-h-0 flex-1 lg:overflow-hidden">
                    <RealEstateTable
                      items={sortedObjects}
                      selectedId={selectedId}
                      onSelect={setSelectedId}
                      sort={sort}
                      onSort={handleSort}
                    />
                  </div>
                </div>
              </div>

              <div className="min-h-0 lg:overflow-hidden">
                <div className="h-full min-h-0 overflow-y-auto p-5">
                  <RealEstateDetailPanel
                    object={selectedObject}
                    detail={selectedDetail}
                    onClose={() => setSelectedId(null)}
                  />
                </div>
              </div>
            </div>
          </CardShell>
        ) : (
          <CardShell
            eyebrow="Реестр объектов"
            title="Недвижимое имущество, выявленное в документах сделки"
            rightSlot={
              <ExportMenuButton
                label="Сохранить список объектов"
                open={openExportMenu === "list"}
                onToggle={() => setOpenExportMenu((prev) => (prev === "list" ? null : "list"))}
                onSelect={handleExport}
              />
            }
            bodyClassName="min-h-0 flex-1 overflow-hidden"
            className="h-full min-h-0"
          >
            <div className="flex h-full min-h-0 flex-col">
              <div className="mb-3 shrink-0">
                <p className="text-sm text-[var(--text-secondary)]">
                  В демонстрационном реестре добавлено больше объектов, чтобы таблица имела
                  собственную внутреннюю прокрутку.
                </p>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">
                <RealEstateTable
                  items={sortedObjects}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  sort={sort}
                  onSort={handleSort}
                />
              </div>
            </div>
          </CardShell>
        )}
      </div>

      <DrilldownModal
        open={drilldown !== null}
        onClose={() => setDrilldown(null)}
        title={
          drilldown === "geography"
            ? "География выявленных объектов"
            : drilldown === "encumbrances"
              ? "Объекты с признаками обременений"
              : drilldown === "area_top"
                ? "Топ-5 объектов по площади"
                : "Критические объекты недвижимости"
        }
      >
        {drilldown === "geography" ? (
          <RegionStructureCard items={regionStructure} />
        ) : drilldown === "encumbrances" ? (
          <RankedListCard title="Объекты с признаками обременений" items={encumberedObjects} />
        ) : drilldown === "area_top" ? (
          <RankedListCard title="Топ-5 объектов по площади" items={topByArea} />
        ) : (
          <CriticalObjectsTable items={criticalObjects} />
        )}
      </DrilldownModal>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const RealEstateTab: React.FC<RealEstateTabProps> = ({
  dealId: _dealId,
  currentRunId: _currentRunId,
}) => {
  const [mode, setMode] = React.useState<PreviewMode>("intro");

  return (
    // Dual-mode scroll contract:
    // Mobile (<lg): no height constraint, content-driven, tabpanel scrolls
    // Desktop (lg+): h-full + overflow-hidden, internal scroll
    <div className="flex min-h-0 flex-col lg:h-full lg:overflow-hidden">
      {mode === "intro" ? (
        <IntroScreen onOpenDemo={() => setMode("demo")} />
      ) : (
        <DemoScreen onBack={() => setMode("intro")} />
      )}
    </div>
  );
};

export default RealEstateTab;


