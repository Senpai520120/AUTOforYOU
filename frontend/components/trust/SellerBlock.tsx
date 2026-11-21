import Link from 'next/link';
import { LocalListing } from '@/lib/types';
import { SELLER_ALL_LISTINGS_LABEL, memberSinceLabel } from '@/lib/labels';

/** Блок продавця на сторінці оголошення (задача 8.6): «на сайті з …», активні оголошення, посилання на сторінку продавця. */
export default function SellerBlock({ listing }: { listing: LocalListing }) {
  if (!listing.seller_id) return null;
  const since = memberSinceLabel(listing.seller_member_since);
  const count = listing.seller_active_listings_count ?? 0;
  return (
    <div data-testid="seller-block" className="mt-1 text-xs text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1">
      {since && <span>{since}</span>}
      {count > 0 && <span>· активних оголошень: {count}</span>}
      <Link href={`/sellers/${listing.seller_id}`} className="text-primary underline underline-offset-4 hover:text-primary/80 font-medium">
        {SELLER_ALL_LISTINGS_LABEL}
      </Link>
    </div>
  );
}
