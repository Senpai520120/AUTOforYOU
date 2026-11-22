import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './card';
import { Button } from './button';

const meta = { title: 'shadcn/Card', component: Card } satisfies Meta<typeof Card>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Card className="w-80">
      <CardHeader>
        <CardTitle>Заголовок картки</CardTitle>
        <CardDescription>Короткий опис тестової картки.</CardDescription>
      </CardHeader>
      <CardContent>Вміст картки.</CardContent>
      <CardFooter>
        <Button size="sm">Дія</Button>
      </CardFooter>
    </Card>
  ),
};
