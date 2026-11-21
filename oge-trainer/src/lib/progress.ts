import type { Attempt, Catalog, Section, Task } from './types';

export type Status = 'new' | 'correct' | 'wrong';
export interface TaskState { status: Status; attempts: Attempt[]; firstOk: boolean | null }
export interface Counts { total: number; correct: number; wrong: number; left: number; firstOk: number; attempted: number }

export function buildStates(attempts: Attempt[]): Map<string, TaskState> {
  const m = new Map<string, TaskState>();
  const sorted = [...attempts].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id);
  for (const a of sorted) {
    const s = m.get(a.task_id) || { status: 'new' as Status, attempts: [], firstOk: null };
    s.attempts.push(a);
    if (s.firstOk === null) s.firstOk = a.is_correct;
    s.status = s.attempts.some((x) => x.is_correct) ? 'correct' : 'wrong';
    m.set(a.task_id, s);
  }
  return m;
}

export function countFor(tasks: Task[], states: Map<string, TaskState>): Counts {
  const checked = tasks.filter((t) => t.kind !== 'open');
  const c: Counts = { total: checked.length, correct: 0, wrong: 0, left: 0, firstOk: 0, attempted: 0 };
  for (const t of checked) {
    const s = states.get(t.id);
    if (!s) { c.left++; continue; }
    c.attempted++;
    if (s.status === 'correct') c.correct++; else c.wrong++;
    if (s.firstOk) c.firstOk++;
  }
  return c;
}

export function pct(a: number, b: number): number { return b ? Math.round((a / b) * 100) : 0; }

export interface Index {
  sections: Section[];
  tasksById: Map<string, Task>;
  tasksBySection: Map<string, Task[]>;
  tasksByPassage: Map<string, Task[]>;
  passagesBySection: Map<string, Catalog['passages']>;
  passageById: Map<string, Catalog['passages'][number]>;
  sectionById: Map<string, Section>;
}

export function buildIndex(c: Catalog): Index {
  const group = <T,>(arr: T[], key: (x: T) => string | null) => {
    const m = new Map<string, T[]>();
    for (const x of arr) { const k = key(x); if (k == null) continue; m.set(k, [...(m.get(k) || []), x]); }
    return m;
  };
  const tasks = [...c.tasks].sort((a, b) => a.sort - b.sort);
  const passages = [...c.passages].sort((a, b) => a.sort - b.sort);
  return {
    sections: [...c.sections].sort((a, b) => a.sort - b.sort),
    tasksById: new Map(tasks.map((t) => [t.id, t])),
    tasksBySection: group(tasks, (t) => t.section_id),
    tasksByPassage: group(tasks, (t) => t.passage_id),
    passagesBySection: group(passages, (p) => p.section_id),
    passageById: new Map(passages.map((p) => [p.id, p])),
    sectionById: new Map(c.sections.map((s) => [s.id, s])),
  };
}

export function formatAnswer(task: Task | undefined, answer: string): string {
  if (!task) return answer;
  if (task.kind === 'matching' && task.options && 'letters' in task.options) {
    const letters = task.options.letters;
    return letters.map((l, i) => `${l}–${answer[i] && answer[i] !== '0' ? answer[i] : '?'}`).join(', ');
  }
  if (task.kind === 'choice' && Array.isArray(task.options)) {
    const o = task.options.find((x) => x.value === answer);
    return o ? `${o.value} (${o.label})` : answer;
  }
  return answer;
}

const rtf = new Intl.RelativeTimeFormat('ru', { numeric: 'auto' });
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '—';
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return 'только что';
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
  if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), 'day');
  return new Date(iso).toLocaleDateString('ru-RU');
}
export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
