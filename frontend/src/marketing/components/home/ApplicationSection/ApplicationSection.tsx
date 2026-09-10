// src/marketing/components/home/ApplicationSection/ApplicationSection.tsx
import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import styles from './ApplicationSection.module.css';

// ─────────────────────────────────────────────────────────────
// Типы
// ─────────────────────────────────────────────────────────────
interface MegaMenuItem {
  label: string;
  href: string;
  description?: string;
}
interface MegaMenuSection {
  title: string;
  items: MegaMenuItem[];
}
interface ApplicationRole {
  id: string;
  title: string;
  description: string;
}

const ORDER = ["ma", "contract", "compliance", "audit", "enrichment"] as const;

const ApplicationSection: React.FC = () => {
  const { t } = useTranslation('marketing');
  const [activeIndex, setActiveIndex] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const isUserInteracting = useRef(false);

  // ── Данные из i18n ─────────────────────────────────────────
  const APPLICATION_DATA: Record<string, ApplicationRole> = {
    ma: {
      id: "ma",
      title: t('application.roles.ma.title'),
      description: t('application.roles.ma.description'),
    },
    contract: {
      id: "contract",
      title: t('application.roles.contract.title'),
      description: t('application.roles.contract.description'),
    },
    compliance: {
      id: "compliance",
      title: t('application.roles.compliance.title'),
      description: t('application.roles.compliance.description'),
    },
    audit: {
      id: "audit",
      title: t('application.roles.audit.title'),
      description: t('application.roles.audit.description'),
    },
    enrichment: {
      id: "enrichment",
      title: t('application.roles.enrichment.title'),
      description: t('application.roles.enrichment.description'),
    },
  };

  // Мега-меню из i18n (для выпадающего списка "Подробнее о сценариях")
  const SOLUTIONS_MEGA_MENU: { sections: MegaMenuSection[] } = {
    sections: [
      {
        title: t('megaMenu.byDirection.title'),
        items: [
          { label: t('megaMenu.byDirection.maDueDiligence.label'), href: '/solutions/ma-due-diligence', description: t('megaMenu.byDirection.maDueDiligence.description') },
          { label: t('megaMenu.byDirection.contractReview.label'), href: '/solutions/contract-review', description: t('megaMenu.byDirection.contractReview.description') },
          { label: t('megaMenu.byDirection.compliance.label'), href: '/solutions/compliance', description: t('megaMenu.byDirection.compliance.description') },
          { label: t('megaMenu.byDirection.internalAudit.label'), href: '/solutions/internal-audit', description: t('megaMenu.byDirection.internalAudit.description') },
        ],
      },
      {
        title: t('megaMenu.byTeam.title'),
        items: [
          { label: t('megaMenu.byTeam.lawFirms.label'), href: '/solutions/law-firms', description: t('megaMenu.byTeam.lawFirms.description') },
          { label: t('megaMenu.byTeam.corporateLegal.label'), href: '/solutions/corporate-legal', description: t('megaMenu.byTeam.corporateLegal.description') },
          { label: t('megaMenu.byTeam.auditCompliance.label'), href: '/solutions/audit-compliance', description: t('megaMenu.byTeam.auditCompliance.description') },
        ],
      },
      {
        title: t('megaMenu.enrichment.title'),
        items: [
          { label: t('megaMenu.enrichment.counterparties.label'), href: '/solutions/counterparties', description: t('megaMenu.enrichment.counterparties.description') },
          { label: t('megaMenu.enrichment.realEstate.label'), href: '/solutions/real-estate', description: t('megaMenu.enrichment.realEstate.description') },
        ],
      },
    ],
  };

  // ── Click outside to close menu ────────────────────────────
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    if (menuOpen) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  // ── IntersectionObserver для активной карточки ─────────────
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const index = Number((entry.target as HTMLElement).dataset.index);
            setActiveIndex(index);
          }
        });
      },
      { root: track, rootMargin: '0px -45% 0px -45%', threshold: 0 }
    );

    const cards = track.querySelectorAll('[data-index]');
    cards.forEach((card) => observer.observe(card));
    return () => observer.disconnect();
  }, []);

  const scrollToCard = (index: number) => {
    const track = trackRef.current;
    if (!track) return;
    const card = track.querySelector(`[data-index="${index}"]`) as HTMLElement;
    if (card) {
      const scrollPos = card.offsetLeft - (track.clientWidth / 2) + (card.clientWidth / 2);
      track.scrollTo({ left: scrollPos, behavior: 'smooth' });
    }
  };

  // ── Автоскролл карусели ────────────────────────────────────
  useEffect(() => {
    const timer = setInterval(() => {
      if (isUserInteracting.current || menuOpen) return;
      setActiveIndex((current) => {
        const next = current === ORDER.length - 1 ? 0 : current + 1;
        scrollToCard(next);
        return next;
      });
    }, 5000);
    return () => clearInterval(timer);
  }, [menuOpen]);

  const activeRoleId = ORDER[activeIndex];
  const activeRoleData = APPLICATION_DATA[activeRoleId];

  return (
    <section className={styles.section} id="application" data-header-theme="dark">
      <div 
        className="mx-auto flex w-full flex-col px-6 lg:px-8 py-20 lg:py-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        
        <div className="mb-16 lg:mb-20">
          <h2 className="text-h1 !text-white max-w-4xl mx-auto mb-4">
            {t('application.title')}
          </h2>
        </div>

        <div className={styles.grid}>
          <div className={styles.leftCol}>
            <div 
              className={styles.carouselTrack} 
              ref={trackRef}
              onMouseEnter={() => { isUserInteracting.current = true; }}
              onMouseLeave={() => { isUserInteracting.current = false; }}
            >
              {ORDER.map((roleId, index) => {
                const role = APPLICATION_DATA[roleId];
                const isActive = index === activeIndex;
                return (
                  <div
                    key={role.id}
                    data-index={index}
                    className={`${styles.card} glass-panel ${isActive ? styles.cardActive : ''}`}
                    onClick={() => { scrollToCard(index); setActiveIndex(index); }}
                  >
                    <div className="flex h-full flex-col justify-end p-8">
                      <h3 className="text-h1 !text-white max-w-4xl mx-auto mb-4">
                        {role.title}
                      </h3>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className={styles.dotsContainer}>
              {ORDER.map((_, index) => (
                <button
                  key={index}
                  className={`${styles.dot} ${index === activeIndex ? styles.dotActive : ''}`}
                  onClick={() => { scrollToCard(index); setActiveIndex(index); }}
                />
              ))}
            </div>
          </div>

          <div className={styles.rightCol}>
            <div key={activeRoleId} className="flex flex-col animate-fadein">
              <span className="eyebrow !text-[var(--accent-primary)]">{t('application.eyebrow')}</span>
              <p className="mt-4 text-body !text-stone-300 font-medium max-w-2xl mx-auto">
                {activeRoleData.description}
              </p>
            </div>
          </div>
        </div>

        {/* КНОПКА С МЕНЮ */}
        <div className="relative mt-16 lg:mt-24" ref={menuRef}>
          <button 
            onClick={() => setMenuOpen(!menuOpen)}
            className="cta-link-inverse flex items-center gap-2 group text-base"
          >
            <span>{t('application.moreButton')}</span>
            <ChevronDown className={`h-4 w-4 transition-transform duration-300 ${menuOpen ? 'rotate-180' : ''}`} />
          </button>

          <AnimatePresence>
            {menuOpen && (
              <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
                className="absolute bottom-full start-0 mb-6 w-full max-w-[840px] max-w-[calc(100vw-2rem)] rounded-2xl bg-white shadow-[0_30px_70px_rgba(0,0,0,0.4)] p-10 lg:p-12 z-50 border border-white/10"
              >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-12 lg:gap-16">
                  {SOLUTIONS_MEGA_MENU.sections.map((section: MegaMenuSection) => (
                    <div key={section.title}>
                      <h3 className="mb-6 text-meta font-bold text-gray-400">
                        {section.title}
                      </h3>
                      <ul className="space-y-5">
                        {section.items.map((item: MegaMenuItem) => (
                          <li key={item.href}>
                            <Link 
                              to={item.href} 
                              className="group/item block"
                              onClick={() => setMenuOpen(false)}
                            >
                              <p className="text-body-sm !font-bold !text-[#1A1917] group-hover/item:!text-[var(--accent-primary)] transition-colors">
                                {item.label}
                              </p>
                              <p className="text-body-sm text-gray-500 font-normal leading-relaxed mt-1">
                                {item.description}
                              </p>
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

      </div>
    </section>
  );
};

export default ApplicationSection;