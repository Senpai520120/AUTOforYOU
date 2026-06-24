import type { Listing } from './types';

/**
 * Generates a human-readable slug for a listing URL.
 * Format: {id}-{make}-{model}-{year}  e.g. "42-toyota-camry-2020"
 * parseInt(slug) always recovers the id for backend fetch.
 */
export function listingSlug(listing: Listing): string {
  const v = listing.vehicle_detail;
  const readable = `${v.make}-${v.model}-${v.year}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  return `${listing.id}-${readable}`;
}
