// src/components/marketing/landing/ApplicationSection/layout/BottomCta.tsx

import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';
import styles from '../ApplicationSection.module.css';

interface BottomCtaProps {
  hidden: boolean;
}

const BottomCta: React.FC<BottomCtaProps> = ({ hidden }) => (
  <div
    className={[
      styles.bottomCta,
      hidden ? styles.bottomCtaHidden : styles.bottomCtaVisible,
    ].join(' ')}
  >
    <Link to="/solutions" className={styles.ctaLink}>
      Подробности о сценариях использования платформы
      <ArrowUpRight size={14} />
    </Link>
  </div>
);

export default BottomCta;