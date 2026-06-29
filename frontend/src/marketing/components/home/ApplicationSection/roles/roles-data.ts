// src/marketing/components/home/ApplicationSection/roles/roles-data.ts

import type { RoleData, RoleId } from '../types';

export const ROLES: Record<RoleId, RoleData> = {
  left: {
    id: 'left',
    title: 'M&A-команды',
    subtitle: 'Скорость и контроль в data room.',
    description:
      'Steloom обрабатывает data room против вашего playbook — каждое положение, ' +
      'риск и перекрёстная ссылка структурированы за часы, а не недели. ' +
      'Ни одно условие не теряется на странице 47.',
    features: ['Due Diligence', 'Data Room', 'Risk Extraction', 'Playbook Review'],
    videoSrc: '/left-video.mp4',
  },

  center: {
    id: 'center',
    title: 'Legal Ops',
    subtitle: 'Операционная прозрачность правовой функции.',
    description:
      'Steloom превращает разрозненные процессы в единый поток: от входящего запроса ' +
      'до финального документа. Метрики, сроки и узкие места видны в реальном времени — ' +
      'без ручных отчётов.',
    features: ['Workflow Automation', 'SLA Tracking', 'Template Management', 'Reporting'],
    videoSrc: '/center-video.mp4',
  },

  right: {
    id: 'right',
    title: 'General Counsel',
    subtitle: 'Стратегический контроль всей правовой вертикали.',
    description:
      'Steloom даёт полную картину правовой функции: риски, обязательства, ' +
      'регуляторные изменения и их влияние на бизнес. Решения принимаются на основе ' +
      'структурированного знания, а не интуиции.',
    features: ['Risk Overview', 'Regulatory Monitoring', 'Board Reporting', 'Compliance Map'],
    videoSrc: '/right-video.mp4',
  },
};

export const ROLE_ORDER: RoleId[] = ['left', 'center', 'right'];

