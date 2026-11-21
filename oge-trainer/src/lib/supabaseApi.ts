import { createClient, SupabaseClient } from '@supabase/supabase-js';
import type { Api, Attempt, Catalog, CheckResult, OverviewRow, Profile, Solution, SignUpInput, Task } from './types';
import { loginToEmail } from './answers';

const TASK_COLUMNS = 'id, section_id, passage_id, sort, number, kind, prompt, word, options, topic';

async function fetchAll<T>(make: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>): Promise<T[]> {
  const out: T[] = [];
  const size = 1000;
  for (let from = 0; ; from += size) {
    let res = await make(from, from + size - 1);
    // при обрыве связи пробуем ещё два раза
    for (let attempt = 1; attempt <= 2 && res.error && /fetch|network|load failed/i.test(res.error.message); attempt++) {
      await new Promise((r) => setTimeout(r, 1500 * attempt));
      res = await make(from, from + size - 1);
    }
    const { data, error } = res;
    if (error) throw new Error(error.message);
    out.push(...(data || []));
    if (!data || data.length < size) break;
  }
  return out;
}

function humanError(message: string): string {
  if (/Invalid login credentials/i.test(message)) return 'Неверный логин или пароль.';
  if (/already registered|already been registered/i.test(message)) return 'Такой пользователь уже зарегистрирован.';
  if (/Password should be at least/i.test(message)) return 'Пароль слишком короткий (минимум 6 символов).';
  if (/Email not confirmed/i.test(message)) return 'Email не подтверждён. Откройте письмо от Supabase или попросите преподавателя отключить подтверждение email.';
  if (/rate limit/i.test(message)) return 'Слишком много попыток. Подождите минуту и попробуйте снова.';
  return message;
}

export function createSupabaseApi(url: string, key: string, opts: { proxied?: boolean } = {}): Api {
  const proxied = !!opts.proxied;
  const sb: SupabaseClient = createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true } });

  async function uid(): Promise<string | null> {
    const { data } = await sb.auth.getSession();
    return data.session?.user.id ?? null;
  }

  return {
    mode: 'supabase',
    realtime: !proxied,
    async getProfile() {
      const id = await uid();
      if (!id) return null;
      const { data, error } = await sb.from('profiles').select('*').eq('id', id).maybeSingle();
      if (error) throw new Error(error.message);
      return (data as Profile) ?? null;
    },
    onAuthChange(cb) {
      const { data } = sb.auth.onAuthStateChange((event) => {
        if (event === 'SIGNED_IN' || event === 'SIGNED_OUT' || event === 'USER_UPDATED') cb();
      });
      return () => data.subscription.unsubscribe();
    },
    async signIn(login, password) {
      const { error } = await sb.auth.signInWithPassword({ email: loginToEmail(login), password });
      if (error) throw new Error(humanError(error.message));
    },
    async signUp({ login, password, displayName, teacherCode }: SignUpInput) {
      const isEmail = login.includes('@');
      const { data, error } = await sb.auth.signUp({
        email: loginToEmail(login),
        password,
        options: { data: { display_name: displayName.trim(), login: isEmail ? null : login.trim().toLowerCase(), teacher_code: teacherCode?.trim() || '' } },
      });
      if (error) throw new Error(humanError(error.message));
      return { needsConfirmation: !data.session };
    },
    async signOut() {
      await sb.auth.signOut();
    },
    async becomeTeacher(code) {
      const { data, error } = await sb.rpc('become_teacher', { p_code: code });
      if (error) throw new Error(error.message);
      return Boolean(data);
    },
    async loadCatalog(): Promise<Catalog> {
      const [sections, passages, tasks] = await Promise.all([
        fetchAll((a, b) => sb.from('sections').select('*').order('sort').range(a, b)),
        fetchAll((a, b) => sb.from('passages').select('*').order('section_id').order('sort').range(a, b)),
        fetchAll<Task>((a, b) => sb.from('tasks').select(TASK_COLUMNS).order('passage_id').order('sort').range(a, b) as never),
      ]);
      return { sections, passages, tasks } as Catalog;
    },
    async myAttempts() {
      const id = await uid();
      if (!id) return [];
      return fetchAll<Attempt>((a, b) => sb.from('attempts').select('*').eq('user_id', id).order('created_at').order('id').range(a, b) as never);
    },
    async checkAnswer(taskId, answer): Promise<CheckResult> {
      const { data, error } = await sb.rpc('check_answer', { p_task_id: taskId, p_answer: answer });
      if (error) throw new Error(error.message);
      return data as CheckResult;
    },
    async getSolutions(taskIds): Promise<Solution[]> {
      const out: Solution[] = [];
      for (let i = 0; i < taskIds.length; i += 150) {
        const { data, error } = await sb.rpc('get_solutions', { p_task_ids: taskIds.slice(i, i + 150) });
        if (error) throw new Error(error.message);
        out.push(...((data || []) as Solution[]));
      }
      return out;
    },
    async touch(sectionId, passageId) {
      await sb.rpc('touch_activity', { p_section_id: sectionId, p_passage_id: passageId });
    },
    async teacherOverview(): Promise<OverviewRow[]> {
      const { data, error } = await sb.rpc('teacher_overview');
      if (error) throw new Error(error.message);
      return ((data || []) as OverviewRow[]).map((r) => ({
        ...r,
        attempts_total: Number(r.attempts_total), tasks_attempted: Number(r.tasks_attempted),
        tasks_correct: Number(r.tasks_correct), tasks_wrong: Number(r.tasks_wrong), first_try_correct: Number(r.first_try_correct),
      }));
    },
    async studentProfile(userId) {
      const { data, error } = await sb.from('profiles').select('*').eq('id', userId).maybeSingle();
      if (error) throw new Error(error.message);
      return (data as Profile) ?? null;
    },
    async studentAttempts(userId) {
      return fetchAll<Attempt>((a, b) => sb.from('attempts').select('*').eq('user_id', userId).order('created_at').order('id').range(a, b) as never);
    },
    subscribeAttempts(cb) {
      if (proxied) {
        // Через прокси Netlify веб-сокеты не работают — спрашиваем новые попытки каждые 15 секунд.
        let since = new Date().toISOString();
        let stopped = false;
        const tick = async () => {
          const { data } = await sb.from('attempts').select('*').gt('created_at', since).order('created_at').limit(500);
          if (stopped || !data) return;
          for (const a of data as Attempt[]) { cb(a); if (a.created_at > since) since = a.created_at; }
        };
        const t = window.setInterval(() => { void tick().catch(() => undefined); }, 15000);
        return () => { stopped = true; window.clearInterval(t); };
      }
      const channel = sb
        .channel('attempts-feed-' + Math.random().toString(36).slice(2))
        .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'attempts' }, (payload) => cb(payload.new as Attempt))
        .subscribe();
      return () => { void sb.removeChannel(channel); };
    },
  };
}
