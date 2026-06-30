// src/marketing/components/home/ApplicationSection/ApplicationSection.tsx

import React, { useRef } from 'react';
import { ROLES, ROLE_ORDER } from './roles/roles-data';
import RolePanel from './layout/RolePanel';
import BottomCta from './layout/BottomCta';
import { useApplicationStory } from './hooks/useApplicationStory';
import styles from './ApplicationSection.module.css';

const ApplicationSection: React.FC = () => {
  const sectionRef = useRef<HTMLElement | null>(null);

  const {
    getPanelState,
    showTitle,
    showCta,
    onPanelEnter,
    onPanelLeave,
  } = useApplicationStory(sectionRef);

  return (
    <section
      ref={sectionRef}
      className={styles.section}
      id="application"
      aria-label="Сценарии использования платформы"
    >
      <div className={styles.scrollTrack}>
        <div className={styles.stickyStage}>
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

          <div className={styles.panelsRow} onMouseLeave={onPanelLeave}>
            {ROLE_ORDER.map((roleId) => (
              <RolePanel
                key={roleId}
                role={ROLES[roleId]}
                panelState={getPanelState(roleId)}
                onMouseEnter={() => onPanelEnter(roleId)}
              />
            ))}
          </div>

          <BottomCta hidden={!showCta} />
        </div>
      </div>
    </section>
  );
};

export default ApplicationSection;


