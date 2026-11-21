import type { StorybookConfig } from '@storybook/nextjs-vite';

const config: StorybookConfig = {
  stories: ['../components/**/*.stories.@(ts|tsx)', '../stories/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-a11y', '@storybook/addon-docs'],
  framework: { name: '@storybook/nextjs-vite', options: {} },
  staticDirs: [],
  // Кеш Vite/Storybook лишається в frontend/node_modules/.cache (диск D), а не в %LOCALAPPDATA% на C.
  viteFinal: async (cfg) => ({ ...cfg, cacheDir: 'node_modules/.cache/storybook-vite' }),
};

export default config;
