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

  useEffect(() => {
    onClose();
  }, [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

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
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col bg-[#FAF8F5] transition-transform duration-300 ease-out"
        style={{ transform: open ? "translateX(0)" : "translateX(100%)" }}
      >
        {/* Header */}
        <div className="flex h-[68px] items-center justify-between border-b border-[#E8E4DD] px-6">
          <span className="text-sm font-medium text-[#78756F]">Меню</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть меню"
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#E8E4DD] text-[#78756F] transition-colors hover:text-[#1A1917]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-1 px-4 pt-4">
          {SITE_NAV.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <Link
                key={item.href}
                to={item.href}
                className="flex items-center rounded-xl px-4 py-3.5 text-[1rem] font-medium transition-colors"
                style={{
                  color: isActive ? "#1A1917" : "#78756F",
                  background: isActive ? "rgba(0,0,0,0.04)" : "transparent",
                }}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex-1" />

        {/* Bottom */}
        <div className="border-t border-[#E8E4DD] p-4 space-y-2">
          <Link
            to={SITE_CTA.demo.href}
            className="cta-primary w-full justify-center"
          >
            {SITE_CTA.demo.label}
          </Link>
          <Link
            to={SITE_CTA.login.href}
            className="flex w-full items-center justify-center rounded-full border border-[#E8E4DD] bg-white px-5 py-3.5 text-[0.9375rem] font-medium text-[#1A1917] transition-colors hover:border-[#D6D0C7]"
          >
            {SITE_CTA.login.label}
          </Link>
        </div>
      </div>
    </>
  );
};

export default MobileMenu;


