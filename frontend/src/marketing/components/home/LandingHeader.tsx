// src/marketing/components/home/LandingHeader.tsx

import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import SteloomWordmark from "../shared/primitives/SteloomWordmark";
import { landingContent } from "../../content/landingContent";
import { useScroll } from "../../context/ScrollContext";

const LandingHeader: React.FC = () => {
  const navigate = useNavigate();
  const { scrolled, scrollToTop, headerTheme } = useScroll();

  const effectiveTheme: "light" | "dark" =
    scrolled ? (headerTheme === "dark" ? "dark" : "light") : "dark";

  const isDark = effectiveTheme === "dark";

  const showLightSurface = scrolled && !isDark;
  const showDarkSurface = scrolled && isDark;

  const headerStyle: React.CSSProperties = {
    background: showLightSurface
      ? "rgba(248,247,244,0.92)"
      : showDarkSurface
        ? "rgba(0,0,0,0.65)"
        : "transparent",
    backdropFilter:
      showLightSurface || showDarkSurface
        ? "blur(20px) saturate(160%)"
        : "none",
    WebkitBackdropFilter:
      showLightSurface || showDarkSurface
        ? "blur(20px) saturate(160%)"
        : "none",
    borderBottom: showLightSurface
      ? "1px solid rgba(229,226,218,0.8)"
      : showDarkSurface
        ? "1px solid rgba(255,255,255,0.1)"
        : "1px solid transparent",
  };

  const logoColor = isDark ? "#ffffff" : "#111827";

  const navLinkStyle: React.CSSProperties = isDark
    ? { color: "rgba(255,255,255,0.9)" }
    : { color: "rgb(120 113 108)" };

  const navLinkHoverColor = isDark ? "#ffffff" : "#111827";
  const navLinkBaseColor = isDark
    ? "rgba(255,255,255,0.9)"
    : "rgb(120 113 108)";

  const loginStyle: React.CSSProperties = isDark
    ? {
        border: "1px solid rgba(255,255,255,0.3)",
        background: "rgba(255,255,255,0.12)",
        color: "rgba(255,255,255,0.95)",
      }
    : {
        border: "1px solid #E5E2DA",
        background: "white",
        color: "rgb(87 83 78)",
      };

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={headerStyle}
    >
      <div className="mx-auto flex h-[68px] w-full max-w-[1280px] items-center justify-between px-4 sm:px-6 lg:px-10 xl:px-12">
        {/* Logo */}
        <button
          type="button"
          onClick={scrollToTop}
          aria-label="steloom — наверх"
          className="flex min-w-0 items-center bg-transparent p-0 transition-opacity hover:opacity-60"
          style={{ color: logoColor, border: "none", cursor: "pointer" }}
        >
          <SteloomWordmark height={40} />
        </button>

        {/* Nav */}
        <nav className="hidden items-center gap-7 lg:flex">
          {landingContent.nav.map((item) => (
            <Link
              key={item.label}
              to={item.href}
              className="text-sm transition-colors"
              style={navLinkStyle}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = navLinkHoverColor;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = navLinkBaseColor;
              }}
            >
              {item.label}
            </Link>
          ))}

          <Link
            to="/about"
            className="text-sm transition-colors"
            style={navLinkStyle}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = navLinkHoverColor;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = navLinkBaseColor;
            }}
          >
            О нас
          </Link>
        </nav>

        {/* Buttons */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Войти — secondary, нейтральная */}
          <button
            type="button"
            onClick={() => navigate("/login")}
            className="hidden rounded-full px-4 py-2 text-sm transition-all sm:inline-flex"
            style={loginStyle}
            onMouseEnter={(e) => {
              if (isDark) {
                e.currentTarget.style.color = "#ffffff";
                e.currentTarget.style.borderColor = "rgba(255,255,255,0.45)";
                e.currentTarget.style.background = "rgba(255,255,255,0.18)";
              } else {
                e.currentTarget.style.color = "#111827";
                e.currentTarget.style.borderColor = "#d6d3d1";
              }
            }}
            onMouseLeave={(e) => {
              if (isDark) {
                e.currentTarget.style.color = "rgba(255,255,255,0.95)";
                e.currentTarget.style.borderColor = "rgba(255,255,255,0.3)";
                e.currentTarget.style.background = "rgba(255,255,255,0.12)";
              } else {
                e.currentTarget.style.color = "rgb(87 83 78)";
                e.currentTarget.style.borderColor = "#E5E2DA";
                e.currentTarget.style.background = "white";
              }
            }}
          >
            Войти
          </button>

          {/* Запросить демо — primary CTA, всегда зелёная */}
          <Link
            to="/demo"
            className="cta-primary sm:px-5"
          >
            <span className="hidden sm:inline">Запросить демо</span>
            <span className="sm:hidden">Демо</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </header>
  );
};

export default LandingHeader;