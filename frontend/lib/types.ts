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
  image: string | null;   // null when photo lives only in source_url
  source_url: string;     // original URL from auction lot import
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

// ─── C2C: місцеві оголошення ─────────────────────────────────────────────────

export interface Region {
  id: number;
  name: string;
  slug: string;
}

export interface City {
  id: number;
  name: string;
  slug: string;
  region: number;
  region_name: string;
}

export type LocalFuelType = 'petrol' | 'diesel' | 'electric' | 'hybrid' | 'gas';
export type LocalTransmission = 'auto' | 'manual' | 'cvt' | 'robot';
export type LocalBodyType = 'sedan' | 'suv' | 'hatchback' | 'wagon' | 'coupe' | 'minivan' | 'pickup' | 'convertible' | 'other';
export type LocalCondition = 'new' | 'used' | 'damaged';
export type LocalStatus = 'draft' | 'active' | 'pending' | 'rejected' | 'expired' | 'sold' | 'hidden';
export type LocalCurrency = 'UAH' | 'USD' | 'EUR';
export type LocalPriceType = 'fixed' | 'negotiable';
export type LocalSellerType = 'private' | 'dealer';

export interface LocalListingImage {
  id: number;
  image: string | null;
  source_url: string;
  is_primary: boolean;
}

export interface LocalListing {
  id: number;
  make: string;
  model: string;
  year: number;
  mileage_km: number;
  engine_cc: number | null;
  fuel_type: LocalFuelType;
  transmission: LocalTransmission;
  body_type: LocalBodyType;
  condition: LocalCondition;
  price: string;
  currency: LocalCurrency;
  price_type: LocalPriceType;
  region: number;
  region_name: string;
  city: number;
  city_name: string;
  description: string;
  status: LocalStatus;
  seller_type: LocalSellerType;
  owner_name: string;
  contact_phone: string | null;
  rejection_reason: string | null;
  images: LocalListingImage[];
  expires_at: string | null;
  expiry_warned: boolean;
  promoted_until: string | null;
  bumped_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromotionTariff {
  id: number;
  code: string;
  name: string;
  type: 'renew' | 'bump' | 'top';
  price: string;
  currency: string;
  duration_days: number;
  description: string;
}

export interface PromoteCheckout {
  payment_id: number;
  order_id: string;
  tariff: string;
  amount: string;
  currency: string;
  checkout_url: string;
  form_data: Record<string, string>;
  sandbox: boolean;
}

export interface LocalListingFilters {
  make?: string;
  model?: string;
  year_min?: string;
  year_max?: string;
  price_min?: string;
  price_max?: string;
  fuel_type?: string;
  transmission?: string;
  body_type?: string;
  region?: string;
  city?: string;
  mileage_max?: string;
  search?: string;
  ordering?: string;
  page?: number;
}

// ─── Messaging ───────────────────────────────────────────────────────────────

export interface MessageParticipant {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
}

export interface ChatMessage {
  id: number;
  sender: number;
  sender_name: string;
  text: string;
  created_at: string;
  read_at: string | null;
}

export interface ConversationSummary {
  id: number;
  subject_title: string;
  subject_url: string;
  other_participant: MessageParticipant | null;
  last_message_text: string;
  last_message_at: string;
  unread_count: number;
}

export interface ConversationDetail {
  id: number;
  subject_title: string;
  subject_url: string;
  participants: MessageParticipant[];
  messages: ChatMessage[];
  created_at: string;
  last_message_at: string;
}

export interface StartConversationResult {
  conversation_id: number;
  created: boolean;
}

// ─── Notifications ───────────────────────────────────────────────────────────

export type NotificationType =
  | 'new_message'
  | 'listing_approved'
  | 'listing_rejected'
  | 'listing_expiring'
  | 'saved_search_match';

export interface AppNotification {
  id: number;
  type: NotificationType;
  title: string;
  text: string;
  link: string;
  is_read: boolean;
  created_at: string;
}

// ─── Favorites ───────────────────────────────────────────────────────────────

export interface FavoriteItem {
  id: number;
  listing_type: 'local' | 'imported';
  listing_id: number;
  title: string;
  url: string;
  price: string | null;
  currency: string | null;
  image_url: string | null;
  created_at: string;
}

// ─── Saved searches ──────────────────────────────────────────────────────────

export interface SavedSearch {
  id: number;
  name: string;
  filters: Record<string, string>;
  notify: boolean;
  last_notified_at: string | null;
  created_at: string;
}

export interface VinPrefillResult {
  make: string | null;
  model: string | null;
  year: number | null;
  engine_cc: number | null;
  fuel_type: string | null;
  body_class: string | null;
  cached: boolean;
  error?: string;
}
