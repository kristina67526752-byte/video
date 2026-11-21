// Чтение настроек: сначала видимый файл «НАСТРОЙКИ.txt», затем .env.local и .env (если есть).
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

export const ROOT = fileURLToPath(new URL('..', import.meta.url));
export const SETTINGS_FILE = join(ROOT, 'НАСТРОЙКИ.txt');
const KEYS = ['VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY'];

function cleanValue(v) {
  // убираем пробелы, кавычки (в т.ч. «умные» из TextEdit) и невидимые символы
  return v.replace(/[​-‍﻿ ]/g, '').replace(/["'“”‘’«»]/g, '').replace(/\s+/g, '').trim();
}

export function parseSettings(text) {
  const out = {};
  for (const line of text.replace(/^﻿/, '').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (!m) continue;
    const v = cleanValue(m[2]);
    if (!v || /ВСТАВЬТЕ/i.test(v)) continue; // заглушка ещё не заменена
    out[m[1]] = v;
  }
  return out;
}

export function loadSettings() {
  const out = {};
  for (const path of [SETTINGS_FILE, join(ROOT, '.env.local'), join(ROOT, '.env')]) {
    if (!existsSync(path)) continue;
    const parsed = parseSettings(readFileSync(path, 'utf8'));
    for (const k of Object.keys(parsed)) if (!(k in out)) out[k] = parsed[k];
  }
  return out;
}

// Подставляет настройки в process.env (уже заданные переменные окружения не трогает).
export function applySettings() {
  const s = loadSettings();
  for (const k of KEYS) if (s[k] && !process.env[k]) process.env[k] = s[k];
  return s;
}
