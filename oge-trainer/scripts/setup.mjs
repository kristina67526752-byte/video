// Мастер настройки: спрашивает адрес проекта Supabase и ключи, создаёт .env.local,
// проверяет подключение и (по желанию) загружает задания.
//   npm run setup
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { loadSettings, SETTINGS_FILE } from './settings.mjs';
import { createInterface } from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const envPath = new URL('../.env.local', import.meta.url);
const rl = createInterface({ input: stdin, output: stdout });

const line = () => console.log('─'.repeat(60));
const clean = (s) => s.trim().replace(/^['"]|['"]$/g, '').replace(/\s+/g, '');

function current() {
  return loadSettings();
}

async function ask(question, check, fallback) {
  for (;;) {
    const hint = fallback ? ` [Enter — оставить прежний]` : '';
    const raw = await rl.question(`${question}${hint}\n> `);
    const v = clean(raw);
    if (!v && fallback) return fallback;
    const err = check(v);
    if (!err) return v;
    console.log(`  ✗ ${err}\n`);
  }
}

function toUrl(v) {
  if (/^https:\/\/[a-z0-9-]+\.supabase\.(co|in)\/?$/i.test(v)) return v.replace(/\/$/, '');
  if (/^[a-z0-9]{15,30}$/i.test(v)) return `https://${v.toLowerCase()}.supabase.co`;
  return null;
}

function jwtRole(key) {
  try { return JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString()).role; } catch { return null; }
}

const checkUrl = (v) => (toUrl(v) ? null : 'Нужен адрес вида https://abcd1234.supabase.co (или просто Project ID).');
const checkKey = (role) => (v) => {
  if (v.startsWith('sb_')) return 'Это ключ нового формата (sb_...). Нажмите «View legacy API keys» и скопируйте ключ, который начинается с eyJ.';
  if (!v.startsWith('eyJ') || v.split('.').length !== 3) return 'Ключ должен начинаться с eyJ и состоять из трёх частей через точку. Скопируйте его целиком.';
  const r = jwtRole(v);
  if (r && r !== role) return `Это ключ «${r}», а здесь нужен «${role}».`;
  return null;
};

console.log('\nНастройка тренажёра ОГЭ English');
line();
console.log('Откройте Supabase → Project Settings → API Keys → «View legacy API keys».');
console.log('Скопируйте значения и вставляйте их по одному (Cmd+V / Ctrl+V, затем Enter).\n');

const prev = current();
const url = toUrl(await ask('1) Адрес проекта (Project URL) или Project ID:', checkUrl, prev.VITE_SUPABASE_URL));
const anon = await ask('\n2) Ключ anon (public):', checkKey('anon'), prev.VITE_SUPABASE_ANON_KEY);
const service = await ask('\n3) Ключ service_role (secret) — нажмите Reveal, чтобы увидеть его:', checkKey('service_role'), prev.SUPABASE_SERVICE_ROLE_KEY);

let text = existsSync(SETTINGS_FILE) ? readFileSync(SETTINGS_FILE, 'utf8') : '';
for (const [k, v] of [['VITE_SUPABASE_URL', url], ['VITE_SUPABASE_ANON_KEY', anon], ['SUPABASE_SERVICE_ROLE_KEY', service]]) {
  const re = new RegExp(`^\\s*${k}\\s*=.*$`, 'm');
  text = re.test(text) ? text.replace(re, `${k}=${v}`) : `${text.trimEnd()}\n${k}=${v}\n`;
}
writeFileSync(SETTINGS_FILE, text);
if (existsSync(envPath)) writeFileSync(envPath, `VITE_SUPABASE_URL=${url}\nVITE_SUPABASE_ANON_KEY=${anon}\nSUPABASE_SERVICE_ROLE_KEY=${service}\n`);
line();
console.log('✓ Настройки сохранены в файл НАСТРОЙКИ.txt\n');

console.log('Проверяю подключение к Supabase…');
let schemaOk = false;
let hasTasks = false;
try {
  const r = await fetch(`${url}/rest/v1/tasks?select=id&limit=1`, { headers: { apikey: service, Authorization: `Bearer ${service}` } });
  const body = await r.text();
  if (r.ok) { schemaOk = true; hasTasks = body.trim() !== '[]'; console.log('✓ Подключение работает, таблицы на месте.'); }
  else if (r.status === 401 || r.status === 403) console.log('✗ Supabase не принял ключ. Проверьте, что скопировали service_role полностью.');
  else if (/relation|does not exist|schema cache/i.test(body)) console.log('✗ Таблиц нет. Выполните файл supabase/schema.sql в Supabase → SQL Editor и запустите настройку ещё раз.');
  else console.log(`✗ Ответ Supabase: ${r.status} ${body.slice(0, 200)}`);
} catch (e) {
  console.log(`✗ Не удалось связаться с ${url}. Проверьте адрес и интернет. (${e.message})`);
}

if (schemaOk) {
  const q = hasTasks ? 'Задания уже загружены. Обновить их из data/tasks.json? (y/N) ' : 'Загрузить задания в базу сейчас? (Y/n) ';
  const a = (await rl.question(q)).trim().toLowerCase();
  const yes = hasTasks ? a === 'y' || a === 'д' : a === '' || a === 'y' || a === 'д';
  if (yes) {
    line();
    spawnSync(process.execPath, ['scripts/push-tasks.mjs'], { cwd: root, stdio: 'inherit' });
  }
}

rl.close();
line();
console.log('Не забудьте: Supabase → Authentication → Sign In / Providers → Email → выключить «Confirm email».');
console.log('Запустить сайт: npm run dev  (или двойной щелчок по файлу «2. Запуск сайта»)\n');
