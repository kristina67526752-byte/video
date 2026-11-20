// Демо-режим: всё хранится в localStorage этого браузера. Нужен только чтобы посмотреть сайт без Supabase.
import raw from '../../data/tasks.json';
import type { Api, Attempt, Catalog, CheckResult, OverviewRow, Profile, Solution, SignUpInput } from './types';
import { loginToEmail, normalizeAnswer } from './answers';

interface RawTask { id: string; section_id: string; passage_id: string | null; sort: number; number: string | null; kind: string;
  prompt: string; word: string | null; options: unknown; topic: string | null; answers: string[]; explanation: string }
interface DemoUser extends Profile { email: string; password: string }

const data = raw as unknown as { sections: Catalog['sections']; passages: Catalog['passages']; tasks: RawTask[] };
const TEACHER_CODE = 'demo-teacher';
const K = { users: 'demo.users', session: 'demo.session', attempts: 'demo.attempts' };
const bus = new EventTarget();

function read<T>(k: string, def: T): T {
  try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : def; } catch { return def; }
}
function write(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ignore */ } }
const strip = (u: DemoUser): Profile => { const { email: _e, password: _p, ...rest } = u; return rest; };

export function createDemoApi(): Api {
  const tasks = new Map(data.tasks.map((t) => [t.id, t]));
  const users = () => read<DemoUser[]>(K.users, []);
  const me = () => users().find((u) => u.id === read<string | null>(K.session, null)) ?? null;
  const attempts = () => read<Attempt[]>(K.attempts, []);
  const updateUser = (id: string, patch: Partial<DemoUser>) => write(K.users, users().map((u) => (u.id === id ? { ...u, ...patch } : u)));

  return {
    mode: 'demo',
    async getProfile() { const u = me(); return u ? strip(u) : null; },
    onAuthChange(cb) { bus.addEventListener('auth', cb); return () => bus.removeEventListener('auth', cb); },
    async signIn(login, password) {
      const u = users().find((x) => x.email === loginToEmail(login) && x.password === password);
      if (!u) throw new Error('Неверный логин или пароль.');
      write(K.session, u.id); bus.dispatchEvent(new Event('auth'));
    },
    async signUp({ login, password, displayName, teacherCode }: SignUpInput) {
      const email = loginToEmail(login);
      if (users().some((u) => u.email === email)) throw new Error('Такой пользователь уже зарегистрирован.');
      if (password.length < 6) throw new Error('Пароль слишком короткий (минимум 6 символов).');
      const u: DemoUser = { id: crypto.randomUUID(), email, password, display_name: displayName.trim() || login,
        login: login.includes('@') ? null : login.trim().toLowerCase(), role: teacherCode === TEACHER_CODE ? 'teacher' : 'student',
        created_at: new Date().toISOString(), last_active_at: null };
      write(K.users, [...users(), u]); write(K.session, u.id); bus.dispatchEvent(new Event('auth'));
      return { needsConfirmation: false };
    },
    async signOut() { write(K.session, null); bus.dispatchEvent(new Event('auth')); },
    async becomeTeacher(code) {
      const u = me(); if (!u || code !== TEACHER_CODE) return false;
      updateUser(u.id, { role: 'teacher' }); bus.dispatchEvent(new Event('auth')); return true;
    },
    async loadCatalog() {
      return { sections: data.sections, passages: data.passages,
        tasks: data.tasks.map(({ answers: _a, explanation: _e, ...t }) => t) } as Catalog;
    },
    async myAttempts() { const u = me(); return u ? attempts().filter((a) => a.user_id === u.id) : []; },
    async checkAnswer(taskId, answer): Promise<CheckResult> {
      const u = me(); const t = tasks.get(taskId);
      if (!u) throw new Error('Нужно войти в аккаунт'); if (!t) throw new Error('Задание не найдено');
      const norm = normalizeAnswer(answer);
      let ok = false; let score = 0; let max = 1; const items: boolean[] = [];
      if (t.kind === 'matching') {
        const right = normalizeAnswer(t.answers[0]); max = right.length;
        for (let i = 0; i < max; i++) { const hit = norm[i] === right[i]; items.push(hit); if (hit) score++; }
        ok = score === max && norm.length === max;
      } else { ok = t.answers.some((a) => normalizeAnswer(a) === norm); score = ok ? 1 : 0; }
      const all = attempts();
      const att: Attempt = { id: all.length + 1, user_id: u.id, task_id: t.id, section_id: t.section_id, answer: answer.trim().slice(0, 200),
        is_correct: ok, score, max_score: max, created_at: new Date().toISOString() };
      write(K.attempts, [...all, att]);
      updateUser(u.id, { last_active_at: att.created_at, current_section_id: t.section_id, current_passage_id: t.passage_id, current_task_id: t.id });
      bus.dispatchEvent(new CustomEvent('attempt', { detail: att }));
      return { correct: ok, score, max_score: max, answers: t.answers, explanation: t.explanation, items };
    },
    async getSolutions(ids): Promise<Solution[]> {
      const u = me(); if (!u) return [];
      const mine = new Set(attempts().filter((a) => a.user_id === u.id).map((a) => a.task_id));
      return ids.filter((id) => u.role === 'teacher' || mine.has(id)).map((id) => tasks.get(id)).filter(Boolean)
        .map((t) => ({ task_id: t!.id, answers: t!.answers, explanation: t!.explanation }));
    },
    async touch(sectionId, passageId) {
      const u = me(); if (u) updateUser(u.id, { last_active_at: new Date().toISOString(), current_section_id: sectionId, current_passage_id: passageId });
    },
    async teacherOverview(): Promise<OverviewRow[]> {
      const u = me(); if (!u || u.role !== 'teacher') throw new Error('Доступ только для преподавателя');
      const all = attempts();
      return users().map((p) => {
        const mine = all.filter((a) => a.user_id === p.id);
        const per = new Map<string, Attempt[]>();
        mine.forEach((a) => per.set(a.task_id, [...(per.get(a.task_id) || []), a]));
        const lists = [...per.values()];
        return { user_id: p.id, display_name: p.display_name, login: p.login, role: p.role, created_at: p.created_at || '',
          last_active_at: p.last_active_at ?? null, current_section_id: p.current_section_id ?? null, current_passage_id: p.current_passage_id ?? null,
          current_task_id: p.current_task_id ?? null, attempts_total: mine.length, tasks_attempted: per.size,
          tasks_correct: lists.filter((l) => l.some((a) => a.is_correct)).length,
          tasks_wrong: lists.filter((l) => !l.some((a) => a.is_correct)).length,
          first_try_correct: lists.filter((l) => l[0].is_correct).length };
      }).sort((a, b) => (b.last_active_at || '').localeCompare(a.last_active_at || ''));
    },
    async studentProfile(id) { const u = users().find((x) => x.id === id); return u ? strip(u) : null; },
    async studentAttempts(id) { return attempts().filter((a) => a.user_id === id); },
    subscribeAttempts(cb) {
      const local = (e: Event) => cb((e as CustomEvent<Attempt>).detail);
      const storage = (e: StorageEvent) => {
        if (e.key !== K.attempts || !e.newValue) return;
        const list = JSON.parse(e.newValue) as Attempt[]; const last = list[list.length - 1]; if (last) cb(last);
      };
      bus.addEventListener('attempt', local); window.addEventListener('storage', storage);
      return () => { bus.removeEventListener('attempt', local); window.removeEventListener('storage', storage); };
    },
  };
}
