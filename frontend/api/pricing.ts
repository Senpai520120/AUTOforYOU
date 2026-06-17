import { apiPost, apiGet } from './client';
import { CalcResult, Calculation, PaginatedResponse } from '@/lib/types';

export interface CalcInputs {
  auction_price_usd: string;
  engine_cc: number;
  fuel_type: string;
  vehicle_year: number;
  auction: string;
  auction_location: string;
  us_port: string;
  eu_port: string;
}

export const pricingApi = {
  calculate: (inputs: CalcInputs) =>
    apiPost<CalcResult>('/api/v1/pricing/calculate/', inputs),

  myCalculations: () =>
    apiGet<PaginatedResponse<Calculation>>('/api/v1/auth/me/calculations/'),
};
