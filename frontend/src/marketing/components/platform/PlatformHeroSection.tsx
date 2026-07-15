import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { HERO_CONTENT } from "./content/platformContent";
import PathCrumb from "./primitives/PathCrumb";

const PlatformHeroSection: React.FC = () => {
  const shouldReduceMotion = useReducedMotion();
  const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

  return (
    <section 
      className="relative flex min-h-[85dvh] items-center overflow-hidden bg-[#FAF8F5]"
      data-header-theme="light"
    >
      {/* ── Background Layer ────────────────────────────────────────── */}
      <div className="absolute inset-0 z-0">
        <motion.img 
          src="/platform-1.png" 
          alt="" 
          className="h-full w-full object-cover object-center opacity-50 lg:opacity-65"
          initial={shouldReduceMotion ? undefined : { scale: 1.02, opacity: 0 }}
          animate={shouldReduceMotion ? undefined : { scale: 1, opacity: 0.65 }}
          transition={{ duration: 1.2, ease }}
          aria-hidden="true"
        />
        <div 
          className="absolute inset-0" 
          style={{
            background: 'linear-gradient(90deg, #FAF8F5 0%, rgba(250,248,245,0.95) 20%, rgba(250,248,245,0.3) 60%, transparent 100%)'
          }} 
        />
      </div>

      {/* ── Content Layer ────────────────────────────────────────────── */}
      <div
        className="relative z-10 mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-12 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-8 xl:col-span-7">
            <motion.div
              initial={shouldReduceMotion ? undefined : { opacity: 0, y: 12 }}
              animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05, ease }}
            >
              <PathCrumb
                root={HERO_CONTENT.eyebrow.root}
                leaf={HERO_CONTENT.eyebrow.leaf}
              />
            </motion.div>

            <motion.h1
              initial={shouldReduceMotion ? undefined : { opacity: 0, y: 14 }}
              animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.12, ease }}
              className="mt-5 font-serif text-[clamp(2.5rem,5vw,4.2rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]"
            >
              {HERO_CONTENT.title}
            </motion.h1>

            <motion.div
              initial={shouldReduceMotion ? undefined : { opacity: 0, y: 12 }}
              animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.22, ease }}
              className="mt-8 space-y-6"
              style={{ maxWidth: 620 }}
            >
              {HERO_CONTENT.paragraphs.map((p, i) => (
                <p key={i} className="text-[1.0625rem] leading-[1.75] text-[#78756F]">
                  {p}
                </p>
              ))}
            </motion.div>
          </div>
          <div className="hidden lg:block lg:col-span-4 xl:col-span-5" />
        </div>
      </div>

      <div className="absolute bottom-0 left-0 w-full">
        <div className="mx-auto" style={{ maxWidth: "var(--container-max-width)" }}>
          <div className="mx-6 lg:mx-8">
            <div className="h-px w-full bg-[#E8E4DD]" />
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformHeroSection;