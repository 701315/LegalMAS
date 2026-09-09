// frontend/src/marketing/components/shared/SiteHeader.tsx
import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Menu, ChevronDown, X, Globe } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useTranslation } from "react-i18next";
import SteloomWordmark from "./primitives/SteloomWordmark";
import MobileMenu from "./MobileMenu";
import { useContactModal } from "../../context/ContactModalContext";
import { useMediaQuery } from "../../hooks/useMediaQuery";

interface SiteHeaderProps {
  variant?: "landing" | "default";
  hideLogin?: boolean;
}

// ─────────────────────────────────────────────────────────────
// Константы
// ─────────────────────────────────────────────────────────────
const DESKTOP_MEDIA_QUERY = "(min-width: 1024px)";
const SCROLLED_THRESHOLD_PX = 32;
const HERO_EXIT_OFFSET_PX = 68;
const MOBILE_BG = "rgba(250, 248, 245, 0.98)";
const MOBILE_FG = "#1A1917";
const MOBILE_SHADOW = "0 1px 0 rgba(0, 0, 0, 0.04)";

// Доступные языки
const LANGUAGES = [
  { code: "ru", label: "RU", name: "Русский" },
  { code: "en", label: "EN", name: "English" },
  { code: "tr", label: "TR", name: "Türkçe" },
  { code: "ar", label: "AR", name: "العربية" },
] as const;

