import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { applySettings, printDiagnosis } from './scripts/settings.mjs';

// Адрес проекта и anon-ключ берутся из файла «НАСТРОЙКИ.txt» (или из .env.local).
applySettings();

// В демо-режиме (npm run demo) задания с ответами подключаются прямо в браузер — только для локального просмотра.
// В обычной сборке этот код вырезается, и ответы на сайт не попадают.
export default defineConfig(({ mode }) => {
  if (mode !== 'demo') printDiagnosis();
  return {
  plugins: [react()],
  base: './',
  define: { __DEMO__: JSON.stringify(mode === 'demo') },
  };
});
