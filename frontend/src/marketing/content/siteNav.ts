// src/marketing/content/siteNav.ts

export interface NavItem {
  label: string;
  href: string;
}

export interface MegaMenuItem {
  label: string;
  href: string;
  description?: string;
}

export interface MegaMenuSection {
  title: string;
  items: MegaMenuItem[];
}

export interface MegaMenuConfig {
  sections: MegaMenuSection[];
}

// ЕДИНСТВЕННЫЙ источник навигации для всего сайта
export const SITE_NAV: NavItem[] = [
  { label: "Платформа", href: "/capabilities" },
  { label: "Безопасность", href: "/security" },
  { label: "Сценарии использования", href: "/solutions" },
  { label: "О нас", href: "/about" },
];

export const SITE_CTA = {
  demo: { label: "Запросить демо", href: "/demo" },
  login: { label: "Войти", href: "/login" },
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Мега-меню для «Сценарии использования»
// ─────────────────────────────────────────────────────────────────────────────

export const SOLUTIONS_MEGA_MENU: MegaMenuConfig = {
  sections: [
    {
      title: "По направлению",
      items: [
        {
          label: "M&A и Due Diligence",
          href: "/solutions/ma-due-diligence",
          description: "Анализ полной data room по единым правилам",
        },
        {
          label: "Анализ договоров",
          href: "/solutions/contract-review",
          description: "Проверка договоров с единым стандартом",
        },
        {
          label: "Комплаенс и контроль",
          href: "/solutions/compliance",
          description: "Проверка соответствия внутренним политикам",
        },
        {
          label: "Внутренний аудит",
          href: "/solutions/internal-audit",
          description: "Проверка договорного массива",
        },
      ],
    },
    {
      title: "По типу команды",
      items: [
        {
          label: "Юридические фирмы",
          href: "/solutions/law-firms",
          description: "Масштабирование экспертизы",
        },
        {
          label: "Корпоративные юристы",
          href: "/solutions/corporate-legal",
          description: "Единый стандарт проверки",
        },
        {
          label: "Внутренний аудит",
          href: "/solutions/audit-compliance",
          description: "Воспроизводимый процесс",
        },
      ],
    },
    // НОВАЯ СЕКЦИЯ:
    {
      title: "Расширенный анализ",
      items: [
        {
          label: "Анализ контрагентов",
          href: "/solutions/counterparties",
          description: "Обогащение данных и проверка UBO",
        },
        {
          label: "Анализ активов",
          href: "/solutions/real-estate",
          description: "Проверка прав и обременений",
        },
      ],
    },
  ],
};


