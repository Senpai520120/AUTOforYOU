import { apiGet, apiPost } from './client';
import { DealerApplication } from '@/lib/types';

export interface ApplyPayload {
  company_name: string;
  full_name: string;
  contact_phone: string;
  documents?: string;
  // Обов'язкове: без згоди сервер відхиляє заявку з 400.
  agreed_to_processing: boolean;
  // Капча (задача 1.6): токен віджета або форм-токен honeypot + приховане поле.
  captcha_token?: string;
  website?: string;
}

export const dealersApi = {
  apply: (data: ApplyPayload) =>
    apiPost<DealerApplication>('/api/v1/dealers/apply/', data),

  getApplication: () =>
    apiGet<DealerApplication>('/api/v1/dealers/application/'),
};
