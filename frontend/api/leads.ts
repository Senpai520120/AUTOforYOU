import { apiGet, apiPost } from './client';
import type {
  BrokerLeadDetail, BrokerLeadList, Lead, LeadCreate, LeadCreated, LeadPartnerStatus, LeadQuestionKey, LeadStatus,
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
  setQualification: (id: number, answers: Partial<Record<LeadQuestionKey, boolean | null>>) =>
    apiPost<BrokerLeadDetail>(`/api/v1/broker/leads/${id}/qualification/`, answers),
  exportUrl: (status: string) => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : '';
    return `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/v1/broker/leads/export.csv${qs}`;
  },
  setPartnerStatus: (id: number, partner_status: LeadPartnerStatus) =>
    apiPost<BrokerLeadDetail>(`/api/v1/broker/leads/${id}/partner-status/`, { partner_status }),
};
