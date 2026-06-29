// src/marketing/components/home/ApplicationSection/layout/RolePanel.tsx

import React, { useRef, useEffect } from 'react';
import type { RoleData, PanelState } from '../types';
import styles from '../ApplicationSection.module.css';

interface RolePanelProps {
  role: RoleData;
  panelState: PanelState;
}

const stateClassMap: Record<PanelState, string> = {
  hidden: '',
  active: styles.panelActive,
  dormant: styles.panelDormant,
};

const RolePanel: React.FC<RolePanelProps> = ({ role, panelState }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const prevStateRef = useRef<PanelState>('hidden');

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (panelState === 'active') {
      if (prevStateRef.current !== 'active') {
        video.currentTime = 0;
      }
      video.play().catch(() => {});
    } else if (panelState === 'dormant') {
      video.pause();
    } else {
      video.pause();
      video.currentTime = 0;
    }

    prevStateRef.current = panelState;
  }, [panelState]);

  const stateClass = stateClassMap[panelState];

  return (
    <div
      className={[styles.panel, stateClass].filter(Boolean).join(' ')}
      tabIndex={0}
      aria-label={role.title}
    >
      {/* Video background */}
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

      {/* Content */}
      <div className={styles.panelContent}>
        {/* Eyebrow */}
        <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
          <span className="text-stone-400">{role.indexLabel}</span>
          <span className="mx-1.5 text-stone-600">/</span>
          <span>{role.eyebrow}</span>
        </div>

        {/* Title */}
        <h3 className="mt-5 font-serif text-5xl leading-[1.06] tracking-[-0.03em] text-stone-50 lg:text-[3.75rem]">
          {role.title}
        </h3>

        {/* Subtitle */}
        <p className="mt-4 text-base font-medium leading-8 text-stone-300 lg:text-[1.05rem] lg:leading-9">
          {role.subtitle}
        </p>

        {/* Description */}
        <p className="mt-3 text-base leading-8 text-stone-400 lg:text-[1.05rem] lg:leading-9">
          {role.description}
        </p>

        {/* Divider */}
        <div className={styles.panelDivider} aria-hidden="true" />

        {/* Capabilities */}
        <ul className="flex flex-col gap-2.5">
          {role.capabilities.map((cap) => (
            <li
              key={cap}
              className="flex items-center gap-2.5 font-mono text-[0.8125rem] text-stone-400"
            >
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full bg-stone-600"
                aria-hidden="true"
              />
              {cap}
            </li>
          ))}
        </ul>

        {/* Outcome */}
        <div className="mt-6">
          <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-stone-600">
            Outcome
          </div>
          <p className="mt-1 text-[0.9375rem] font-medium leading-relaxed text-stone-300">
            {role.outcome}
          </p>
        </div>
      </div>
    </div>
  );
};

export default RolePanel;


