import { apiPost, apiGet } from './client';
import { CalcRatesResponse, CalcResult, Calculation, PaginatedResponse } from '@/lib/types';

export interface CalcInputs {
  auction_price_usd: string;
  engine_cc: number;
  fuel_type: string;
  vehicle_year: number;
  auction: string;
  auction_location: string;
  us_port: string;
  eu_port: string;
  member_type?: string;
  payment_type?: string;
  title_type?: string;
  // Ємність батареї, кВт·год (2.5): лише для electric/phev, рядок як у полі форми (напр. "75.5")
  battery_capacity_kwh?: string;
}

export const pricingApi = {
  options: () => apiGet<CalcRatesResponse>('/api/v1/pricing/rates/'),

  calculate: (inputs: CalcInputs) =>
    apiPost<CalcResult>('/api/v1/pricing/calculate/', inputs),

  myCalculations: () =>
    apiGet<PaginatedResponse<Calculation>>('/api/v1/auth/me/calculations/'),
};
