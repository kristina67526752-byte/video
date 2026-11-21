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

function normalizeUrl(v) {
  let u = v.replace(/\/+(rest\/v1)?\/*$/i, '');
  if (/^[a-z0-9]{15,30}$/i.test(u)) return `https://${u.toLowerCase()}.supabase.co`; // вставили Project ID
  if (!/^https?:\/\//i.test(u)) u = 'https://' + u;
  return u;
}

export function parseSettings(text) {
  const out = {};
  for (const line of text.replace(/^﻿/, '').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (!m) continue;
    // если значение вставили рядом со словом-заглушкой, а её не стёрли — убираем заглушку
    let v = cleanValue(m[2]).replace(/ВСТАВЬТЕ_(АДРЕС_ПРОЕКТА|КЛЮЧ_SERVICE_ROLE|КЛЮЧ_ANON)/gi, '');
    if (!v || /ВСТАВЬТЕ/i.test(v)) continue; // заглушка ещё не заменена
    if (m[1] === 'VITE_SUPABASE_URL') v = normalizeUrl(v);
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

// Понятная проверка файла настроек: что найдено и что не так.
export function diagnose() {
  const s = loadSettings();
  const problems = [];
  const url = s.VITE_SUPABASE_URL, anon = s.VITE_SUPABASE_ANON_KEY, service = s.SUPABASE_SERVICE_ROLE_KEY;
  if (!url) problems.push('Адрес проекта не найден: в строке VITE_SUPABASE_URL= всё ещё стоит ВСТАВЬТЕ_... или пусто.');
  else if (!/^https:\/\/[a-z0-9-]+\.supabase\.(co|in)$/i.test(url)) problems.push(`Адрес проекта выглядит странно: ${url} (нужен вида https://abcd1234.supabase.co).`);
  if (!anon) problems.push('Ключ anon не найден: в строке VITE_SUPABASE_ANON_KEY= всё ещё стоит ВСТАВЬТЕ_... или пусто.');
  else if (anon.startsWith('sb_')) problems.push('В строку anon вставлен ключ нового формата (sb_...). Нужен legacy-ключ anon, он начинается с eyJ.');
  else if (!anon.startsWith('eyJ')) problems.push('Ключ anon должен начинаться с eyJ — похоже, он скопирован не целиком.');
  if (!service) problems.push('Ключ service_role не найден (нужен только для загрузки заданий).');
  else if (service.startsWith('sb_')) problems.push('В строку service_role вставлен ключ нового формата (sb_...). Нужен legacy-ключ service_role (eyJ...).');
  const mask = (k) => (k ? k.slice(0, 10) + '…' + k.slice(-4) : 'НЕ НАЙДЕН');
  return { ok: problems.length === 0, problems, found: { url: url || 'НЕ НАЙДЕН', anon: mask(anon), service: service ? 'есть' : 'НЕ НАЙДЕН' }, fileExists: existsSync(SETTINGS_FILE) };
}

export function printDiagnosis() {
  const d = diagnose();
  console.log('\nФайл настроек: ' + SETTINGS_FILE + (d.fileExists ? '' : '  ✗ ФАЙЛ НЕ НАЙДЕН — он должен лежать в папке проекта!'));
  console.log('  Адрес проекта: ' + d.found.url);
  console.log('  Ключ anon:     ' + d.found.anon);
  console.log('  Ключ service_role: ' + d.found.service);
  if (d.ok) console.log('✓ Настройки в порядке.\n');
  else console.log('✗ Что исправить:\n  - ' + d.problems.join('\n  - ') + '\n  После исправления сохраните файл (Cmd+S) и перезапустите сайт.\n');
  return d;
}
