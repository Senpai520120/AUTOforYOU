import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import LocalListingCard from './LocalListingCard';
import { fakeListing } from '@/stories/fixtures/listings';

const meta = {
  title: 'Local/LocalListingCard',
  component: LocalListingCard,
  args: { listing: fakeListing },
  decorators: [(Story) => <div className="w-80"><Story /></div>],
} satisfies Meta<typeof LocalListingCard>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Top: Story = {
  args: { listing: { ...fakeListing, promoted_until: '2999-01-01T00:00:00Z' } },
};
export const Dealer: Story = {
  args: { listing: { ...fakeListing, seller_type: 'dealer', seller_has_badge: true } },
};
export const Electric: Story = {
  args: { listing: { ...fakeListing, fuel_type: 'electric', engine_cc: null } },
};
