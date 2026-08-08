// src/marketing/components/shared/MobileMenu.tsx
import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { SITE_NAV, SITE_CTA, SOLUTIONS_MEGA_MENU } from "../../content/siteNav";
import { useContactModal } from "../../context/ContactModalContext";

interface MobileMenuProps {
  open: boolean;
  onClose: () => void;
}

const MobileMenu: React.FC<MobileMenuProps> = ({ open, onClose }) => {
  const location = useLocation();
  const { openContactModal } = useContactModal();

  const isOnSolutions = location.pathname.startsWith("/solutions");
  const [solutionsOpen, setSolutionsOpen] = useState<boolean>(isOnSolutions);

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
        aria-label="Мобильное меню"
        className="fixed inset-y-0 right-0 z-50 flex w-[320px] max-w-[85vw] flex-col bg-[#FAF8F5] shadow-2xl transition-transform duration-300 ease-out"
        style={{ transform: open ? "translateX(0)" : "translateX(100%)" }}
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
                      className="flex items-center rounded-xl px-4 py-3 text-[1rem] font-medium transition-colors"
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
                    className="flex w-full items-center justify-between rounded-xl px-4 py-3 text-[1rem] font-medium transition-colors"
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
                        <div className="mt-1 mb-2 ml-3 border-l border-[#E8E4DD] pl-3">
                          {SOLUTIONS_MEGA_MENU.sections.map((section) => (
                            <div key={section.title} className="pt-3 first:pt-1">
                              <p className="px-4 pb-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-[#A8A29E]">
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
                                        className="flex items-center rounded-lg px-4 py-2 text-[0.9375rem] transition-colors"
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
        </nav>

        {/* Bottom CTAs */}
        <div
          className="shrink-0 border-t border-[#E8E4DD] p-4 space-y-2"
          style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
        >
          <button
            type="button"
            onClick={handleDemoClick}
            className="cta-primary w-full justify-center"
          >
            {SITE_CTA.demo.label}
          </button>
          <a
            href={SITE_CTA.login.href}
            className="flex w-full items-center justify-center rounded-full border border-[#E8E4DD] bg-white px-5 py-3.5 text-[0.9375rem] font-medium text-[#1A1917] transition-colors hover:border-[#D6D0C7]"
          >
            {SITE_CTA.login.label}
          </a>
        </div>
      </div>
    </>
  );
};

export default MobileMenu;

