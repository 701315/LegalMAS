// src/marketing/components/home/ApplicationSection/ApplicationSection.tsx
import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { SOLUTIONS_MEGA_MENU } from '../../../content/siteNav';
import styles from './ApplicationSection.module.css';

const APPLICATION_DATA: any = {
  ma: {
    id: "ma",
    title: "M&A и Due Diligence",
    description: "Автоматизация анализа data room: формирование DD grid и выявление рисков с прямой привязкой каждого вывода к источнику."
  },
  contract: {
    id: "contract",
    title: "Анализ договоров",
    description: "Проверка договоров на соответствие стандартам. Поиск отклонений от playbook, выявление отсутствующих положений и рисков в едином формате."
  },
  compliance: {
    id: "compliance",
    title: "Комплаенс и контроль",
    description: "Контроль соответствия договорного массива внутренним политикам организации. Автоматическое выявление отклонений для быстрого согласования с бизнесом."
  },
  audit: {
    id: "audit",
    title: "Внутренний аудит",
    description: "Проверка больших массивов действующих и исторических договоров. Формирование воспроизводимой истории findings с полной прослеживаемостью для контроля."
  },
  enrichment: {
    id: "enrichment",
    title: "Расширенный анализ (контрагенты и активы)",
    description: "Глубокая проверка контрагентов и активов (UBO, санкции, обременения недвижимости) через внешние реестры со встраиванием результатов в общий DD grid сделки."
  }
};

const ORDER = ["ma", "contract", "compliance", "audit", "enrichment"];

const ApplicationSection: React.FC = () => {
  const [activeIndex, setActiveIndex] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const isUserInteracting = useRef(false);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    if (menuOpen) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

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
          <h2 className="section-title text-white">
            Одна платформа<br />
            для ключевых контуров юридической работы
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
                      <h3 className="text-xl font-serif text-white lg:text-3xl transition-all duration-300 tracking-tight leading-tight">
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
              <span className="eyebrow !text-[#C86B52]">Сценарий использования</span>
              <p className="mt-4 text-base leading-[1.8] text-stone-300 lg:text-[1.125rem] font-medium">
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
            <span>Подробнее о сценариях</span>
            <ChevronDown className={`h-4 w-4 transition-transform duration-300 ${menuOpen ? 'rotate-180' : ''}`} />
          </button>

          <AnimatePresence>
            {menuOpen && (
              <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
                className="absolute bottom-full left-0 mb-6 w-full max-w-[840px] rounded-2xl bg-white shadow-[0_30px_70px_rgba(0,0,0,0.4)] p-10 lg:p-12 z-50 border border-white/10"
              >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-12 lg:gap-16">
                  {SOLUTIONS_MEGA_MENU.sections.map((section) => (
                    <div key={section.title}>
                      <h3 className="mb-6 text-[11px] font-bold uppercase tracking-widest text-gray-400">
                        {section.title}
                      </h3>
                      <ul className="space-y-5">
                        {section.items.map((item) => (
                          <li key={item.href}>
                            <Link 
                              to={item.href} 
                              className="group/item block"
                              onClick={() => setMenuOpen(false)}
                            >
                              <p className="text-[15px] font-semibold text-[#1A1917] group-hover/item:text-[#C86B52] transition-colors">
                                {item.label}
                              </p>
                              <p className="text-[13px] text-gray-500 font-normal leading-relaxed mt-1">
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


