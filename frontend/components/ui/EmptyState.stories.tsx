import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import EmptyState from './EmptyState';

const meta = {
  title: 'UI/EmptyState',
  component: EmptyState,
  args: { title: 'Нічого не знайдено', hint: 'Змініть фільтри або повернітесь пізніше.' },
} satisfies Meta<typeof EmptyState>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const WithLinkAction: Story = { args: { action: { label: 'До каталогу', href: '/ua' } } };
export const WithButtonAction: Story = { args: { action: { label: 'Скинути фільтри', onClick: () => {} } } };
