import type { LocalListing } from '@/lib/types';

/** Фейкова картка оголошення для stories (без ПДн, без мережі). Фото — data-URI. */
const PHOTO =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='300'%3E%3Crect width='400' height='300' fill='%23cbd5e1'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='20' fill='%231e293b'%3EТестове фото%3C/text%3E%3C/svg%3E";

export const fakeListing: LocalListing = {
  id: 1,
  make: 'Toyota',
  model: 'Camry',
  year: 2019,
  mileage_km: 84000,
  engine_cc: 2500,
  fuel_type: 'petrol',
  transmission: 'auto',
  body_type: 'sedan',
  condition: 'used',
  price: '18500',
  currency: 'USD',
  price_usd: '18500.00',
  price_type: 'negotiable',
  region: 1,
  region_name: 'Тестова область',
  city: 1,
  city_name: 'Тестове місто',
  description: 'Фейкове оголошення для Storybook.',
  status: 'active',
  seller_type: 'private',
  owner_name: 'Тест Продавець',
  contact_phone: null,
  rejection_reason: null,
  images: [{ id: 1, image: null, thumbnail: PHOTO, source_url: '', is_primary: true }],
  expires_at: null,
  expiry_warned: false,
  promoted_until: null,
  bumped_at: null,
  seller_has_badge: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};
