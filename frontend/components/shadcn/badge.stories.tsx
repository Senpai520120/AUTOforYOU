import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Badge } from './badge';

const meta = { title: 'shadcn/Badge', component: Badge, args: { children: 'Новий' } } satisfies Meta<typeof Badge>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Secondary: Story = { args: { variant: 'secondary' } };
export const Destructive: Story = { args: { variant: 'destructive', children: 'Помилка' } };
export const Outline: Story = { args: { variant: 'outline' } };
