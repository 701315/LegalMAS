// src/marketing/pages/HomePage.tsx

import React from "react";
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
import { ContactModalProvider } from "../context/ContactModalContext";

const HomePage: React.FC = () => {
  return (
    <ContactModalProvider>
      <SiteHeader />

      <main>
        <section data-header-theme="dark">
          <PremiumHeroSection />
          <ConceptTagsSection />
        </section>

        <section data-header-theme="light">
          <KnowledgeGrowthSection />
        </section>

        <section data-header-theme="light">
          <SecurityFoundationSection />
        </section>

        <section data-header-theme="light">
          <ApplicationSection />
        </section>

        <section data-header-theme="light">
          <FounderSection />
        </section>

        <section data-header-theme="light">
          <FaqSection />
        </section>

        <section data-header-theme="light">
          <PremiumFinalCtaSection />
        </section>
      </main>

      <SiteFooter />
    </ContactModalProvider>
  );
};

export default HomePage;