import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './tabs';

const meta = { title: 'shadcn/Tabs', component: Tabs } satisfies Meta<typeof Tabs>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Tabs defaultValue="a" className="w-80">
      <TabsList>
        <TabsTrigger value="a">Перша</TabsTrigger>
        <TabsTrigger value="b">Друга</TabsTrigger>
      </TabsList>
      <TabsContent value="a">Вміст першої вкладки.</TabsContent>
      <TabsContent value="b">Вміст другої вкладки.</TabsContent>
    </Tabs>
  ),
};
