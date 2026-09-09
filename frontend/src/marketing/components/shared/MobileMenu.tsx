// src/marketing/components/shared/MobileMenu.tsx
import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, Globe } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useTranslation } from "react-i18next";
import { useContactModal } from "../../context/ContactModalContext";

interface MobileMenuProps {
  open: boolean;
  onClose: () => void;
}

// Доступные языки
const LANGUAGES = [
  { code: "ru", label: "RU", name: "Русский" },
  { code: "en", label: "EN", name: "English" },
  { code: "tr", label: "TR", name: "Türkçe" },
  { code: "ar", label: "AR", name: "العربية" },
] as const;

const MobileMenu: React.FC<MobileMenuProps> = ({ open, onClose }) => {
  const location = useLocation();
  const { t, i18n } = useTranslation("marketing");
  const { openContactModal } = useContactModal();
  const isOnSolutions = location.pathname.startsWith("/solutions");
  const [solutionsOpen, setSolutionsOpen] = useState<boolean>(isOnSolutions);
  const [langOpen, setLangOpen] = useState(false);

  // Навигация из i18n
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
          { label: t("megaMenu.byDirection.maDueDiligence.label"), href: "/solutions/ma-due-diligence" },
          { label: t("megaMenu.byDirection.contractReview.label"), href: "/solutions/contract-review" },
          { label: t("megaMenu.byDirection.compliance.label"), href: "/solutions/compliance" },
          { label: t("megaMenu.byDirection.internalAudit.label"), href: "/solutions/internal-audit" },
        ],
      },
      {
        title: t("megaMenu.byTeam.title"),
        items: [
          { label: t("megaMenu.byTeam.lawFirms.label"), href: "/solutions/law-firms" },
          { label: t("megaMenu.byTeam.corporateLegal.label"), href: "/solutions/corporate-legal" },
          { label: t("megaMenu.byTeam.auditCompliance.label"), href: "/solutions/audit-compliance" },
        ],
      },
      {
        title: t("megaMenu.enrichment.title"),
        items: [
          { label: t("megaMenu.enrichment.counterparties.label"), href: "/solutions/counterparties" },
          { label: t("megaMenu.enrichment.realEstate.label"), href: "/solutions/real-estate" },
        ],
      },
    ],
  };

  // Закрывать меню при смене маршрута
  useEffect(() => {
    onClose();
  }, [location.pathname]);

  // Раскрыть solutions если пользователь на /solutions/*
  useEffect(() => {
    if (isOnSolutions) setSolutionsOpen(true);
  }, [isOnSolutions, open]);

  // Блокировать скролл body при открытом меню
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  // Закрытие по Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const handleDemoClick = () => {
    onClose();
    setTimeout(() => openContactModal(), 250);
  };

  const handleLanguageChange = (lng: string) => {
    i18n.changeLanguage(lng);
    setLangOpen(false);
  };

  // Определяем направление для drawer (RTL/LTR)
  const isRTL = i18n.language === "ar";

  return (
    <>
      {/* Backdrop */}
      <div
        aria-hidden="true"
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm transition-opacity duration-300"
        style={{ opacity: open ? 1 : 0, pointerEvents: open ? "auto" : "none" }}
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("mobileMenu.ariaLabel")}
        className="fixed inset-y-0 z-50 flex w-[320px] max-w-[85vw] flex-col bg-[var(--bg-base)] shadow-2xl transition-transform duration-300 ease-out"
        style={{
          // RTL: drawer выезжает слева, LTR: справа
          [isRTL ? "left" : "right"]: 0,
          transform: open ? "translateX(0)" : `translateX(${isRTL ? "-100%" : "100%"})`,
        }}
      >
        {/* Отступ сверху под header (высота 64px на mobile) */}
        <div className="h-16 shrink-0" />

        {/* Nav (scrollable) */}
        <nav className="flex-1 overflow-y-auto px-4 pt-2 pb-6">
          <ul className="flex flex-col gap-1">
            {SITE_NAV.map((item) => {
              const isSolutionsTrigger = item.href === "/solutions";
              if (!isSolutionsTrigger) {
                const isActive = location.pathname === item.href;
                return (
                  <li key={item.href}>
                    <Link
                      to={item.href}
                      className="flex items-center rounded-xl px-4 py-3 text-base font-medium transition-colors"
                      style={{
                        color: isActive ? "#1A1917" : "#78756F",
                        background: isActive
                          ? "rgba(0,0,0,0.04)"
                          : "transparent",
                      }}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              }
              // Аккордеон для «Сценарии использования»
              return (
                <li key="solutions">
                  <button
                    type="button"
                    onClick={() => setSolutionsOpen((v) => !v)}
                    aria-expanded={solutionsOpen}
                    aria-controls="mobile-solutions-panel"
                    className="flex w-full items-center justify-between rounded-xl px-4 py-3 text-base font-medium transition-colors"
                    style={{
                      color: isOnSolutions ? "#1A1917" : "#78756F",
                      background: isOnSolutions
                        ? "rgba(0,0,0,0.04)"
                        : "transparent",
                    }}
                  >
                    <span>{item.label}</span>
                    <ChevronDown
                      className="h-4 w-4 transition-transform duration-300"
                      style={{
                        transform: solutionsOpen
                          ? "rotate(180deg)"
                          : "rotate(0deg)",
                        color: "#A8A29E",
                      }}
                      strokeWidth={2}
                    />
                  </button>
                  <AnimatePresence initial={false}>
                    {solutionsOpen && (
                      <motion.div
                        id="mobile-solutions-panel"
                        key="panel"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{
                          height: { duration: 0.28, ease: [0.16, 1, 0.3, 1] },
                          opacity: { duration: 0.2 },
                        }}
                        className="overflow-hidden"
                      >
                        {/* RTL: border-s (start) вместо border-l (left) */}
                        <div className="mt-1 mb-2 ms-3 border-s border-[var(--border-color)] ps-3">
                          {SOLUTIONS_MEGA_MENU.sections.map((section) => (
                            <div key={section.title} className="pt-3 first:pt-1">
                              <p className="px-4 pb-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--text-muted)]">
                                {section.title}
                              </p>
                              <ul className="flex flex-col">
                                {section.items.map((sub) => {
                                  const isSubActive =
                                    location.pathname === sub.href;
                                  return (
                                    <li key={sub.href}>
                                      <Link
                                        to={sub.href}
                                        className="flex items-center rounded-lg px-4 py-2 text-body-sm transition-colors"
                                        style={{
                                          color: isSubActive
                                            ? "#1A1917"
                                            : "#78756F",
                                          background: isSubActive
                                            ? "rgba(200, 107, 82, 0.08)"
                                            : "transparent",
                                          fontWeight: isSubActive ? 600 : 500,
                                        }}
                                      >
                                        {sub.label}
                                      </Link>
                                    </li>
                                  );
                                })}
                              </ul>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </li>
              );
            })}
          </ul>

          {/* Language Switcher в мобильном меню */}
          <div className="mt-6 border-t border-[var(--border-color)] pt-4">
            <button
              type="button"
              onClick={() => setLangOpen((v) => !v)}
              className="flex w-full items-center justify-between rounded-xl px-4 py-3 text-base font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface)]"
            >
              <span className="flex items-center gap-2">
                <Globe className="h-4 w-4" />
                <span>{t("mobileMenu.language")}</span>
              </span>
              <ChevronDown
                className="h-4 w-4 transition-transform duration-300"
                style={{
                  transform: langOpen ? "rotate(180deg)" : "rotate(0deg)",
                  color: "#A8A29E",
                }}
                strokeWidth={2}
              />
            </button>

            <AnimatePresence initial={false}>
              {langOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{
                    height: { duration: 0.28, ease: [0.16, 1, 0.3, 1] },
                    opacity: { duration: 0.2 },
                  }}
                  className="overflow-hidden"
                >
                  <ul className="mt-2 space-y-1">
                    {LANGUAGES.map((lang) => (
                      <li key={lang.code}>
                        <button
                          type="button"
                          onClick={() => handleLanguageChange(lang.code)}
                          className={`flex w-full items-center justify-between rounded-lg px-4 py-2.5 text-body-sm transition-colors ${
                            i18n.language === lang.code
                              ? "bg-[#F5EBE7] text-[var(--accent-primary)] font-medium"
                              : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
                          }`}
                        >
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
                        </button>
                      </li>
                    ))}
                  </ul>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </nav>

        {/* Bottom CTAs */}
        <div
          className="shrink-0 border-t border-[var(--border-color)] p-4 space-y-2"
          style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
        >
          <button
            type="button"
            onClick={handleDemoClick}
            className="cta-primary w-full justify-center"
          >
            {t("cta.demo")}
          </button>
          <a
            href="https://app.steloom.com/login"
            className="flex w-full items-center justify-center rounded-full border border-[var(--border-color)] bg-white px-5 py-3.5 text-body-sm font-medium text-[var(--text-primary)] transition-colors hover:border-[#D6D0C7]"
          >
            {t("cta.login")}
          </a>
        </div>
      </div>
    </>
  );
};

export default MobileMenu;