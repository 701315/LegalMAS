// src/pages/LandingPage.tsx

import React, { useState, useEffect, useRef } from "react";
import { ScrollProvider, useScroll } from "../context/ScrollContext";
import LandingHeader from "../components/marketing/landing/LandingHeader";
import PremiumHeroSection from "../components/marketing/landing/PremiumHeroSection";
import ConceptTagsSection from "../components/marketing/landing/ConceptTagsSection";
import SolutionsSection from "../components/marketing/landing/SolutionsSection";
import CapabilitiesSection from "../components/marketing/landing/CapabilitiesSection";
import ArchitecturePreviewSection from "../components/marketing/landing/ArchitecturePreviewSection";
import SecuritySection from "../components/marketing/landing/SecuritySection";
import FaqSection from "../components/marketing/landing/FaqSection";
import PremiumFinalCtaSection from "../components/marketing/landing/PremiumFinalCtaSection";
import LandingFooter from "../components/marketing/landing/LandingFooter";
import ContactModal from "../components/marketing/landing/ContactModal";

const LandingPageInner: React.FC = () => {
  const { scrollContainerRef, setScrolled } = useScroll();
  const [contactOpen, setContactOpen] = useState(false);
  const [formEmail, setFormEmail] = useState("");
  const [formMessage, setFormMessage] = useState("");
  const isScrolling = useRef(false);

  // Следим за скроллом → обновляем контекст
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const handleScroll = () => setScrolled(container.scrollTop > 32);
    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, [scrollContainerRef, setScrolled]);

  // Wheel snap хелпер — правильный алгоритм поиска текущего блока
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (isScrolling.current) return;

      const sections = Array.from(
        container.querySelectorAll<HTMLElement>("[data-snap]")
      );
      if (sections.length === 0) return;

      const scrollTop = container.scrollTop;
      const direction = e.deltaY > 0 ? 1 : -1;

      // Находим блок с offsetTop ближайшим к текущей позиции скролла
      let currentIndex = 0;
      let minDistance = Infinity;
      for (let i = 0; i < sections.length; i++) {
        const distance = Math.abs(sections[i].offsetTop - scrollTop);
        if (distance < minDistance) {
          minDistance = distance;
          currentIndex = i;
        }
      }

      const nextIndex = Math.max(
        0,
        Math.min(sections.length - 1, currentIndex + direction)
      );
      if (nextIndex === currentIndex) return;

      isScrolling.current = true;
      container.scrollTo({
        top: sections[nextIndex].offsetTop,
        behavior: "smooth",
      });

      setTimeout(() => {
        isScrolling.current = false;
      }, 900);
    };

    container.addEventListener("wheel", handleWheel, { passive: false });
    return () => container.removeEventListener("wheel", handleWheel);
  }, [scrollContainerRef]);

  const handleContactSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const subject = encodeURIComponent("Запрос демо Steloom");
    const body = encodeURIComponent(`Email: ${formEmail}\n\n${formMessage}`);
    window.location.href = `mailto:vladimir.gorelov.mail@gmail.com?subject=${subject}&body=${body}`;
  };

  return (
    <>
      <LandingHeader />

      <div
        ref={scrollContainerRef}
        className="bg-[#F8F7F4] text-stone-950 antialiased"
        style={{
          overflowY: "scroll",
          height: "100vh",
          scrollPaddingTop: "68px",
          scrollSnapType: "y mandatory",
        }}
      >
        {/* 1. Hero + теги */}
        <div data-snap style={{ scrollSnapAlign: "start" }}>
          <PremiumHeroSection />
          <ConceptTagsSection />
        </div>

        {/* 2. Возможности */}
        <div data-snap style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}>
          <CapabilitiesSection />
        </div>

        {/* 3. Для кого */}
        <div data-snap style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}>
          <SolutionsSection />
        </div>

        {/* 4. Безопасность */}
        <div data-snap style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}>
          <SecuritySection />
        </div>

        {/* 5. Архитектура */}
        <div data-snap style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}>
          <ArchitecturePreviewSection />
        </div>

        {/* 6. FAQ (50vh) + CTA (50vh) = один экран */}
        <div data-snap style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}>
          <FaqSection />
          <PremiumFinalCtaSection onOpenContact={() => setContactOpen(true)} />
        </div>

        {/* 7. Футер — отдельный snap-блок, виден полностью */}
        <div data-snap style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}>
          <LandingFooter />
        </div>
      </div>

      <ContactModal
        open={contactOpen}
        email={formEmail}
        message={formMessage}
        onEmailChange={setFormEmail}
        onMessageChange={setFormMessage}
        onClose={() => setContactOpen(false)}
        onSubmit={handleContactSubmit}
      />
    </>
  );
};

const LandingPage: React.FC = () => (
  <ScrollProvider>
    <LandingPageInner />
  </ScrollProvider>
);

export default LandingPage;

