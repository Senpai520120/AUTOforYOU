export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  // role — мітка, а не привілей. Нова реєстрація завжди 'buyer'; broker, moderator
  // і admin призначає лише адмін. Права перевіряються по is_admin_role і is_verified_dealer (is_staff — лише доступ в адмінку).
  role: 'buyer' | 'dealer' | 'broker' | 'moderator' | 'admin';
  is_verified_dealer: boolean;
  is_email_verified: boolean;
  is_staff: boolean;
  is_admin_role: boolean;
  created_at: string;
  telegram_id: number | null;
  // Період скасування видалення (1.8): дата остаточного видалення або null.
  deletion_scheduled_for: string | null;
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
  // 2.7: після розмитнення; null / pending — «уточнюється менеджером»
  ua_delivery_usd: string | null;
  ua_delivery_pending: boolean;
  broker_services: { title: string; amount_usd: string }[];
  broker_services_total_usd: string;
  broker_services_pending: boolean;
}

export interface CalcResult {
  calculation_id: number;
  is_estimate: boolean;
  // Q5: правило розмитнення звірено з брокером; поки false — «Орієнтовний розрахунок».
  rules_confirmed: boolean;
  rates_validity_date: string;
  rates_updated_on: string | null;
  exchange_rate_date: string;
  warning: string;
  // 2.6: демо — є неперевірена застосована ставка або курс із сиду; лише тоді показується демо-банер.
  is_demo: boolean;
  estimate_note: string;
  demo_banner: DemoBannerTexts;
  // Ставки рядком Decimal ("0.1000"), для підписів «Мито 10%».
  applied_rates: {
    duty_rate: string;
    vat_rate: string;
    pension_fund_rate: string;
    excise_eur_per_100cc?: string;
    ev_excise_eur_per_kwh?: string;
  };
  breakdown: CalcBreakdown;
}

export interface DemoBannerTexts {
  title: string;
  text: string;
}

export interface CalcOption {
  value: string;
  label: string;
}

// GET /api/v1/pricing/rates/ (2.6, Q11): довідники форми з активних тарифів, без сум.
export interface CalcOptions {
  auctions: CalcOption[];
  auction_locations: (CalcOption & { us_ports: string[] })[];
  us_ports: (CalcOption & { eu_ports: string[] })[];
  eu_ports: CalcOption[];
  fuel_types: (CalcOption & { requires_battery: boolean })[];
  member_types: CalcOption[];
  payment_types: CalcOption[];
  title_types: CalcOption[];
  defaults: { member_type: string | null; payment_type: string | null; title_type: string | null };
  is_configured: boolean;
}

// 2.7 (Q11): гостям — без сум; суми приходять у розрахунку.
export interface UaDeliveryOption {
  id: number;
  destination: string;
  eu_port: string | null;
  quote_on_request: boolean;
}

