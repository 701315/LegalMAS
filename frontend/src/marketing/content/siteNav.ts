// src/marketing/content/siteNav.ts

export interface NavItem {
  label: string;
  href: string;
}

export const SITE_NAV: NavItem[] = [
  { label: "Platform",  href: "/platform"  },
  { label: "Security",  href: "/security"  },
  { label: "Use Cases", href: "/use-cases" },
  { label: "About",     href: "/about"     },
];

export const SITE_CTA = {
  demo:  { label: "Request demo", href: "/demo"  },
  login: { label: "Log in",       href: "/login" },
} as const;

