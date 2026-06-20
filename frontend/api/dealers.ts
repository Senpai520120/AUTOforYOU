import { apiGet, apiPost } from './client';
import { DealerApplication } from '@/lib/types';

export interface ApplyPayload {
  company_name: string;
  full_name: string;
  contact_phone: string;
  documents?: string;
}

export const dealersApi = {
  apply: (data: ApplyPayload) =>
    apiPost<DealerApplication>('/api/v1/dealers/apply/', data),

  getApplication: () =>
    apiGet<DealerApplication>('/api/v1/dealers/application/'),
};
