// src/components/marketing/landing/ApplicationSection/layout/RolePanel.tsx

import React, { useRef, useEffect } from 'react';
import type { RoleData, PanelState } from '../types';
import styles from '../ApplicationSection.module.css';

interface RolePanelProps {
  role: RoleData;
  panelState: PanelState;
  sectionVisible: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

const stateClassMap: Record<PanelState, string> = {
  hidden: '',
  active: styles.panelActive,
  dormant: styles.panelDormant,
};

const RolePanel: React.FC<RolePanelProps> = ({
  role,
  panelState,
  sectionVisible,
  onMouseEnter,
  onMouseLeave,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const prevStateRef = useRef<PanelState>('hidden');

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (panelState === 'active' && sectionVisible) {
      if (prevStateRef.current === 'hidden') {
        video.currentTime = 0;
      }
      video.play().catch(() => {});
    } else {
      video.pause();
    }

    prevStateRef.current = panelState;
  }, [panelState, sectionVisible]);

  useEffect(() => {
    if (!sectionVisible) {
      const video = videoRef.current;
      if (video) {
        video.pause();
        video.currentTime = 0;
      }
      prevStateRef.current = 'hidden';
    }
  }, [sectionVisible]);

  const stateClass = stateClassMap[panelState];

  return (
    <div
      className={[styles.panel, stateClass].filter(Boolean).join(' ')}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      role="button"
      tabIndex={0}
      aria-label={role.title}
      onFocus={onMouseEnter}
      onBlur={onMouseLeave}
    >
      <div className={styles.videoContainer}>
        <video
          ref={videoRef}
          className={styles.video}
          src={role.videoSrc}
          muted
          loop
          playsInline
          preload="auto"
        />
        <div className={styles.videoOverlay} />
      </div>

      <div className={styles.panelContent}>
        {/* Заголовок — точно как h2 в SecurityFoundationSection */}
        <h3 className="font-serif text-5xl leading-[1.06] tracking-[-0.03em] text-stone-50 lg:text-[3.75rem]">
          {role.title}
        </h3>

        {/* Subtitle — leading-8 / lg:leading-9 как в Security */}
        <p className="mt-4 text-base font-medium leading-8 text-stone-300 lg:text-[1.05rem] lg:leading-9">
          {role.subtitle}
        </p>

        {/* Description — точно как параграфы в SecurityFoundationSection */}
        <p className="mt-4 text-base leading-8 text-stone-400 lg:text-[1.05rem] lg:leading-9">
          {role.description}
        </p>

        {/* Features */}
        <ul className="mt-6 flex flex-col gap-2.5">
          {role.features.map((feature) => (
            <li
              key={feature}
              className="flex items-center gap-2.5 font-mono text-[0.8125rem] text-stone-400"
            >
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full bg-stone-500"
                aria-hidden="true"
              />
              {feature}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default RolePanel;

