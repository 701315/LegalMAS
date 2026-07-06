// src/marketing/content/siteNav.ts

export interface NavItem {
  label: string;
  href: string;
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

// Юридические ссылки для футера
export const LEGAL_LINKS: NavItem[] = [
  { label: "Условия использования", href: "/legal/terms" },
  { label: "Политика конфиденциальности", href: "/legal/privacy" },
  { label: "Политика cookie", href: "/legal/cookies" },
  { label: "Политика безопасности", href: "/legal/security" },
];


