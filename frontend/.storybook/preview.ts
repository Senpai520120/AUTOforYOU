import type { Preview } from '@storybook/nextjs-vite';
// Токени дизайн-системи (11.13) і Tailwind: той самий файл, що й у застосунку.
import '../app/globals.css';
import { installFakeFetch } from '../stories/fixtures/site';

// Жодних запитів до API: fetch підмінено до першого рендеру (форми та AuthProvider ходять в API з ефектів).
installFakeFetch();

// Шрифт: next/font/google (Manrope) у Storybook вимагав би мережі при збірці, тому тут його немає.
// --font-sans у globals.css падає на ui-sans-serif/system-ui. Метрики тексту трохи інші, ніж на сайті.

const preview: Preview = {
  parameters: {
    layout: 'centered',
    controls: { matchers: { color: /(background|color)$/i, date: /Date$/i } },
    // a11y: порушення роблять тест-прогін Storybook червоним (не ігноруються мовчки).
    a11y: { test: 'error' },
    nextjs: { appDirectory: true },
  },
};

export default preview;
