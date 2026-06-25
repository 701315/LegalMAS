// frontend/src/components/marketing/landing/PremiumHeroSection.tsx

import React, { useEffect, useState } from "react";

function IntelligenceGraph() {
  return (
    <svg
      viewBox="0 0 520 420"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="h-full w-full"
      aria-hidden="true"
    >
      <circle cx="260" cy="210" r="5.5" fill="#2F5A4A" opacity="0.95" />
      <circle cx="140" cy="130" r="3.5" fill="#4B7A69" opacity="0.65" />
      <circle cx="380" cy="130" r="3.5" fill="#4B7A69" opacity="0.65" />
      <circle cx="100" cy="290" r="3"   fill="#4B7A69" opacity="0.50" />
      <circle cx="420" cy="290" r="3"   fill="#4B7A69" opacity="0.50" />
      <circle cx="200" cy="340" r="3"   fill="#4B7A69" opacity="0.45" />
      <circle cx="320" cy="340" r="3"   fill="#4B7A69" opacity="0.45" />
      <circle cx="180" cy="72"  r="2.5" fill="#6B9A89" opacity="0.38" />
      <circle cx="340" cy="72"  r="2.5" fill="#6B9A89" opacity="0.38" />
      <circle cx="56"  cy="195" r="2.5" fill="#6B9A89" opacity="0.30" />
      <circle cx="464" cy="195" r="2.5" fill="#6B9A89" opacity="0.30" />
      <circle cx="230" cy="390" r="2"   fill="#6B9A89" opacity="0.25" />
      <circle cx="290" cy="390" r="2"   fill="#6B9A89" opacity="0.25" />
      <line x1="260" y1="210" x2="140" y2="130" stroke="#2F5A4A" strokeWidth="0.9" opacity="0.55" />
      <line x1="260" y1="210" x2="380" y2="130" stroke="#2F5A4A" strokeWidth="0.9" opacity="0.55" />
      <line x1="260" y1="210" x2="100" y2="290" stroke="#2F5A4A" strokeWidth="0.8" opacity="0.42" />
      <line x1="260" y1="210" x2="420" y2="290" stroke="#2F5A4A" strokeWidth="0.8" opacity="0.42" />
      <line x1="260" y1="210" x2="200" y2="340" stroke="#2F5A4A" strokeWidth="0.7" opacity="0.35" />
      <line x1="260" y1="210" x2="320" y2="340" stroke="#2F5A4A" strokeWidth="0.7" opacity="0.35" />
      <line x1="140" y1="130" x2="180" y2="72"  stroke="#4B7A69" strokeWidth="0.6" opacity="0.28" />
      <line x1="380" y1="130" x2="340" y2="72"  stroke="#4B7A69" strokeWidth="0.6" opacity="0.28" />
      <line x1="100" y1="290" x2="56"  y2="195" stroke="#4B7A69" strokeWidth="0.6" opacity="0.22" />
      <line x1="420" y1="290" x2="464" y2="195" stroke="#4B7A69" strokeWidth="0.6" opacity="0.22" />
      <line x1="200" y1="340" x2="230" y2="390" stroke="#4B7A69" strokeWidth="0.5" opacity="0.18" />
      <line x1="320" y1="340" x2="290" y2="390" stroke="#4B7A69" strokeWidth="0.5" opacity="0.18" />
      <line x1="140" y1="130" x2="100" y2="290" stroke="#4B7A69" strokeWidth="0.5" opacity="0.18" />
      <line x1="380" y1="130" x2="420" y2="290" stroke="#4B7A69" strokeWidth="0.5" opacity="0.18" />
      <line x1="70"  y1="152" x2="450" y2="152" stroke="#3F7A5A" strokeWidth="0.4" opacity="0.14" strokeDasharray="4 7" />
      <line x1="50"  y1="235" x2="470" y2="235" stroke="#3F7A5A" strokeWidth="0.4" opacity="0.10" strokeDasharray="4 7" />
      <line x1="70"  y1="312" x2="450" y2="312" stroke="#3F7A5A" strokeWidth="0.4" opacity="0.08" strokeDasharray="4 7" />
      <text x="455" y="156" fill="#4B7A69" fontSize="7.5" opacity="0.50" fontFamily="Inter,sans-serif" letterSpacing="0.07em">LAYER 2</text>
      <text x="455" y="239" fill="#4B7A69" fontSize="7.5" opacity="0.38" fontFamily="Inter,sans-serif" letterSpacing="0.07em">LAYER 1</text>
      <text x="455" y="316" fill="#4B7A69" fontSize="7.5" opacity="0.28" fontFamily="Inter,sans-serif" letterSpacing="0.07em">LAYER 0</text>
    </svg>
  );
}

