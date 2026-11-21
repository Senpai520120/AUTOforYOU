import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from './sheet';
import { Button } from './button';

const meta = { title: 'shadcn/Sheet', component: Sheet } satisfies Meta<typeof Sheet>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Closed: Story = {
  render: () => (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline">Відкрити панель</Button>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Панель</SheetTitle>
          <SheetDescription>Тестовий вміст бічної панелі.</SheetDescription>
        </SheetHeader>
      </SheetContent>
    </Sheet>
  ),
};
export const Open: Story = {
  render: () => (
    <Sheet defaultOpen>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Панель</SheetTitle>
          <SheetDescription>Тестовий вміст бічної панелі.</SheetDescription>
        </SheetHeader>
      </SheetContent>
    </Sheet>
  ),
};
