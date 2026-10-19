import { apiGet, apiPost } from './client';
import type { Lead, LeadCreate, LeadCreated, PaginatedResponse } from '@/lib/types';

export const leadsApi = {
  create: (payload: LeadCreate) => apiPost<LeadCreated>('/api/v1/leads/', payload),
  mine: () => apiGet<PaginatedResponse<Lead>>('/api/v1/leads/mine/'),
};
