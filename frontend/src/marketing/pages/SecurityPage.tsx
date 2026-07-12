// src/marketing/pages/SecurityPage.tsx

import React from 'react';
import SiteHeader from '../components/shared/SiteHeader';
import MarketingPageFooter from '../components/shared/MarketingPageFooter';
import SecurityHeroSection from '../components/security/SecurityHeroSection';
import SecurityCapabilitiesSection from '../components/security/SecurityCapabilitiesSection';
import SecurityDeploymentSection from '../components/security/SecurityDeploymentSection';
import SecurityCTASection from '../components/security/SecurityCTASection';
import SecurityFAQSection from '../components/security/SecurityFAQSection';

const SecurityPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        {/* Hero — light */}
        <SecurityHeroSection />

        {/* Capabilities — light, alternating */}
        <SecurityCapabilitiesSection />

        {/* Deployment — off-white */}
        <SecurityDeploymentSection />

        {/* CTA — light */}
        <SecurityCTASection />

        {/* FAQ — off-white, финальная секция */}
        <SecurityFAQSection />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default SecurityPage;