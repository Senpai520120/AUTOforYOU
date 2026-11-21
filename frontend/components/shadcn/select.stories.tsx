import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './select';

const meta = { title: 'shadcn/Select', component: Select } satisfies Meta<typeof Select>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Select defaultValue="petrol">
      <SelectTrigger className="w-48" aria-label="Паливо">
        <SelectValue placeholder="Паливо" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="petrol">Бензин</SelectItem>
        <SelectItem value="diesel">Дизель</SelectItem>
        <SelectItem value="electric">Електро</SelectItem>
      </SelectContent>
    </Select>
  ),
};
export const Placeholder: Story = {
  render: () => (
    <Select>
      <SelectTrigger className="w-48" aria-label="Паливо">
        <SelectValue placeholder="Оберіть паливо" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="petrol">Бензин</SelectItem>
      </SelectContent>
    </Select>
  ),
};
