// src/components/marketing/landing/LandingHeader.tsx

import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import SteloomWordmark from "../primitives/SteloomWordmark";
import { landingContent } from "../../../content/landingContent";
import { useScroll } from "../../../context/ScrollContext";

const LandingHeader: React.FC = () => {
  const navigate = useNavigate();
  const { scrolled, scrollToTop } = useScroll();

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={{
        background: scrolled ? "rgba(248,247,244,0.92)" : "transparent",
        backdropFilter: scrolled ? "blur(20px) saturate(160%)" : "none",
        WebkitBackdropFilter: scrolled ? "blur(20px) saturate(160%)" : "none",
        borderBottom: scrolled
          ? "1px solid rgba(229,226,218,0.8)"
          : "1px solid transparent",
      }}
    >
      <div className="mx-auto flex h-[68px] w-full max-w-[1280px] items-center justify-between px-4 sm:px-6 lg:px-10 xl:px-12">

        {/* Логотип */}
        <button
          type="button"
          onClick={scrollToTop}
          aria-label="steloom — наверх"
          className="flex min-w-0 items-center transition-opacity hover:opacity-60"
          style={{
            color: scrolled ? "#111827" : "white",
            background: "none",
            border: "none",
            padding: 0,
            cursor: "pointer",
          }}
        >
          <SteloomWordmark height={40} />
        </button>

        {/* Навигация */}
        <nav className="hidden items-center gap-7 lg:flex">
          {landingContent.nav.map((item) => (
            <Link
              key={item.label}
              to={item.href}
              className="text-sm transition-colors"
              style={{
                color: scrolled ? "rgb(120 113 108)" : "rgba(255,255,255,0.65)",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.color = scrolled ? "#111827" : "white")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.color = scrolled
                  ? "rgb(120 113 108)"
                  : "rgba(255,255,255,0.65)")
              }
            >
              {item.label}
            </Link>
          ))}
          <Link
            to="/about"
            className="text-sm transition-colors"
            style={{
              color: scrolled ? "rgb(120 113 108)" : "rgba(255,255,255,0.65)",
            }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.color = scrolled ? "#111827" : "white")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.color = scrolled
                ? "rgb(120 113 108)"
                : "rgba(255,255,255,0.65)")
            }
          >
            О нас
          </Link>
        </nav>

        {/* Кнопки */}
        <div className="flex items-center gap-2 sm:gap-3">

          {/* Войти */}
          <button
            type="button"
            onClick={() => navigate("/login")}
            className="hidden rounded-full px-4 py-2 text-sm transition-all sm:inline-flex"
            style={{
              border: scrolled
                ? "1px solid #E5E2DA"
                : "1px solid rgba(255,255,255,0.20)",
              background: scrolled ? "white" : "rgba(255,255,255,0.08)",
              color: scrolled ? "rgb(87 83 78)" : "rgba(255,255,255,0.70)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = scrolled ? "#111827" : "white";
              e.currentTarget.style.borderColor = scrolled
                ? "#d6d3d1"
                : "rgba(255,255,255,0.35)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = scrolled
                ? "rgb(87 83 78)"
                : "rgba(255,255,255,0.70)";
              e.currentTarget.style.borderColor = scrolled
                ? "#E5E2DA"
                : "rgba(255,255,255,0.20)";
            }}
          >
            Войти
          </button>

          {/* Запросить демо */}
          <Link
            to="/demo"
            className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all sm:px-5"
            style={{
              background: scrolled ? "#111827" : "rgba(255,255,255,0.12)",
              color: "white",
              border: scrolled
                ? "1px solid transparent"
                : "1px solid rgba(255,255,255,0.20)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = scrolled
                ? "#1f2937"
                : "rgba(255,255,255,0.22)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = scrolled
                ? "#111827"
                : "rgba(255,255,255,0.12)";
            }}
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

