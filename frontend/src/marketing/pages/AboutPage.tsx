import React from 'react';
import SiteHeader from '../components/shared/SiteHeader';
import MarketingPageFooter from '../components/shared/MarketingPageFooter';
import AboutHeroSection from '../components/about/AboutHeroSection';
import AboutProcessSection from '../components/about/AboutProcessSection';
import AboutPhilosophySection from '../components/about/AboutPhilosophySection';
import AboutPrinciplesSection from '../components/about/AboutPrinciplesSection';
import AboutTeamSection from '../components/about/AboutTeamSection';
import AboutCTASection from '../components/about/AboutCTASection';

const AboutPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        {/* Hero — Manifesto, focus on typography */}
        <AboutHeroSection />

        {/* Process — Visualizing the workflow pipeline */}
        <AboutProcessSection />

        {/* Philosophy — Detailed positioning in cards */}
        <AboutPhilosophySection />

        {/* Principles — Engineering & Legal foundations */}
        <AboutPrinciplesSection />

        {/* Team — Professionals grid */}
        <AboutTeamSection />

        {/* Final CTA — Transition to demo */}
        <AboutCTASection />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default AboutPage;


