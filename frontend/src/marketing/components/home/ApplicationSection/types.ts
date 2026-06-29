// src/components/marketing/landing/ApplicationSection/types.ts

export type RoleId = 'left' | 'center' | 'right';

export type SequenceStep = 'black' | 'left' | 'center' | 'right' | 'idle';

export type PanelState = 'hidden' | 'active' | 'dormant';

export interface RoleData {
  id: RoleId;
  title: string;
  subtitle: string;
  description: string;
  features: string[];
  videoSrc: string;
}

