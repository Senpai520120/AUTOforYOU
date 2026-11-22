import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import type { ReactNode } from 'react';
import CalcBreakdown from './CalcBreakdown';
import { fakeCalcResult } from '@/stories/fixtures/calc';
import { AuthProvider } from '@/lib/auth-context';

// Мережі немає: fetch підмінено глобально в .storybook/preview.ts (stories/fixtures/site.ts).
function FakeNetwork({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

const meta = {
  title: 'Calculator/CalcBreakdown',
  component: CalcBreakdown,
  args: { result: fakeCalcResult },
  parameters: { layout: 'padded' },
  decorators: [(Story) => <FakeNetwork><div className="max-w-3xl"><Story /></div></FakeNetwork>],
} satisfies Meta<typeof CalcBreakdown>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Demo: Story = {
  args: { result: { ...fakeCalcResult, is_demo: true, demo_banner: { title: 'Демо-розрахунок', text: 'Ставки тестові.' } } },
};
