import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';
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
  }, {
    // Список заданий БЕЗ ответов и разборов кладём рядом с сайтом (catalog.json), чтобы не тянуть его из базы.
    name: 'static-catalog',
    apply: 'build',
    generateBundle() {
      if (mode === 'demo') return;
      const d = JSON.parse(readFileSync(new URL('./data/tasks.json', import.meta.url), 'utf8'));
      const tasks = d.tasks.map(({ answers: _a, explanation: _e, ...t }: Record<string, unknown>) => t);
      this.emitFile({ type: 'asset', fileName: 'catalog.json', source: JSON.stringify({ sections: d.sections, passages: d.passages, tasks }) });
    },
  }],
  base: './',
  define: { __DEMO__: JSON.stringify(mode === 'demo') },
  };
});
