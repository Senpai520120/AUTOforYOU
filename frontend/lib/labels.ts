import type { LeadStatus } from './types';

/** Підписи статусів заявки для клієнта (шаг 6, задача 2.3). */
export const LEAD_STATUS_LABELS: Record<LeadStatus, string> = {
  new: 'Нова',
  in_progress: 'У роботі',
  contract: 'Договір',
  car_bought: 'Авто куплено',
  in_transit: 'В дорозі',
  customs: 'Розмитнення',
  delivered: 'Видано',
  rejected: 'Відмова',
  spam: 'Спам',
};

export function leadStatusLabel(status: string, fallback = ''): string {
  return (LEAD_STATUS_LABELS as Record<string, string>)[status] || fallback || status;
}
