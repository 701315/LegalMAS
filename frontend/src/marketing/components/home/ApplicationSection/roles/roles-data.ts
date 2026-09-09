// src/marketing/components/home/ApplicationSection/roles/roles-data.ts
import type { RoleId } from '../types';

/**
 * Порядок отображения ролей в UI.
 * Используется компонентами для итерации по ролям в правильном порядке.
 * 
 * Сами данные (title, description) теперь берутся из i18n:
 *   t(`application.roles.${roleId}.title`)
 *   t(`application.roles.${roleId}.description`)
 */
export const ROLE_ORDER: RoleId[] = ['ma', 'contract', 'compliance', 'audit', 'enrichment'];