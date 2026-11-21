import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Label } from './label';
import { Input } from './input';

const meta = { title: 'shadcn/Label', component: Label } satisfies Meta<typeof Label>;
export default meta;
type Story = StoryObj<typeof meta>;

export const WithInput: Story = {
  render: () => (
    <div className="grid gap-2">
      <Label htmlFor="story-name">Імʼя</Label>
      <Input id="story-name" placeholder="Тест" />
    </div>
  ),
};
