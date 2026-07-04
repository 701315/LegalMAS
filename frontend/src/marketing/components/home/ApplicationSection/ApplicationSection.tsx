// src/marketing/components/home/ApplicationSection/ApplicationSection.tsx
import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';
import { ROLES, ROLE_ORDER } from './roles/roles-data';
import styles from './ApplicationSection.module.css';

const ApplicationSection: React.FC = () => {
  const [activeIndex, setActiveIndex] = useState(0);
  const trackRef = useRef<HTMLDivElement>(null);
  const isUserInteracting = useRef(false);

  // Обзервер: следит, какая карточка по центру при ручном скролле
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
      {
        root: track,
        rootMargin: '0px -45% 0px -45%', 
        threshold: 0,
      }
    );

    const cards = track.querySelectorAll('[data-index]');
    cards.forEach((card) => observer.observe(card));

    return () => observer.disconnect();
  }, []);

  // Функция программного скролла
  const scrollToCard = (index: number) => {
    const track = trackRef.current;
    if (!track) return;
    
    const card = track.querySelector(`[data-index="${index}"]`) as HTMLElement;
    if (card) {
      const scrollPos = card.offsetLeft - (track.clientWidth / 2) + (card.clientWidth / 2);
      track.scrollTo({ left: scrollPos, behavior: 'smooth' });
    }
  };

  // Автоплей: крутит карусель каждые 4 секунды
  useEffect(() => {
    const timer = setInterval(() => {
      if (isUserInteracting.current) return; // Пауза, если мышка на карусели

      setActiveIndex((current) => {
        const next = current === ROLE_ORDER.length - 1 ? 0 : current + 1;
        scrollToCard(next);
        return next;
      });
    }, 4000);

    return () => clearInterval(timer);
  }, []);

  const activeRoleId = ROLE_ORDER[activeIndex];
  const activeRoleData = ROLES[activeRoleId];

  return (
    <section className={styles.section} id="application">
      <div className="mx-auto flex w-full max-w-[1280px] flex-col px-6 lg:px-10 xl:px-12 py-24 sm:py-32">
        
        <div className="mb-16 lg:mb-20">
          <h2 className="section-title text-white">
            Одна платформа<br />
            для ключевых контуров юридической работы
          </h2>
        </div>

        <div className={styles.grid}>
          {/* Левая колонка */}
          <div className={styles.leftCol}>
            
            <div 
              className={styles.carouselTrack} 
              ref={trackRef}
              // Ставим автоплей на паузу при наведении или тапе
              onTouchStart={() => { isUserInteracting.current = true; }}
              onTouchEnd={() => { setTimeout(() => { isUserInteracting.current = false; }, 3000); }}
              onMouseEnter={() => { isUserInteracting.current = true; }}
              onMouseLeave={() => { isUserInteracting.current = false; }}
              onWheel={() => { 
                isUserInteracting.current = true;
                setTimeout(() => { isUserInteracting.current = false; }, 3000);
              }}
            >
              {ROLE_ORDER.map((roleId, index) => {
                const role = ROLES[roleId];
                const isActive = index === activeIndex;

                return (
                  <div
                    key={role.id}
                    data-index={index}
                    className={`${styles.card} glass-panel ${isActive ? styles.cardActive : ''}`}
                    onClick={() => {
                      scrollToCard(index);
                      setActiveIndex(index);
                    }}
                  >
                    <div className="flex h-full flex-col justify-end p-8">
                      <h3 className="text-xl font-medium text-white lg:text-2xl transition-all duration-300">
                        {role.title}
                      </h3>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Индикаторы */}
            <div className={styles.dotsContainer}>
              {ROLE_ORDER.map((_, index) => (
                <button
                  key={index}
                  className={`${styles.dot} ${index === activeIndex ? styles.dotActive : ''}`}
                  onClick={() => {
                    scrollToCard(index);
                    setActiveIndex(index);
                  }}
                  aria-label={`Сценарий ${index + 1}`}
                />
              ))}
            </div>
          </div>

          {/* Правая колонка */}
          <div className={styles.rightCol}>
            <div key={activeRoleId} className="flex flex-col animate-fadein">
              <span className="eyebrow !text-[#5BA88A]">Сценарий</span>
              <p className="mt-4 text-base leading-[1.8] text-stone-300 lg:text-[1.125rem] lg:leading-[1.8]">
                {activeRoleData.description}
              </p>
            </div>
          </div>
        </div>

        <div className="mt-16 lg:mt-24">
          <Link 
            to="/solutions" 
            className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-medium text-white transition-all hover:bg-white/20 hover:border-white/30"
          >
            Подробнее о сценариях
            <ArrowUpRight size={16} />
          </Link>
        </div>

      </div>
    </section>
  );
};

export default ApplicationSection;

