// src/marketing/components/home/ApplicationSection/types.ts

export type RoleId = 'left' | 'center' | 'right';

export type StoryPhase = 'intro' | 'left' | 'center' | 'right' | 'outro';

export type PanelState = 'hidden' | 'active' | 'dormant';

export interface RoleData {
  id: RoleId;
  title: string;
  subtitle: string;
  description: string;
  features: string[];
  videoSrc: string;
}

