// frontend/src/marketing/components/shared/SiteHeader.tsx

import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Menu, ChevronDown, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import SteloomWordmark from "./primitives/SteloomWordmark";
import MobileMenu from "./MobileMenu";
import { SITE_NAV, SITE_CTA, SOLUTIONS_MEGA_MENU } from "../../content/siteNav";
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

// Mobile-safe defaults — применяются inline, работают до загрузки CSS
const MOBILE_BG = "rgba(250, 248, 245, 0.98)";
const MOBILE_FG = "#1A1917";
const MOBILE_SHADOW = "0 1px 0 rgba(0, 0, 0, 0.04)";

// ─────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────

const SiteHeader: React.FC<SiteHeaderProps> = ({
  variant = "default",
  hideLogin = false,
}) => {
  const location = useLocation();
  const currentPath = location.pathname;
  const { openContactModal } = useContactModal();

  const isDesktop = useMediaQuery(DESKTOP_MEDIA_QUERY);

  const [mobileOpen, setMobileOpen] = useState(false);
  const [solutionsOpen, setSolutionsOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [isLandingZone, setIsLandingZone] = useState(variant === "landing");
  const solutionsRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    if (!solutionsOpen) return;

    const clickOutside = (e: MouseEvent) => {
      if (
        solutionsRef.current &&
        !solutionsRef.current.contains(e.target as Node)
      ) {
        setSolutionsOpen(false);
      }
    };

    document.addEventListener("mousedown", clickOutside);
    return () => document.removeEventListener("mousedown", clickOutside);
  }, [solutionsOpen]);

  // ── Desktop-only derived state ──
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

  // ── Итоговые значения для header ──
  // На desktop — динамические (landing/scroll-aware).
  // На mobile — фиксированные mobile-safe defaults.
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
            aria-label="Steloom — home"
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
                                      <p className="text-[15px] font-semibold text-[#1A1917] group-hover:text-[#C86B52] transition-colors">
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
                  window.location.href = SITE_CTA.login.href;
                }}
                style={{ ...navItemStyle, color: desktopColorSecondary }}
              >
                {SITE_CTA.login.label}
              </button>
            )}
            <button
              type="button"
              onClick={openContactModal}
              className="cta-primary h-10 px-5"
              style={{ fontSize: "14px", fontWeight: 500 }}
            >
              {SITE_CTA.demo.label}
              <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
            </button>
          </div>

          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? "Закрыть меню" : "Открыть меню"}
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


