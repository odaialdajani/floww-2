import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { transformWithEsbuild } from 'vite';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export default {
  framework: '@storybook/react-vite',
  stories: ['../src/**/*.stories.@(js|jsx|mjs|ts|tsx)'],
  addons: ['@storybook/addon-docs', '@storybook/addon-a11y', '@storybook/addon-vitest'],
  core: { disableTelemetry: true },
  async viteFinal(config) {
    config.resolve ??= {};
    config.plugins ??= [];
    config.resolve.alias = { ...config.resolve.alias, '@': path.join(root, 'src') };
    config.resolve.dedupe = [...new Set([...(config.resolve.dedupe || []), 'react', 'react-dom'])];
    config.optimizeDeps ??= {};
    config.optimizeDeps.include = [...new Set([...(config.optimizeDeps.include || []), 'react', 'react-dom', 'react/jsx-runtime', 'react/jsx-dev-runtime'])];
    config.define = { ...config.define, 'process.env.REACT_APP_BACKEND_URL': '""',
      'process.env.REACT_APP_STEAL_THREE_BASE': '""', 'process.env.REACT_APP_API_BASE': '""',
      'process.env.REACT_APP_API_URL': '""', 'process.env.REACT_APP_ALPHAPOD_PROXY': '"false"' };
    config.plugins.unshift({
      name: 'solstice-js-as-jsx', enforce: 'pre',
      async transform(code, id) {
        if (!id.startsWith(path.join(root, 'src')) || !id.endsWith('.js')) return null;
        return transformWithEsbuild(code, id, { loader: 'jsx', jsx: 'automatic' });
      },
    });
    return config;
  },
};
