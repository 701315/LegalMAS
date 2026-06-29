// src/marketing/components/shared/SiteHeader.tsx

import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Menu } from "lucide-react";
import SteloomWordmark from "./primitives/SteloomWordmark";
import MobileMenu from "./MobileMenu";
import { SITE_NAV, SITE_CTA } from "../../content/siteNav";

// ─── Типы ────────────────────────────────────────────────────
type Theme = "light" | "dark";

interface SiteHeaderProps {
  /** Принудительная тема. Если не задана — определяется автоматически по скроллу и секции. */
  forcedTheme?: Theme;
}

// ─── Hook: следим за window scroll ───────────────────────────
function useWindowScroll(threshold = 32) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > threshold);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);

  return scrolled;
}

// ─── Hook: определяем тему по видимой секции ─────────────────
function useSectionTheme(): Theme {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const sections = document.querySelectorAll<HTMLElement>("[data-header-theme]");
    if (!sections.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Берём секцию с наибольшим intersectionRatio
        let best: { ratio: number; theme: Theme } = { ratio: 0, theme: "dark" };
        entries.forEach((entry) => {
          if (entry.intersectionRatio > best.ratio) {
            const t = (entry.target as HTMLElement).dataset.headerTheme as Theme;
            best = { ratio: entry.intersectionRatio, theme: t ?? "dark" };
          }
        });
        if (best.ratio > 0) setTheme(best.theme);
      },
      {
        threshold: [0, 0.1, 0.5, 0.9, 1],
        rootMargin: "-68px 0px 0px 0px",
      }
    );

    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, []);

  return theme;
}

// ─── Palettes ─────────────────────────────────────────────────
const PALETTE = {
  dark: {
    logo: "#ffffff",
    navBase: "rgba(255,255,255,0.75)",
    navHover: "#ffffff",
    navActive: "#ffffff",
    loginBg: "rgba(255,255,255,0.10)",
    loginBorder: "rgba(255,255,255,0.25)",
    loginColor: "rgba(255,255,255,0.90)",
    loginHoverBg: "rgba(255,255,255,0.18)",
    loginHoverBorder: "rgba(255,255,255,0.40)",
    demoBg: "rgba(255,255,255,0.15)",
    demoBorder: "rgba(255,255,255,0.25)",
    demoColor: "#ffffff",
    demoHoverBg: "rgba(255,255,255,0.25)",
    menuIcon: "rgba(255,255,255,0.80)",
    menuBorder: "rgba(255,255,255,0.20)",
    menuBg: "rgba(255,255,255,0.08)",
  },
  light: {
    logo: "#111827",
    navBase: "rgb(120,113,108)",
    navHover: "#111827",
    navActive: "#111827",
    loginBg: "white",
    loginBorder: "#E5E2DA",
    loginColor: "rgb(87,83,78)",
    loginHoverBg: "white",
    loginHoverBorder: "#d6d3d1",
    demoBg: "#111827",
    demoBorder: "transparent",
    demoColor: "white",
    demoHoverBg: "#1f2937",
    menuIcon: "rgb(87,83,78)",
    menuBorder: "#E5E2DA",
    menuBg: "white",
  },
} as const;

// ─── Компонент ────────────────────────────────────────────────
const SiteHeader: React.FC<SiteHeaderProps> = ({ forcedTheme }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const scrolled = useWindowScroll(32);
  const sectionTheme = useSectionTheme();
  const [menuOpen, setMenuOpen] = useState(false);

  const theme: Theme = forcedTheme ?? sectionTheme;
  const p = PALETTE[theme];

  // Surface стилизация
  const surface: React.CSSProperties = (() => {
    if (!scrolled) return {
      background: "transparent",
      backdropFilter: "none",
      WebkitBackdropFilter: "none",
      borderBottom: "1px solid transparent",
    };

    if (theme === "dark") return {
      background: "rgba(17,24,39,0.80)",
      backdropFilter: "blur(20px) saturate(160%)",
      WebkitBackdropFilter: "blur(20px) saturate(160%)",
      borderBottom: "1px solid rgba(255,255,255,0.08)",
    };

    return {
      background: "rgba(248,247,244,0.92)",
      backdropFilter: "blur(20px) saturate(160%)",
      WebkitBackdropFilter: "blur(20px) saturate(160%)",
      borderBottom: "1px solid rgba(229,226,218,0.80)",
    };
  })();

  return (
    <>
      <header
        className="fixed top-0 left-0 right-0 z-30 transition-all duration-300"
        style={surface}
      >
        <div className="mx-auto flex h-[68px] w-full max-w-[1280px] items-center justify-between px-4 sm:px-6 lg:px-10 xl:px-12">

          {/* ── Logo ───────────────────────────────────────── */}
          <Link
            to="/"
            aria-label="Steloom — home"
            className="flex items-center transition-opacity hover:opacity-60"
            style={{ color: p.logo }}
          >
            <SteloomWordmark height={36} />
          </Link>

          {/* ── Desktop nav ────────────────────────────────── */}
          <nav
            className="hidden items-center gap-6 lg:flex"
            aria-label="Main navigation"
          >
            {SITE_NAV.map((item) => {
              const isActive = location.pathname === item.href;
              return (
                <Link
                  key={item.href}
                  to={item.href}
                  className="relative text-sm transition-colors"
                  style={{ color: isActive ? p.navActive : p.navBase }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.color = p.navHover)
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.color =
                      isActive ? p.navActive : p.navBase)
                  }
                >
                  {item.label}
                  {/* Active underline */}
                  {isActive && (
                    <span
                      className="absolute -bottom-1 left-0 right-0 h-px rounded-full"
                      style={{ background: p.navActive, opacity: 0.4 }}
                    />
                  )}
                </Link>
              );
            })}
          </nav>

          {/* ── Desktop actions ────────────────────────────── */}
          <div className="hidden items-center gap-2 lg:flex">
            {/* Log in — контракт не меняется: всегда /login */}
            <button
              type="button"
              onClick={() => navigate(SITE_CTA.login.href)}
              className="rounded-full px-4 py-2 text-sm transition-all"
              style={{
                background: p.loginBg,
                border: `1px solid ${p.loginBorder}`,
                color: p.loginColor,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = p.loginHoverBg;
                e.currentTarget.style.borderColor = p.loginHoverBorder;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = p.loginBg;
                e.currentTarget.style.borderColor = p.loginBorder;
              }}
            >
              {SITE_CTA.login.label}
            </button>

            {/* Request demo */}
            <Link
              to={SITE_CTA.demo.href}
              className="inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-medium transition-all"
              style={{
                background: p.demoBg,
                border: `1px solid ${p.demoBorder}`,
                color: p.demoColor,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = p.demoHoverBg;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = p.demoBg;
              }}
            >
              Request demo
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          {/* ── Mobile: demo + burger ──────────────────────── */}
          <div className="flex items-center gap-2 lg:hidden">
            <Link
              to={SITE_CTA.demo.href}
              className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-all"
              style={{
                background: p.demoBg,
                border: `1px solid ${p.demoBorder}`,
                color: p.demoColor,
              }}
            >
              Demo
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>

            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Open menu"
              className="inline-flex h-9 w-9 items-center justify-center rounded-full transition-colors"
              style={{
                background: p.menuBg,
                border: `1px solid ${p.menuBorder}`,
                color: p.menuIcon,
              }}
            >
              <Menu className="h-4 w-4" />
            </button>
          </div>

        </div>
      </header>

      {/* Mobile menu drawer */}
      <MobileMenu open={menuOpen} onClose={() => setMenuOpen(false)} />
    </>
  );
};

export default SiteHeader;


