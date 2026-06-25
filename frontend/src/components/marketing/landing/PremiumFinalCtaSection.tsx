// src/components/marketing/landing/PremiumFinalCtaSection.tsx

import React, { useEffect, useRef, useState } from "react";

interface PremiumFinalCtaSectionProps {
  onOpenContact?: () => void;
}

const PremiumFinalCtaSection: React.FC<PremiumFinalCtaSectionProps> = ({ onOpenContact }) => {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); observer.disconnect(); } },
      { threshold: 0.2 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const fadeIn = (delay: number): React.CSSProperties => ({
    opacity: visible ? 1 : 0,
    transform: visible ? "translateY(0)" : "translateY(16px)",
    transition: `opacity 0.8s cubic-bezier(0.16,1,0.3,1) ${delay}ms, transform 0.8s cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
  });

  return (
    <section
      ref={ref}
      className="relative overflow-hidden bg-[#111827] flex items-center justify-center"
      style={{ height: "50vh", minHeight: 320 }}
    >
      {/* Видеофон */}
      <video
        autoPlay muted loop playsInline aria-hidden="true"
        className="pointer-events-none absolute inset-0 h-full w-full object-cover"
        style={{ opacity: 0.10 }}
      >
        <source src="/video/cta-bg.mp4" type="video/mp4" />
      </video>

      {/* Radial glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(ellipse 70% 60% at 50% 50%, rgba(47,90,74,0.18) 0%, transparent 70%)" }}
      />

      {/* Контент */}
      <div className="relative mx-auto flex max-w-[1280px] flex-col items-center px-6 text-center lg:px-8">
        <div style={fadeIn(0)}>
          <span className="inline-block rounded-full border border-[#2F5A4A]/50 px-3.5 py-1 text-[11px] font-medium uppercase tracking-[0.09em] text-[#5BA88A]">
            The intelligence layer for legal work
          </span>
        </div>

        <h2
          className="mt-5 font-serif font-light text-white"
          style={{
            fontSize: "clamp(28px, 3.5vw, 56px)",
            lineHeight: 1.08,
            letterSpacing: "-0.02em",
            maxWidth: 640,
            ...fadeIn(100),
          }}
        >
          Превращайте документы
          <br />
          в структурированное знание.
        </h2>

        <p
          className="mt-4 text-sm leading-7 text-stone-400"
          style={{ maxWidth: 480, ...fadeIn(200) }}
        >
          Steloom даёт команде проверяемое и пригодное к действию знание
          из любого набора документов — быстро и без потери контроля.
        </p>

        <div style={fadeIn(300)} className="mt-7">
          <button
            type="button"
            onClick={onOpenContact}
            className="rounded-full bg-[#2F5A4A] px-8 py-3.5 text-sm font-medium text-white transition-all hover:bg-[#3F735F]"
            onMouseEnter={(e) =>
              (e.currentTarget.style.boxShadow = "0 8px 32px rgba(47,90,74,0.35)")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.boxShadow = "none")
            }
          >
            Запросить демо
          </button>
        </div>
      </div>
    </section>
  );
};

export default PremiumFinalCtaSection;

