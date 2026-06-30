// src/marketing/content/siteNav.ts

export interface NavItem {
  label: string;
  href: string;
}

export const SITE_NAV: NavItem[] = [
  { label: "Платформа", href: "/platform" },
  { label: "Безопасность", href: "/security" },
  { label: "Сценарии", href: "/use-cases" },
  { label: "О нас", href: "/about" },
];

export const SITE_CTA = {
  demo: { label: "Запросить демо", href: "/demo" },
  login: { label: "Войти", href: "/login" },
} as const;