export interface CalcRatesResponse {
  options: CalcOptions;
  ua_delivery_rates: UaDeliveryOption[];
  broker_service_fees: { id: number; title: string }[];
  is_demo: boolean;
  demo_banner: DemoBannerTexts;
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
  /** true только для владельца (есть в детали объявления) */
  is_owner?: boolean;
  contact_phone: string | null;
  rejection_reason: string | null;
  images: LocalListingImage[];
  expires_at: string | null;
  expiry_warned: boolean;
  promoted_until: string | null;
  bumped_at: string | null;
  seller_has_badge: boolean;
  seller_avg_rating?: number | null;
  seller_deal_count?: number;
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
  display_name: string;
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
  | 'saved_search_match'
  | 'deal_proposed'
  | 'deal_confirmed'
  | 'deal_cancelled'
  | 'review_received';

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

// ─── Reports ─────────────────────────────────────────────────────────────────

export type ReportReason = 'spam' | 'wrong_info' | 'inappropriate' | 'fraud' | 'duplicate' | 'other';

export interface ReportPayload {
  listing?: number;
  reported_user?: number;
  reason: ReportReason;
  comment?: string;
}

// ─── Deals & Reviews ─────────────────────────────────────────────────────────

export type DealStatus = 'proposed' | 'confirmed' | 'cancelled';

export interface DealUser {
  id: number;
  display_name: string;
}

export interface DealListing {
  id: number;
  make: string;
  model: string;
  year: number;
}

export interface DealReview {
  id: number;
  rating: number;
  text: string;
  author_name: string;
  created_at: string;
}

export interface Deal {
  id: number;
  listing: DealListing;
  seller: DealUser;
  buyer: DealUser;
  status: DealStatus;
  created_at: string;
  confirmed_at: string | null;
  review: DealReview | null;
}

export interface ReviewPayload {
  rating: number;
  text?: string;
}

export interface SellerRating {
  confirmed_deal_count: number;
  review_count: number;
  avg_rating: number | null;
  has_badge: boolean;
  badge_threshold: number;
}

export type OwnerLegalForm = 'fop' | 'tov' | 'other' | '';

/** Публічні налаштування сайту (GET /api/v1/site-settings/). */
export interface SiteSettings {
  owner_legal_form: OwnerLegalForm;
  owner_legal_name: string;
  owner_code: string;
  owner_address: string;
  support_email: string;
  privacy_email: string;
  phone: string;
  manager_contact: string;
  telegram_channel_url: string;
  partner_name: string;
  partner_legal_name: string;
  /** Готовий текст згоди партнеру (єдине джерело — бекенд; порожній, якщо партнера немає). */
  partner_consent_text: string;
  data_retention_years: number | null;
  log_retention_days: number;
  account_deletion_grace_days: number;
  legal_docs_approved: boolean;
  legal_docs_updated_at: string | null;
  legal_docs_version: string;
  legal_docs_reconsent_required: boolean;
  owner_configured: boolean;
  /** Флаги модулів (задача 2.8): джерело правди — .env бекенда, лише читання. */
  lots_enabled: boolean;
  b2b_enabled: boolean;
  dealers_enabled: boolean;
  shipments_enabled: boolean;
  vin_reports_enabled: boolean;
  /** Розділ «Оголошення по Україні» і платежі (задача 6.7): джерело правди — .env бекенда. */
  c2c_enabled: boolean;
  /** false = «засів»: оголошення вносить staff, підача/переписка/угоди закриті. */
  c2c_public_posting_enabled: boolean;
  payments_enabled: boolean;
  /** Партнерське посилання carVertical (3.2a); порожній рядок — посилання немає. */
  carvertical_partner_url: string;
  /** Публічна конфігурація (задача 6.4): лімити оголошень і ім'я бота з .env бекенда. */
  local_listing_max_active: number;
  local_listing_expiry_days: number;
  local_listing_max_photos: number;
  local_listing_photo_max_size_mb: number;
  /** Ім'я бота без @; порожній рядок — бот не налаштований. */
  telegram_bot_username: string;
}

// Заявки брокеру (задача 2.3)
export type LeadStatus =
  | 'new' | 'in_progress' | 'contract' | 'car_bought' | 'in_transit'
  | 'customs' | 'delivered' | 'rejected' | 'spam';
export type LeadSource = 'calculator' | 'listing' | 'landing';
export type LeadContactMethod = 'phone' | 'telegram' | 'viber';
export type LeadNeededWhen = 'asap' | 'month' | 'three_months' | 'later';

export interface LeadCreate {
  name: string;
  phone: string;
  email?: string;
  contact_method?: LeadContactMethod;
  contact_handle?: string;
  comment?: string;
  source: LeadSource;
  landing_slug?: string;
  calculation_id?: number | null;
  listing_id?: number | null;
  budget_usd?: string | null;
  needed_when?: LeadNeededWhen | '';
  city?: string;
  vehicle_label?: string;
  utm?: Record<string, string>;
  referrer?: string;
  entry_page_url?: string;
  page_url?: string;
  consent: boolean;
  partner_consent: boolean;
  // Антиспам (задача 1.6): токен капчі і приховане поле honeypot.
  captcha_token?: string;
  website?: string;
}

export interface LeadCreated {
  public_id: string;
  status: LeadStatus;
  created_at: string;
}

export interface Lead {
  id: number;
  public_id: string;
  status: LeadStatus;
  status_display: string;
  source: LeadSource;
  vehicle_label: string;
  total_usd: string | null;
  total_uah: string | null;
  listing_id: number | null;
  created_at: string;
}

// Кабінет брокера (задача 2.4)
export type LeadQualification = 'unrated' | 'hot' | 'cold';
export type LeadQuestionKey = 'q_budget_ok' | 'q_term_ok' | 'q_knows_repair' | 'q_ready_deposit';
export type LeadPartnerStatus = '' | 'no_answer' | 'thinking' | 'deposit' | 'bought' | 'rejected';

// email приходить лише для себе й адміна; для інших — тільки відображуване ім’я.
export interface BrokerStaffRef {
  id: number;
  name: string;
  email?: string;
}

export interface BrokerLeadRow {
  id: number;
  public_id: string;
  created_at: string;
  name: string;
  phone: string;
  contact_method: LeadContactMethod | '';
  status: LeadStatus;
  status_display: string;
  partner_status: LeadPartnerStatus;
  partner_status_display: string;
  qualification: LeadQualification;
  qualification_display: string;
  total_usd: string | null;
  total_uah: string | null;
  source: LeadSource;
  source_display: string;
  utm_source: string;
  first_response_at: string | null;
  assigned_to: BrokerStaffRef | null;
  car: string;
}

export interface BrokerLeadHistoryItem {
  id: number;
  from_status: string;
  from_status_display: string;
  to_status: string;
  to_status_display: string;
  changed_by: BrokerStaffRef | null;
  note: string;
  created_at: string;
}

export interface BrokerLeadDetail extends BrokerLeadRow {
  email: string;
  contact_method_display: string;
  contact_handle: string;
  comment: string;
  budget_usd: string | null;
  needed_when: LeadNeededWhen | '';
  needed_when_display: string;
  city: string;
  utm: Record<string, string>;
  referrer: string;
  entry_page_url: string;
  page_url: string;
  calculation_snapshot: {
    created_at?: string;
    is_estimate?: boolean;
    inputs_snapshot?: Record<string, unknown>;
    rates_snapshot?: Record<string, unknown>;
    breakdown?: Record<string, unknown>;
    total_usd?: string;
    total_uah?: string;
  };
  listing: { id: number; url: string } | null;
  history: BrokerLeadHistoryItem[];
  allowed_transitions: LeadStatus[];
  partner_name: string;
  updated_at: string;
  q_budget_ok: boolean | null;
  q_term_ok: boolean | null;
  q_knows_repair: boolean | null;
  q_ready_deposit: boolean | null;
  attribution_until: string | null;
}

export interface BrokerLeadList extends PaginatedResponse<BrokerLeadRow> {
  new_count: number;
}

/** Сторінки довіри (задача 2.13): GET /api/v1/content/how-it-works/ і /faq/. Усе — звичайний текст. */
export interface ImportStepItem {
  title: string;
  description: string;
  duration: string;
}

export interface FaqEntry {
  question: string;
  answer: string;
}

export interface HowItWorksData {
  published: boolean;
  steps: ImportStepItem[];
  faq: FaqEntry[];
}
