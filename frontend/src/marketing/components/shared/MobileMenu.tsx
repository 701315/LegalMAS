// src/marketing/components/shared/MobileMenu.tsx

import React, { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { X } from "lucide-react";
import { SITE_NAV, SITE_CTA } from "../../content/siteNav";

interface MobileMenuProps {
  open: boolean;
  onClose: () => void;
}

const MobileMenu: React.FC<MobileMenuProps> = ({ open, onClose }) => {
  const location = useLocation();

  // Закрываем при навигации
  useEffect(() => {
    onClose();
  }, [location.pathname]);

  // Блокируем скролл body пока меню открыто
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      {/* Backdrop */}
      <div
        aria-hidden="true"
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity duration-300"
        style={{ opacity: open ? 1 : 0, pointerEvents: open ? "auto" : "none" }}
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Navigation menu"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col bg-[#F8F7F4] shadow-2xl transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
        style={{ transform: open ? "translateX(0)" : "translateX(100%)" }}
      >
        {/* Header */}
        <div className="flex h-[68px] items-center justify-between border-b border-[#E5E2DA] px-6">
          <span className="text-sm font-medium text-stone-500">Menu</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#E5E2DA] bg-white text-stone-500 transition-colors hover:text-stone-950"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Nav links */}
        <nav className="flex flex-col gap-1 px-4 pt-4">
          {SITE_NAV.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <Link
                key={item.href}
                to={item.href}
                className="flex items-center rounded-2xl px-4 py-3.5 text-base font-medium transition-colors"
                style={{
                  color: isActive ? "#111827" : "rgb(120,113,108)",
                  background: isActive ? "rgba(0,0,0,0.04)" : "transparent",
                }}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Bottom actions */}
        <div className="border-t border-[#E5E2DA] p-4 space-y-2">
          <Link
            to={SITE_CTA.demo.href}
            className="flex w-full items-center justify-center rounded-2xl bg-[#111827] px-5 py-3.5 text-sm font-medium text-white transition-colors hover:bg-[#1f2937]"
          >
            {SITE_CTA.demo.label}
          </Link>
          <Link
            to={SITE_CTA.login.href}
            className="flex w-full items-center justify-center rounded-2xl border border-[#E5E2DA] bg-white px-5 py-3.5 text-sm text-stone-600 transition-colors hover:text-stone-950"
          >
            {SITE_CTA.login.label}
          </Link>
        </div>
      </div>
    </>
  );
};

export default MobileMenu;


