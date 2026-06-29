// src/components/marketing/landing/ApplicationSection/ApplicationSection.tsx

import React, { useRef } from 'react';
import { useIntersection } from './hooks/useIntersection';
import { useReducedMotion } from './hooks/useReducedMotion';
import { useApplicationSequence } from './hooks/useApplicationSequence';
import { ROLES, ROLE_ORDER } from './roles/roles-data';
import RolePanel from './layout/RolePanel';
import BottomCta from './layout/BottomCta';
import styles from './ApplicationSection.module.css';

const ApplicationSection: React.FC = () => {
  const sectionRef = useRef<HTMLElement | null>(null);
  const isVisible = useIntersection(sectionRef, 0.3);
  const reducedMotion = useReducedMotion();

  const {
    getPanelState,
    onPanelEnter,
    onPanelLeave,
    showTitle,
  } = useApplicationSequence(isVisible, reducedMotion);

  return (
    <section
      ref={sectionRef}
      className={styles.section}
      id="application"
      aria-label="Сценарии использования платформы"
    >
      <div
        className={[
          styles.titleOverlay,
          showTitle ? styles.titleVisible : styles.titleHidden,
        ].join(' ')}
      >
        <h2 className={styles.sectionTitle}>
          Одна платформа
          <br />
          для ключевых контуров
          <br />
          юридической работы
        </h2>
      </div>

      <div className={styles.panelsRow}>
        {ROLE_ORDER.map((roleId) => (
          <RolePanel
            key={roleId}
            role={ROLES[roleId]}
            panelState={getPanelState(roleId)}
            sectionVisible={isVisible}
            onMouseEnter={() => onPanelEnter(roleId)}
            onMouseLeave={onPanelLeave}
          />
        ))}
      </div>

      <BottomCta hidden={showTitle} />
    </section>
  );
};

export default ApplicationSection;