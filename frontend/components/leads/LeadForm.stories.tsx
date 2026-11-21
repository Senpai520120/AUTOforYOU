import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import type { ReactNode } from 'react';
import LeadForm from './LeadForm';
import { AuthProvider } from '@/lib/auth-context';

// Мережі немає: fetch підмінено глобально в .storybook/preview.ts (stories/fixtures/site.ts).
function FakeNetwork({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

const meta = {
  title: 'Leads/LeadForm',
  component: LeadForm,
  args: { source: 'calculator' },
  parameters: { layout: 'padded' },
  decorators: [(Story) => <FakeNetwork><div className="max-w-xl"><Story /></div></FakeNetwork>],
} satisfies Meta<typeof LeadForm>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const WithVehicle: Story = { args: { vehicleLabel: 'Toyota Camry 2019 (тест)' } };
