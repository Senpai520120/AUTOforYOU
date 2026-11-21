import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Button } from './button';

const meta = { title: 'shadcn/Button', component: Button, args: { children: 'Надіслати' } } satisfies Meta<typeof Button>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Secondary: Story = { args: { variant: 'secondary' } };
export const Outline: Story = { args: { variant: 'outline' } };
export const Ghost: Story = { args: { variant: 'ghost' } };
export const Link: Story = { args: { variant: 'link' } };
export const Destructive: Story = { args: { variant: 'destructive', children: 'Видалити' } };
export const Disabled: Story = { args: { disabled: true } };
export const Small: Story = { args: { size: 'sm' } };
export const Large: Story = { args: { size: 'lg' } };
