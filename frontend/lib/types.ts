export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  role: 'buyer' | 'dealer' | 'admin';
  is_verified_dealer: boolean;
  created_at: string;
}

export interface VehicleImage {
  id: number;
  image: string;
  is_primary: boolean;
}

export interface Vehicle {
  id: number;
  vin: string;
  make: string;
  model: string;
  year: number;
  engine_cc: number;
  fuel_type: 'petrol' | 'diesel' | 'electric' | 'hybrid';
  mileage_km: number;
  damage_type: string;
  source_auction: 'copart' | 'iaai' | 'other';
  lot_number: string;
  images: VehicleImage[];
  created_at: string;
}

export interface Listing {
  id: number;
  vehicle: number;
  vehicle_detail: Vehicle;
  seller: number;
  price: string;
  currency: 'USD' | 'UAH' | 'EUR';
  channel: 'retail' | 'wholesale';
  status: 'in_transit' | 'in_stock' | 'sold';
  repair_description: string;
  calculation: number | null;
  is_express_buyout: boolean;
  express_buyout_until: string | null;
  is_express_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface CalcBreakdown {
  auction_price_usd: string;
  auction_fee_usd: string;
  us_land_usd: string;
  ocean_freight_usd: string;
  eu_to_ua_usd: string;
  customs_value_usd: string;
  excise_eur: string;
  excise_uah: string;
  duty_usd: string;
  duty_uah: string;
  vat_base_uah: string;
  vat_uah: string;
  pension_fund_uah: string;
  customs_total_uah: string;
  total_usd: string;
  total_uah: string;
  is_estimate: boolean;
}

export interface CalcResult {
  calculation_id: number;
  is_estimate: boolean;
  warning: string;
  breakdown: CalcBreakdown;
}

export interface TrackingEvent {
  id: number;
  status: string;
  status_display: string;
  note: string;
  photo: string | null;
  created_at: string;
}

export interface Shipment {
  id: number;
  container_no: string;
  vessel: string;
  arrival_port_eu: string;
  arrival_port_eu_display: string;
  eta: string | null;
  status: string;
  status_display: string;
  vehicle_count: number;
  events?: TrackingEvent[];
  created_at: string;
}

export interface Calculation {
  id: number;
  inputs_snapshot: Record<string, unknown>;
  breakdown: CalcBreakdown;
  total_usd: string;
  total_uah: string;
  is_estimate: boolean;
  created_at: string;
}

export interface TrustedShop {
  id: number;
  name: string;
  type: 'service' | 'painter' | 'parts' | 'other';
  contacts: string;
  rating: number;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface DealerApplication {
  id: number;
  company_name: string;
  full_name: string;
  contact_phone: string;
  documents: string;
  status: 'pending' | 'approved' | 'rejected';
  review_notes: string;
  created_at: string;
  reviewed_at: string | null;
}

export interface Tokens {
  access: string;
  refresh: string;
}
