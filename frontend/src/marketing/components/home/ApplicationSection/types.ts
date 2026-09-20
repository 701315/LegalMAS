// src/marketing/components/home/ApplicationSection/types.ts

// Синхронизировано с массивом ORDER в ApplicationSection.tsx
export type RoleId = 'ma' | 'contract' | 'compliance' | 'audit' | 'enrichment';

export interface RoleData {
  id: RoleId;
  title: string;
  description: string;
}