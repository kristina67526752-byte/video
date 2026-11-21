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
  plugins: [react(), {
    // Файл для Netlify: прокси /sb/* → проект Supabase (чтобы сайт работал без прямого доступа к supabase.co).
    name: 'netlify-supabase-proxy',
    apply: 'build',
    generateBundle() {
      const url = process.env.VITE_SUPABASE_URL;
      if (mode === 'demo' || !url) return;
      this.emitFile({ type: 'asset', fileName: '_redirects', source: `/sb/*  ${url}/:splat  200!\n` });
    },
  }],
  base: './',
  define: { __DEMO__: JSON.stringify(mode === 'demo') },
  };
});
