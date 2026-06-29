// src/marketing/pages/HomePage.tsx

import React, { useState } from "react";
import SiteHeader from "../components/shared/SiteHeader";
import PremiumHeroSection from "../components/home/PremiumHeroSection";
import ConceptTagsSection from "../components/home/ConceptTagsSection";
import KnowledgeGrowthSection from "../components/home/KnowledgeGrowthSection";
import SecurityFoundationSection from "../components/home/SecurityFoundationSection";
import { ApplicationSection } from "../components/home/ApplicationSection";
import FounderSection from "../components/home/FounderSection";
import FaqSection from "../components/home/FaqSection";
import PremiumFinalCtaSection from "../components/home/PremiumFinalCtaSection";
import SiteFooter from "../components/shared/SiteFooter";
import ContactModal from "../components/home/ContactModal";

const HomePage: React.FC = () => {
  const [contactOpen, setContactOpen] = useState(false);
  const [formEmail, setFormEmail] = useState("");
  const [formMessage, setFormMessage] = useState("");

  const handleContactSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const subject = encodeURIComponent("Steloom demo request");
    const body = encodeURIComponent(
      `Email: ${formEmail}\n\n${formMessage}`
    );
    window.location.href =
      `mailto:vladimir.gorelov.mail@gmail.com?subject=${subject}&body=${body}`;
  };

  return (
    <>
      <SiteHeader />

      <main>
        {/* 1. Hero — тёмная секция */}
        <section data-header-theme="dark">
          <PremiumHeroSection />
          <ConceptTagsSection />
        </section>

        {/* 2. Knowledge — светлая */}
        <section data-header-theme="light">
          <KnowledgeGrowthSection />
        </section>

        {/* 3. Security — светлая */}
        <section data-header-theme="light">
          <SecurityFoundationSection />
        </section>

        {/* 4. Use Cases — тёмная */}
        <section data-header-theme="light">
          <ApplicationSection />
        </section>

        {/* 5. Founder — светлая */}
        <section data-header-theme="light">
          <FounderSection />
        </section>

        {/* 6. FAQ — светлая */}
        <section data-header-theme="light">
          <FaqSection />
        </section>

        {/* 7. Final CTA — тёмная */}
        <section data-header-theme="light">
          <PremiumFinalCtaSection
            onOpenContact={() => setContactOpen(true)}
          />
        </section>
      </main>

      <SiteFooter />

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

export default HomePage;