const PremiumHeroSection: React.FC = () => {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 60);
    return () => clearTimeout(t);
  }, []);

  const fadeIn = (delayMs: number): React.CSSProperties => ({
    opacity: mounted ? 1 : 0,
    transform: mounted ? "translateY(0)" : "translateY(14px)",
    transition: `opacity 0.75s cubic-bezier(0.16,1,0.3,1) ${delayMs}ms, transform 0.75s cubic-bezier(0.16,1,0.3,1) ${delayMs}ms`,
  });

  return (
    <section
      className="relative flex min-h-screen items-center overflow-hidden bg-[#111827]"
      style={{ paddingTop: 160, paddingBottom: 120 }}
    >
      {/* Видеофон */}
      <video
        autoPlay muted loop playsInline aria-hidden="true"
        className="pointer-events-none absolute inset-0 h-full w-full object-cover"
        style={{ opacity: 0.18 }}
      >
        <source src="/video/hero-bg.mp4" type="video/mp4" />
      </video>

      {/* Grain */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
          opacity: 0.04,
        }}
      />

      {/* Radial glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(ellipse 65% 55% at 68% 50%, rgba(47,90,74,0.20) 0%, transparent 72%)" }}
      />

      {/* Контент */}
      <div className="relative mx-auto grid w-full max-w-[1280px] grid-cols-1 gap-16 px-6 lg:grid-cols-2 lg:gap-12 lg:px-8">

        {/* Левая колонка */}
        <div className="flex flex-col justify-center">
          <h1
            className="font-serif font-light text-white"
            style={{
              fontSize: "clamp(48px, 5.2vw, 84px)",
              lineHeight: 1.07,
              letterSpacing: "-0.02em",
              ...fadeIn(60),
            }}
          >
            Превращайте документы
            <br />
            <em className="not-italic" style={{ color: "#5BA88A" }}>
              в структурированное знание.
            </em>
          </h1>

          <p
            className="mt-7 text-base leading-[1.8] text-stone-400"
            style={{ maxWidth: 460, ...fadeIn(180) }}
          >
            Steloom превращает массивы юридических документов в связанную,
            проверяемую и пригодную к работе интеллектуальную систему —
            чтобы команда тратила время на суждение, а не на ручное чтение.
          </p>
        </div>

        {/* Правая колонка — SVG граф */}
        <div
          className="hidden items-center justify-center lg:flex"
          style={fadeIn(160)}
        >
          <div className="relative h-[420px] w-full max-w-[520px]">
            <IntelligenceGraph />
          </div>
        </div>
      </div>

      {/* Scroll indicator */}
      <div
        className="absolute bottom-10 left-1/2 -translate-x-1/2"
        style={fadeIn(600)}
      >
        <div className="flex h-8 w-5 items-start justify-center rounded-full border border-white/20 pt-1.5">
          <div
            className="h-1.5 w-0.5 rounded-full bg-white/40"
            style={{ animation: "scrollBounce 2s ease-in-out infinite" }}
          />
        </div>
      </div>
    </section>
  );
};

export default PremiumHeroSection;

