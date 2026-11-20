// Загрузка/обновление заданий из data/tasks.json в Supabase.
//   npm run check-tasks   — только проверить файл (ничего не отправляет)
//   npm run push-tasks    — проверить и загрузить (нужны VITE_SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY в .env.local)
// Повторный запуск безопасен: существующие записи обновляются по id, попытки учеников не трогаются.
import { readFileSync, existsSync } from 'node:fs';
import { createClient } from '@supabase/supabase-js';

const dryRun = process.argv.includes('--dry-run');
const file = new URL('../data/tasks.json', import.meta.url);

function loadEnv() {
  for (const name of ['.env.local', '.env']) {
    const path = new URL('../' + name, import.meta.url);
    if (!existsSync(path)) continue;
    for (const line of readFileSync(path, 'utf8').split('\n')) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^['"]|['"]$/g, '');
    }
  }
}

function validate(data) {
  const errors = [];
  const sectionIds = new Set(); const passageIds = new Set(); const taskIds = new Set();
  for (const s of data.sections || []) {
    if (!s.id || !s.title) errors.push(`Раздел без id/title: ${JSON.stringify(s).slice(0, 80)}`);
    if (!['matching', 'tfn', 'gap'].includes(s.kind)) errors.push(`Раздел ${s.id}: kind должен быть matching | tfn | gap`);
    if (sectionIds.has(s.id)) errors.push(`Повтор id раздела ${s.id}`); sectionIds.add(s.id);
  }
  for (const p of data.passages || []) {
    if (!p.id) errors.push('Текст без id');
    if (!sectionIds.has(p.section_id)) errors.push(`Текст ${p.id}: нет раздела ${p.section_id}`);
    if (passageIds.has(p.id)) errors.push(`Повтор id текста ${p.id}`); passageIds.add(p.id);
  }
  for (const t of data.tasks || []) {
    const where = `Задание ${t.id}`;
    if (!t.id) errors.push('Задание без id');
    if (taskIds.has(t.id)) errors.push(`Повтор id задания ${t.id}`); taskIds.add(t.id);
    if (!sectionIds.has(t.section_id)) errors.push(`${where}: нет раздела ${t.section_id}`);
    if (t.passage_id && !passageIds.has(t.passage_id)) errors.push(`${where}: нет текста ${t.passage_id}`);
    if (!['text', 'choice', 'matching'].includes(t.kind)) errors.push(`${where}: kind должен быть text | choice | matching`);
    if (!t.prompt) errors.push(`${where}: пустой prompt`);
    if (!Array.isArray(t.answers) || !t.answers.length || t.answers.some((a) => typeof a !== 'string' || !a.trim())) errors.push(`${where}: answers должен быть непустым списком строк`);
    if (t.kind === 'text' && !String(t.prompt).includes('_____')) errors.push(`${where}: в prompt нет пропуска «_____» (5 подчёркиваний)`);
    if (t.kind === 'choice' && (!Array.isArray(t.options) || !t.options.length)) errors.push(`${where}: для choice нужен список options [{value,label}]`);
    if (t.kind === 'choice' && Array.isArray(t.options) && !t.options.some((o) => o.value === t.answers[0])) errors.push(`${where}: ответ ${t.answers[0]} не совпадает ни с одним value в options`);
    if (t.kind === 'matching') {
      const o = t.options || {};
      if (!Array.isArray(o.letters) || !Array.isArray(o.questions)) errors.push(`${where}: для matching нужны options.letters и options.questions`);
      else if (t.answers[0].length !== o.letters.length || /[^1-9]/.test(t.answers[0])) errors.push(`${where}: ответ должен состоять из ${o.letters.length} цифр (по одной на каждый текст)`);
    }
  }
  return errors;
}

async function upsert(sb, table, rows) {
  for (let i = 0; i < rows.length; i += 200) {
    const { error } = await sb.from(table).upsert(rows.slice(i, i + 200), { onConflict: 'id' });
    if (error) throw new Error(`${table}: ${error.message}`);
    process.stdout.write(`\r  ${table}: ${Math.min(i + 200, rows.length)} / ${rows.length}`);
  }
  process.stdout.write('\n');
}

const data = JSON.parse(readFileSync(file, 'utf8'));
const errors = validate(data);
console.log(`Разделов: ${data.sections.length}, текстов: ${data.passages.length}, заданий: ${data.tasks.length}`);
if (errors.length) {
  console.error(`\nНайдено ошибок: ${errors.length}\n- ` + errors.slice(0, 50).join('\n- '));
  process.exit(1);
}
console.log('Файл заданий в порядке.');
if (dryRun) process.exit(0);

loadEnv();
const url = process.env.VITE_SUPABASE_URL; const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !key || key.startsWith('eyJhbGciOi...')) {
  console.error('\nУкажите VITE_SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY в файле .env.local (см. .env.example).');
  process.exit(1);
}
const sb = createClient(url, key, { auth: { persistSession: false } });
const pick = (o, keys) => Object.fromEntries(keys.map((k) => [k, o[k] ?? null]));
await upsert(sb, 'sections', data.sections.map((s) => pick(s, ['id', 'title', 'subtitle', 'kind', 'instruction', 'sort'])));
await upsert(sb, 'passages', data.passages.map((p) => ({ ...pick(p, ['id', 'section_id', 'title', 'sort']), body: p.body ?? '' })));
await upsert(sb, 'tasks', data.tasks.map((t) => ({ ...pick(t, ['id', 'section_id', 'passage_id', 'sort', 'number', 'kind', 'prompt', 'word', 'options', 'topic', 'answers']), explanation: t.explanation ?? '' })));
console.log('Готово! Задания загружены в Supabase.');