// ─────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────
const SiteHeader: React.FC<SiteHeaderProps> = ({
  variant = "default",
  hideLogin = false,
}) => {
  const location = useLocation();
  const currentPath = location.pathname;
  const { t, i18n } = useTranslation("marketing");
  const { openContactModal } = useContactModal();
  const isDesktop = useMediaQuery(DESKTOP_MEDIA_QUERY);

  const [mobileOpen, setMobileOpen] = useState(false);
  const [solutionsOpen, setSolutionsOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [isLandingZone, setIsLandingZone] = useState(variant === "landing");
  const solutionsRef = useRef<HTMLDivElement>(null);
  const langRef = useRef<HTMLDivElement>(null);

  // ── Навигация из i18n ─────────────────────────────────────
  const SITE_NAV = [
    { label: t("nav.platform"), href: "/capabilities" },
    { label: t("nav.security"), href: "/security" },
    { label: t("nav.solutions"), href: "/solutions" },
    { label: t("nav.about"), href: "/about" },
  ];

  const SOLUTIONS_MEGA_MENU = {
    sections: [
      {
        title: t("megaMenu.byDirection.title"),
        items: [
          { label: t("megaMenu.byDirection.maDueDiligence.label"), href: "/solutions/ma-due-diligence", description: t("megaMenu.byDirection.maDueDiligence.description") },
          { label: t("megaMenu.byDirection.contractReview.label"), href: "/solutions/contract-review", description: t("megaMenu.byDirection.contractReview.description") },
          { label: t("megaMenu.byDirection.compliance.label"), href: "/solutions/compliance", description: t("megaMenu.byDirection.compliance.description") },
          { label: t("megaMenu.byDirection.internalAudit.label"), href: "/solutions/internal-audit", description: t("megaMenu.byDirection.internalAudit.description") },
        ],
      },
      {
        title: t("megaMenu.byTeam.title"),
        items: [
          { label: t("megaMenu.byTeam.lawFirms.label"), href: "/solutions/law-firms", description: t("megaMenu.byTeam.lawFirms.description") },
          { label: t("megaMenu.byTeam.corporateLegal.label"), href: "/solutions/corporate-legal", description: t("megaMenu.byTeam.corporateLegal.description") },
          { label: t("megaMenu.byTeam.auditCompliance.label"), href: "/solutions/audit-compliance", description: t("megaMenu.byTeam.auditCompliance.description") },
        ],
      },
      {
        title: t("megaMenu.enrichment.title"),
        items: [
          { label: t("megaMenu.enrichment.counterparties.label"), href: "/solutions/counterparties", description: t("megaMenu.enrichment.counterparties.description") },
          { label: t("megaMenu.enrichment.realEstate.label"), href: "/solutions/real-estate", description: t("megaMenu.enrichment.realEstate.description") },
        ],
      },
    ],
  };

  // ─ Scroll & landing zone detection ────────────────────────
  useEffect(() => {
    const hero = document.getElementById("landing-hero");
    let ticking = false;
    const update = () => {
      setScrolled(window.scrollY > SCROLLED_THRESHOLD_PX);
      if (variant === "landing" && hero) {
        const rect = hero.getBoundingClientRect();
        setIsLandingZone(rect.bottom > HERO_EXIT_OFFSET_PX);
      } else {
        setIsLandingZone(false);
      }
      ticking = false;
    };
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [variant, currentPath]);

  // ── Click outside to close mega menu ───────────────────────
  useEffect(() => {
    if (!solutionsOpen) return;
    const clickOutside = (e: MouseEvent) => {
      if (solutionsRef.current && !solutionsRef.current.contains(e.target as Node)) {
        setSolutionsOpen(false);
      }
    };
    document.addEventListener("mousedown", clickOutside);
    return () => document.removeEventListener("mousedown", clickOutside);
  }, [solutionsOpen]);

  // ── Click outside to close language dropdown ───────────────
  useEffect(() => {
    if (!langOpen) return;
    const clickOutside = (e: MouseEvent) => {
      if (langRef.current && !langRef.current.contains(e.target as Node)) {
        setLangOpen(false);
      }
    };
    document.addEventListener("mousedown", clickOutside);
    return () => document.removeEventListener("mousedown", clickOutside);
  }, [langOpen]);

  // ── Desktop-only derived state ─────────────────────────────
  const isDarkDesktop = isDesktop && isLandingZone;
  const desktopColorPrimary = isDarkDesktop ? "#FFFFFF" : "#1A1917";
  const desktopColorSecondary = isDarkDesktop
    ? "rgba(255, 255, 255, 0.7)"
    : "#78756F";
  const desktopBgHeader = isDarkDesktop
    ? scrolled
      ? "rgba(26, 25, 23, 0.85)"
      : "transparent"
    : "rgba(250, 248, 245, 0.95)";
  const desktopHeaderHeight = scrolled ? 60 : 72;

  const headerBg = isDesktop ? desktopBgHeader : MOBILE_BG;
  const headerFg = isDesktop ? desktopColorPrimary : MOBILE_FG;
  const headerBlur =
    isDesktop && isDarkDesktop && !scrolled ? "none" : "blur(20px)";
  const headerShadow = isDesktop
    ? !isDarkDesktop && scrolled
      ? "0 4px 20px rgba(0,0,0,0.06)"
      : "none"
    : MOBILE_SHADOW;
  const headerHeight = isDesktop ? desktopHeaderHeight : 64;

  const navItemStyle: React.CSSProperties = {
    fontSize: "15px",
    fontWeight: 500,
    letterSpacing: "-0.01em",
    lineHeight: 1,
    display: "inline-flex",
    alignItems: "center",
    transition: "color 0.3s ease, opacity 0.3s ease",
    border: "none",
    background: "none",
    padding: 0,
    cursor: "pointer",
  };

  // ── Language switcher handler ──────────────────────────────
  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
    setLangOpen(false);
    // Опционально: можно добавить редирект на URL с префиксом языка
    // когда будет реализован URL-based routing
  };

  return (
    <>
      <header
        className="fixed top-0 left-0 right-0 z-[9999]"
        style={{
          backgroundColor: headerBg,
          color: headerFg,
          backdropFilter: headerBlur,
          WebkitBackdropFilter: headerBlur,
          boxShadow: headerShadow,
        }}
      >
        <div
          className="mx-auto flex w-full items-center justify-between px-6 lg:px-8"
          style={{
            maxWidth: "1400px",
            height: `${headerHeight}px`,
          }}
        >
          <Link
            to="/"
            aria-label={t("header.homeLabel")}
            style={{
              color: headerFg,
              display: "flex",
              alignItems: "center",
            }}
          >
            <SteloomWordmark height={32} />
          </Link>

          <nav className="hidden items-center gap-8 lg:flex">
            {SITE_NAV.map((item) => {
              const isSolutionsTrigger = item.href === "/solutions";
              const isParentActive =
                isSolutionsTrigger && currentPath.startsWith("/solutions");
              const isActive = currentPath === item.href || isParentActive;

              if (!isSolutionsTrigger) {
                return (
                  <Link
                    key={item.href}
                    to={item.href}
                    className="relative group"
                    style={{
                      ...navItemStyle,
                      color: isActive
                        ? desktopColorPrimary
                        : desktopColorSecondary,
                    }}
                  >
                    {item.label}
                    {isActive && (
                      <span
                        className="absolute -bottom-1.5 left-0 right-0 h-[1px]"
                        style={{
                          backgroundColor: desktopColorPrimary,
                          opacity: 0.4,
                        }}
                      />
                    )}
                  </Link>
                );
              }

              return (
                <div
                  key="solutions"
                  ref={solutionsRef}
                  className="relative flex items-center"
                >
                  <button
                    type="button"
                    onClick={() => setSolutionsOpen((v) => !v)}
                    aria-expanded={solutionsOpen}
                    aria-haspopup="true"
                    style={{
                      ...navItemStyle,
                      color: isActive
                        ? desktopColorPrimary
                        : desktopColorSecondary,
                    }}
                  >
                    {item.label}
                    <ChevronDown
                      className={`ml-1.5 h-3.5 w-3.5 transition-transform duration-300 ${
                        solutionsOpen ? "rotate-180" : ""
                      }`}
                      strokeWidth={2.5}
                    />
                    {isActive && (
                      <span
                        className="absolute -bottom-1.5 left-0 right-1.5 h-[1px]"
                        style={{
                          backgroundColor: desktopColorPrimary,
                          opacity: 0.4,
                        }}
                      />
                    )}
                  </button>
                  <AnimatePresence>
                    {solutionsOpen && (
                      <motion.div
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 12 }}
                        className="absolute left-0 top-full mt-5 w-[1140px] rounded-2xl bg-white shadow-[0_40px_80px_rgba(0,0,0,0.15)] p-12 border border-gray-100 overflow-hidden"
                      >
                        <div className="grid grid-cols-3 gap-12 relative z-10">
                          {SOLUTIONS_MEGA_MENU.sections.map((s) => (
                            <div key={s.title}>
                              <h3 className="mb-6 text-[11px] font-bold uppercase tracking-[0.2em] text-gray-400">
                                {s.title}
                              </h3>
                              <ul className="space-y-5">
                                {s.items.map((i) => (
                                  <li key={i.href}>
                                    <Link
                                      to={i.href}
                                      onClick={() => setSolutionsOpen(false)}
                                      className="group block"
                                    >
                                      <p className="text-[15px] font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent-primary)] transition-colors">
                                        {i.label}
                                      </p>
                                      <p className="text-[13px] text-gray-500 font-normal leading-relaxed mt-1">
                                        {i.description}
                                      </p>
                                    </Link>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </nav>

          <div className="hidden items-center gap-5 lg:flex">
            {!hideLogin && (
              <button
                type="button"
                onClick={() => {
                  window.location.href = "https://app.steloom.com/login";
                }}
                style={{ ...navItemStyle, color: desktopColorSecondary }}
              >
                {t("cta.login")}
              </button>
            )}

            {/* Language Switcher */}
            <div className="relative" ref={langRef}>
              <button
                type="button"
                onClick={() => setLangOpen((v) => !v)}
                aria-expanded={langOpen}
                aria-label="Select language"
                className="flex items-center gap-1.5 px-2.5 py-2 text-sm font-medium transition-colors"
                style={{
                  color: desktopColorSecondary,
                  borderRadius: "8px",
                }}
              >
                <Globe className="h-4 w-4" />
                <span>{i18n.language.toUpperCase()}</span>
                <ChevronDown
                  className={`h-3 w-3 transition-transform duration-200 ${
                    langOpen ? "rotate-180" : ""
                  }`}
                />
              </button>

              <AnimatePresence>
                {langOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 8 }}
                    className="absolute right-0 mt-2 w-40 rounded-xl bg-white shadow-lg border border-[var(--border-color)] py-1 z-[10000]"
                    style={{
                      boxShadow: "0 10px 40px rgba(0,0,0,0.1)",
                    }}
                  >
                    {LANGUAGES.map((lang) => (
                      <button
                        key={lang.code}
                        onClick={() => changeLanguage(lang.code)}
                        className={`block w-full text-left px-4 py-2.5 text-sm transition-colors ${
                          i18n.language === lang.code
                            ? "bg-[#F5EBE7] text-[var(--accent-primary)] font-medium"
                            : "text-[var(--text-primary)] hover:bg-[var(--bg-surface)]"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span>{lang.name}</span>
                          <span
                            className="text-xs font-medium"
                            style={{
                              color:
                                i18n.language === lang.code
                                  ? "#C86B52"
                                  : "#A8A29E",
                            }}
                          >
                            {lang.label}
                          </span>
                        </div>
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <button
              type="button"
              onClick={openContactModal}
              className="cta-primary h-10 px-5"
              style={{ fontSize: "14px", fontWeight: 500 }}
            >
              {t("cta.demo")}
              <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
            </button>
          </div>

          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? t("header.closeMenu") : t("header.openMenu")}
            aria-expanded={mobileOpen}
            className="lg:hidden p-2 relative z-[10000]"
            style={{ color: headerFg }}
          >
            {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
      </header>
      <MobileMenu open={mobileOpen} onClose={() => setMobileOpen(false)} />
    </>
  );
};

export default SiteHeader;

