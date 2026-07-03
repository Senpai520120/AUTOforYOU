import { apiPost } from './client';
import { ReportPayload } from '@/lib/types';

export const reportsApi = {
  create: (data: ReportPayload) =>
    apiPost<{ id: number }>('/api/v1/reports/', data),
};
