import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Separator } from './separator';

const meta = { title: 'shadcn/Separator', component: Separator } satisfies Meta<typeof Separator>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Horizontal: Story = {
  render: () => (
    <div className="w-64">
      <p className="text-sm">Вище</p>
      <Separator className="my-3" />
      <p className="text-sm">Нижче</p>
    </div>
  ),
};
export const Vertical: Story = {
  render: () => (
    <div className="flex h-6 items-center gap-3 text-sm">
      Ліворуч
      <Separator orientation="vertical" />
      Праворуч
    </div>
  ),
};
