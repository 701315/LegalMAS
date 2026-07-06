// src/marketing/components/shared/SiteHeader.tsx
import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Menu } from "lucide-react";
import SteloomWordmark from "./primitives/SteloomWordmark";
import MobileMenu from "./MobileMenu";
import { SITE_NAV, SITE_CTA } from "../../content/siteNav";
import { useContactModal } from "../../context/ContactModalContext";

type Theme = "light" | "dark";

interface SiteHeaderProps {
  forcedTheme?: Theme;
  hideLogin?: boolean;
}

// Утилита: нормализует путь (убирает trailing slash, кроме корня)
function normalizePath(path: string): string {
  if (path === "/") return "/";
  return path.replace(/\/+$/, "");
}

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

function useSectionTheme(): Theme {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    const sections = document.querySelectorAll<HTMLElement>("[data-header-theme]");
    if (!sections.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        let best: { ratio: number; theme: Theme } = { ratio: 0, theme: "light" };
        entries.forEach((entry) => {
          if (entry.intersectionRatio > best.ratio) {
            const t = (entry.target as HTMLElement).dataset.headerTheme as Theme;
            best = { ratio: entry.intersectionRatio, theme: t ?? "light" };
          }
        });
        if (best.ratio > 0) setTheme(best.theme);
      },
      { threshold: [0, 0.1, 0.5, 0.9, 1], rootMargin: "-68px 0px 0px 0px" }
    );
    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, []);
  return theme;
}

const SiteHeader: React.FC<SiteHeaderProps> = ({ forcedTheme, hideLogin = false }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const scrolled = useWindowScroll(32);
  const sectionTheme = useSectionTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const { openContactModal } = useContactModal();

  const theme: Theme = forcedTheme ?? sectionTheme;
  const isDark = theme === "dark";

  // Нормализованный текущий путь
  const currentPath = normalizePath(location.pathname);

  return (
    <>
      <header
        className="fixed top-0 left-0 right-0 z-30 transition-all duration-300"
        style={{
          background: scrolled
            ? isDark
              ? "rgba(26, 25, 23, 0.92)"
              : "rgba(250, 248, 245, 0.92)"
            : "transparent",
          backdropFilter: scrolled ? "blur(16px)" : "none",
          WebkitBackdropFilter: scrolled ? "blur(16px)" : "none",
          borderBottom: scrolled
            ? `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"}`
            : "1px solid transparent",
        }}
      >
        <div
          className="mx-auto flex h-[68px] w-full items-center justify-between px-6 lg:px-8"
          style={{ maxWidth: "var(--container-max-width)" }}
        >
          {/* Logo */}
          <Link
            to="/"
            aria-label="Steloom — главная"
            className="flex items-center transition-opacity hover:opacity-60"
            style={{ color: isDark ? "#FAF8F5" : "#1A1917" }}
          >
            <SteloomWordmark height={32} />
          </Link>

          {/* Desktop Nav */}
          <nav className="hidden items-center gap-8 lg:flex" aria-label="Основная навигация">
            {SITE_NAV.map((item) => {
              // ✅ Нормализованное сравнение путей
              const itemPath = normalizePath(item.href);
              const isActive = currentPath === itemPath;

              return (
                <Link
                  key={item.href}
                  to={item.href}
                  className="relative text-[0.9375rem] font-medium transition-colors"
                  style={{
                    color: isActive
                      ? isDark ? "#FAF8F5" : "#1A1917"
                      : isDark ? "rgba(250,248,245,0.65)" : "#78756F",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = isDark ? "#FAF8F5" : "#1A1917";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = isActive
                      ? isDark ? "#FAF8F5" : "#1A1917"
                      : isDark ? "rgba(250,248,245,0.65)" : "#78756F";
                  }}
                >
                  {item.label}
                  {isActive && (
                    <span
                      className="absolute -bottom-1 left-0 right-0 h-px"
                      style={{ background: isDark ? "#FAF8F5" : "#1A1917", opacity: 0.3 }}
                    />
                  )}
                </Link>
              );
            })}
          </nav>

          {/* Desktop Actions */}
          <div className="hidden items-center gap-3 lg:flex">
            {!hideLogin && (
              <button
                type="button"
                onClick={() => navigate(SITE_CTA.login.href)}
                className="rounded-full px-4 py-2 text-[0.9375rem] font-medium transition-colors"
                style={{
                  color: isDark ? "rgba(250,248,245,0.8)" : "#78756F",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = isDark ? "#FAF8F5" : "#1A1917";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = isDark ? "rgba(250,248,245,0.8)" : "#78756F";
                }}
              >
                {SITE_CTA.login.label}
              </button>
            )}
            <button type="button" onClick={openContactModal} className="cta-primary">
              {SITE_CTA.demo.label}
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Mobile */}
          <div className="flex items-center gap-2 lg:hidden">
            <button type="button" onClick={openContactModal} className="cta-primary px-4 py-2 text-sm">
              Демо
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Открыть меню"
              className="inline-flex h-9 w-9 items-center justify-center rounded-full transition-colors"
              style={{
                color: isDark ? "#FAF8F5" : "#1A1917",
              }}
            >
              <Menu className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>
      <MobileMenu open={menuOpen} onClose={() => setMenuOpen(false)} />
    </>
  );
};

export default SiteHeader;


