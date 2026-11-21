import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Textarea } from './textarea';

const meta = {
  title: 'shadcn/Textarea',
  component: Textarea,
  args: { 'aria-label': 'Коментар', placeholder: 'Ваш коментар' },
} satisfies Meta<typeof Textarea>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Disabled: Story = { args: { disabled: true } };
