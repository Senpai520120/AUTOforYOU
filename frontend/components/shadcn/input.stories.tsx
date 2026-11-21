import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Input } from './input';

const meta = {
  title: 'shadcn/Input',
  component: Input,
  args: { 'aria-label': 'Поле вводу', placeholder: 'Введіть текст' },
} satisfies Meta<typeof Input>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Filled: Story = { args: { defaultValue: 'Значення' } };
export const Disabled: Story = { args: { disabled: true } };
export const Invalid: Story = { args: { 'aria-invalid': true, defaultValue: 'Помилка' } };
