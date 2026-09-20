// src/marketing/pages/CapabilitiesPage.tsx

import React from "react";
import SiteHeader from "../components/shared/SiteHeader";
import MarketingPageFooter from "../components/shared/MarketingPageFooter";

// ── Platform sections ────────────────────────────────────────────────────────
import PlatformHeroSection from "../components/platform/PlatformHeroSection";
import PlatformWorkflowSection from "../components/platform/PlatformWorkflowSection";
import PlatformDocumentStructureSection from "../components/platform/PlatformDocumentStructureSection";
import PlatformStandardsSection from "../components/platform/PlatformStandardsSection";
import PlatformFindingsSection from "../components/platform/PlatformFindingsSection";
import PlatformMethodologySection from "../components/platform/PlatformMethodologySection";
import PlatformCTASection from "../components/platform/PlatformCTASection";
import PlatformTechnicalSection from "../components/platform/PlatformTechnicalSection";

/**
 * CapabilitiesPage — страница /capabilities (внутренне: Platform).
 *
 * Header БЕЗ forcedTheme — автоматически подстраивает цвета через
 * data-header-theme на каждой секции. На тёмной Standards-секции
 * навигация становится светлой.
 *
 * Порядок секций (после упрощения):
 *   1. Hero
 *   2. Workflow
 *   3. Document Structure
 *   4. Standards (тёмная)
 *   5. Findings
 *   6. Methodology
 *   7. CTA
 *   8. Technical Accordion (Как устроен Steloom)
 *
 * Отключены (файлы оставлены как opt-in на будущее):
 *   • PlatformFeatureGridSection — «Что внутри / Возможности…»
 *   • PlatformSummarySection — «Итого» (3 тезиса)
 */
const CapabilitiesPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <PlatformHeroSection />
        <PlatformWorkflowSection />
        <PlatformDocumentStructureSection />
        <PlatformStandardsSection />
        <PlatformFindingsSection />
        <PlatformMethodologySection />
        <PlatformCTASection />
        <PlatformTechnicalSection />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default CapabilitiesPage;


