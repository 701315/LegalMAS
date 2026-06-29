// src/marketing/components/home/ApplicationSection/roles/roles-data.ts

import type { RoleData, RoleId } from '../types';

export const ROLES: Record<RoleId, RoleData> = {
  left: {
    id: 'left',
    indexLabel: '01',
    eyebrow: 'M&A',
    title: 'M&A-команды',
    subtitle: 'Скорость и контроль в data room.',
    description:
      'Проверка идёт против playbook, а риски и связи собираются в структурированную картину за часы.',
    capabilities: [
      'Playbook review',
      'Risk extraction',
      'Cross-reference mapping',
    ],
    outcome: 'Часы вместо недель',
    videoSrc: '/left-video.mp4',
  },

  center: {
    id: 'center',
    indexLabel: '02',
    eyebrow: 'Operations',
    title: 'Legal Ops',
    subtitle: 'Прозрачность правовой функции.',
    description:
      'Запросы, документы и SLA собираются в единый операционный поток без ручных отчётов.',
    capabilities: [
      'Workflow orchestration',
      'SLA visibility',
      'Template control',
    ],
    outcome: 'Один поток вместо разрозненных процессов',
    videoSrc: '/center-video.mp4',
  },

  right: {
    id: 'right',
    indexLabel: '03',
    eyebrow: 'Leadership',
    title: 'General Counsel',
    subtitle: 'Контроль правовой вертикали.',
    description:
      'Риски, обязательства и регуляторные изменения становятся видны в едином decision-ready представлении.',
    capabilities: [
      'Risk overview',
      'Board reporting',
      'Compliance visibility',
    ],
    outcome: 'Единая картина вместо ручного контроля',
    videoSrc: '/right-video.mp4',
  },
};

export const ROLE_ORDER: RoleId[] = ['left', 'center', 'right'];

