import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import ErrorState from './ErrorState';

const meta = {
  title: 'UI/ErrorState',
  component: ErrorState,
  args: { error: new Error('Не вдалося завантажити дані') },
} satisfies Meta<typeof ErrorState>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const WithRetry: Story = { args: { onRetry: () => {} } };
