import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Menu, ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import SteloomWordmark from "./primitives/SteloomWordmark";
import MobileMenu from "./MobileMenu";
import { SITE_NAV, SITE_CTA, SOLUTIONS_MEGA_MENU } from "../../content/siteNav";
import { useContactModal } from "../../context/ContactModalContext";

interface SiteHeaderProps { variant?: "landing" | "default"; hideLogin?: boolean; }

const SiteHeader: React.FC<SiteHeaderProps> = ({ variant = "default", hideLogin = false }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { openContactModal } = useContactModal();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [solutionsOpen, setSolutionsOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [isLandingZone, setIsLandingZone] = useState(variant === "landing");
  const solutionsRef = useRef<HTMLDivElement>(null);
  const currentPath = location.pathname;

  useEffect(() => {
    const hero = document.getElementById("landing-hero");
    const checkPos = () => {
      setScrolled(window.scrollY > 32);
      if (variant === "landing" && hero) {
        const rect = hero.getBoundingClientRect();
        setIsLandingZone(rect.bottom > 68);
      } else {
        setIsLandingZone(false);
      }
    };
    checkPos();
    window.addEventListener("scroll", checkPos, { passive: true });
    return () => window.removeEventListener("scroll", checkPos);
  }, [variant, currentPath]);

  useEffect(() => {
    const clickOutside = (e: MouseEvent) => {
      if (solutionsRef.current && !solutionsRef.current.contains(e.target as Node)) setSolutionsOpen(false);
    };
    if (solutionsOpen) document.addEventListener("mousedown", clickOutside);
    return () => document.removeEventListener("mousedown", clickOutside);
  }, [solutionsOpen]);

  const isDark = isLandingZone;
  const colorPrimary = isDark ? "#FFFFFF" : "#1A1917";
  const colorSecondary = isDark ? "rgba(255, 255, 255, 0.7)" : "#78756F";
  const bgHeader = isDark 
    ? (scrolled ? "rgba(26, 25, 23, 0.85)" : "transparent") 
    : "rgba(250, 248, 245, 0.95)";

  const navItemStyle = {
    fontSize: "15px",
    fontWeight: 500,
    letterSpacing: "-0.01em",
    lineHeight: "1",
    display: "inline-flex",
    alignItems: "center",
    transition: "color 0.3s ease, opacity 0.3s ease",
    border: "none",
    background: "none",
    padding: 0,
    cursor: "pointer"
  };

  return (
    <>
      <header 
        className="fixed top-0 left-0 right-0 z-[9999] transition-all duration-500"
        style={{ 
          backgroundColor: bgHeader, 
          backdropFilter: (isDark && !scrolled) ? "none" : "blur(20px)",
          boxShadow: (!isDark && scrolled) ? "0 4px 20px rgba(0,0,0,0.06)" : "none"
        }}
      >
        <div 
          className="mx-auto flex w-full items-center justify-between px-6 lg:px-8 transition-all duration-500"
          style={{ maxWidth: "1400px", height: scrolled ? "60px" : "72px" }}
        >
          <Link to="/" style={{ color: colorPrimary, display: "flex", alignItems: "center" }}>
            <SteloomWordmark height={32} />
          </Link>

          <nav className="hidden items-center gap-8 lg:flex">
            {SITE_NAV.map((item) => {
              const isSolutionsTrigger = item.href === "/solutions";
              const isParentActive = isSolutionsTrigger && currentPath.startsWith("/solutions");
              const isActive = currentPath === item.href || isParentActive;

              if (!isSolutionsTrigger) {
                return (
                  <Link 
                    key={item.href} 
                    to={item.href} 
                    className="relative group"
                    style={{ ...navItemStyle, color: isActive ? colorPrimary : colorSecondary }}
                  >
                    {item.label}
                    {isActive && (
                      <span className="absolute -bottom-1.5 left-0 right-0 h-[1px]" style={{ backgroundColor: colorPrimary, opacity: 0.4 }} />
                    )}
                  </Link>
                );
              }

              return (
                <div key="solutions" ref={solutionsRef} className="relative flex items-center">
                  <button 
                    type="button"
                    onClick={() => setSolutionsOpen(!solutionsOpen)}
                    style={{ ...navItemStyle, color: isActive ? colorPrimary : colorSecondary }}
                  >
                    {item.label}
                    <ChevronDown 
                      className={`ml-1.5 h-3.5 w-3.5 transition-transform duration-300 ${solutionsOpen ? "rotate-180" : ""}`} 
                      strokeWidth={2.5}
                    />
                    {isActive && (
                      <span className="absolute -bottom-1.5 left-0 right-1.5 h-[1px]" style={{ backgroundColor: colorPrimary, opacity: 0.4 }} />
                    )}
                  </button>
                  
                  <AnimatePresence>
                    {solutionsOpen && (
                      <motion.div 
                        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}
                        className="absolute left-0 top-full mt-5 w-[1140px] rounded-2xl bg-white shadow-[0_40px_80px_rgba(0,0,0,0.15)] p-12 border border-gray-100 overflow-hidden"
                      >
                        <div className="grid grid-cols-3 gap-12 relative z-10"> {/* Сетка на 3 колонки */}
                          {SOLUTIONS_MEGA_MENU.sections.map((s) => (
                            <div key={s.title}>
                              <h3 className="mb-6 text-[11px] font-bold uppercase tracking-[0.2em] text-gray-400">{s.title}</h3>
                              <ul className="space-y-5">
                                {s.items.map((i) => (
                                  <li key={i.href}>
                                    <Link to={i.href} onClick={() => setSolutionsOpen(false)} className="group block">
                                      <p className="text-[15px] font-semibold text-[#1A1917] group-hover:text-[#C86B52] transition-colors">{i.label}</p>
                                      <p className="text-[13px] text-gray-500 font-normal leading-relaxed mt-1">{i.description}</p>
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
                onClick={() => navigate(SITE_CTA.login.href)}
                style={{ ...navItemStyle, color: colorSecondary }}
              >
                {SITE_CTA.login.label}
              </button>
            )}
            <button 
              onClick={openContactModal} 
              className="cta-primary h-10 px-5"
              style={{ fontSize: "14px", fontWeight: 500 }}
            >
              {SITE_CTA.demo.label}
              <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
            </button>
          </div>

          <button onClick={() => setMobileOpen(true)} className="lg:hidden p-2" style={{ color: colorPrimary }}>
            <Menu className="h-6 w-6" />
          </button>
        </div>
      </header>
      <MobileMenu open={mobileOpen} onClose={() => setMobileOpen(false)} />
    </>
  );
};

export default SiteHeader;


