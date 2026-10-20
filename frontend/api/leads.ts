import { apiGet, apiPost } from './client';
import type {
  BrokerLeadDetail, BrokerLeadList, Lead, LeadCreate, LeadCreated, LeadPartnerStatus, LeadStatus,
  PaginatedResponse,
} from '@/lib/types';

export const leadsApi = {
  create: (payload: LeadCreate) => apiPost<LeadCreated>('/api/v1/leads/', payload),
  mine: () => apiGet<PaginatedResponse<Lead>>('/api/v1/leads/mine/'),
};

export const brokerLeadsApi = {
  list: (params: Record<string, string>) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
    return apiGet<BrokerLeadList>(`/api/v1/broker/leads/${qs ? `?${qs}` : ''}`);
  },
  detail: (id: number) => apiGet<BrokerLeadDetail>(`/api/v1/broker/leads/${id}/`),
  take: (id: number) => apiPost<BrokerLeadDetail>(`/api/v1/broker/leads/${id}/take/`),
  setStatus: (id: number, status: LeadStatus, note: string) =>
    apiPost<BrokerLeadDetail>(`/api/v1/broker/leads/${id}/status/`, { status, note }),
  setPartnerStatus: (id: number, partner_status: LeadPartnerStatus) =>
    apiPost<BrokerLeadDetail>(`/api/v1/broker/leads/${id}/partner-status/`, { partner_status }),
};
