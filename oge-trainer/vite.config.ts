import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// В демо-режиме (npm run demo) задания с ответами подключаются прямо в браузер — только для локального просмотра.
// В обычной сборке этот код вырезается, и ответы на сайт не попадают.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: './',
  define: { __DEMO__: JSON.stringify(mode === 'demo') },
}));
