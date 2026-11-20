-- =====================================================================
--  ОГЭ English Trainer — схема базы данных Supabase
--  Выполните этот файл целиком в Supabase → SQL Editor → New query → Run.
--  Скрипт можно запускать повторно: он не удаляет данные.
-- =====================================================================

-- ---------- Настройки (код преподавателя) ----------
create table if not exists public.app_settings (
  key   text primary key,
  value text not null
);
alter table public.app_settings enable row level security;   -- политик нет: клиенты не видят таблицу
revoke all on public.app_settings from anon, authenticated;
insert into public.app_settings (key, value)
values ('teacher_code', 'ЗАМЕНИТЕ-ЭТОТ-КОД')
on conflict (key) do nothing;

-- ---------- Профили пользователей ----------
create table if not exists public.profiles (
  id                 uuid primary key references auth.users (id) on delete cascade,
  display_name       text not null default '',
  login              text,
  role               text not null default 'student' check (role in ('student', 'teacher')),
  created_at         timestamptz not null default now(),
  last_active_at     timestamptz,
  current_section_id text,
  current_passage_id text,
  current_task_id    text
);

-- ---------- Задания: разделы → тексты → задания ----------
create table if not exists public.sections (
  id          text primary key,
  title       text not null,
  subtitle    text,
  kind        text not null check (kind in ('matching', 'tfn', 'gap')),
  instruction text,
  sort        int not null default 0
);

create table if not exists public.passages (
  id         text primary key,
  section_id text not null references public.sections (id) on delete cascade,
  title      text,
  body       text not null default '',
  sort       int not null default 0
);

create table if not exists public.tasks (
  id          text primary key,
  section_id  text not null references public.sections (id) on delete cascade,
  passage_id  text references public.passages (id) on delete cascade,
  sort        int not null default 0,
  number      text,
  kind        text not null check (kind in ('text', 'choice', 'matching')),
  prompt      text not null,
  word        text,
  options     jsonb,
  topic       text,
  answers     jsonb not null default '[]'::jsonb,   -- секрет: недоступен клиентам напрямую
  explanation text not null default ''              -- секрет: выдаётся только после попытки
);
create index if not exists tasks_passage_idx on public.tasks (passage_id, sort);

-- ---------- Попытки ----------
create table if not exists public.attempts (
  id         bigint generated always as identity primary key,
  user_id    uuid not null references public.profiles (id) on delete cascade,
  task_id    text not null references public.tasks (id) on delete cascade,
  section_id text,
  answer     text not null,
  is_correct boolean not null,
  score      int not null default 0,
  max_score  int not null default 1,
  created_at timestamptz not null default now()
);
create index if not exists attempts_user_idx on public.attempts (user_id, created_at desc);
create index if not exists attempts_task_idx on public.attempts (task_id);

-- =====================================================================
--  Вспомогательные функции
-- =====================================================================
create or replace function public.is_teacher()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'teacher');
$$;

-- Нормализация ответа как на ОГЭ: регистр и пробелы не важны, орфография — важна.
create or replace function public.normalize_answer(p text)
returns text language sql immutable as $$
  select regexp_replace(
           translate(lower(coalesce(p, '')), '’‘`´', ''''''''''),
           '\s+', '', 'g');
$$;

-- Профиль создаётся автоматически при регистрации.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  v_code   text;
  v_wanted text := coalesce(new.raw_user_meta_data ->> 'teacher_code', '');
begin
  select value into v_code from public.app_settings where key = 'teacher_code';
  insert into public.profiles (id, display_name, login, role)
  values (
    new.id,
    coalesce(nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''), split_part(new.email, '@', 1)),
    nullif(new.raw_user_meta_data ->> 'login', ''),
    case when v_wanted <> '' and v_wanted = v_code then 'teacher' else 'student' end
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Стать преподавателем уже после регистрации (по коду).
create or replace function public.become_teacher(p_code text)
returns boolean language plpgsql security definer set search_path = public as $$
declare v_code text;
begin
  if auth.uid() is null then raise exception 'Нужно войти в аккаунт'; end if;
  select value into v_code from public.app_settings where key = 'teacher_code';
  if p_code is null or p_code <> v_code then return false; end if;
  update public.profiles set role = 'teacher' where id = auth.uid();
  return true;
end;
$$;

-- Проверка ответа: сверка на сервере + запись попытки + выдача разбора.
create or replace function public.check_answer(p_task_id text, p_answer text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  t        public.tasks;
  v_norm   text;
  v_ok     boolean := false;
  v_score  int := 0;
  v_max    int := 1;
  v_right  text;
  v_items  jsonb := '[]'::jsonb;
  a        text;
  i        int;
begin
  if auth.uid() is null then raise exception 'Нужно войти в аккаунт'; end if;
  if p_answer is null or length(trim(p_answer)) = 0 then raise exception 'Пустой ответ'; end if;
  if length(p_answer) > 200 then raise exception 'Слишком длинный ответ'; end if;

  select * into t from public.tasks where id = p_task_id;
  if not found then raise exception 'Задание не найдено'; end if;

  v_norm := public.normalize_answer(p_answer);

  if t.kind = 'matching' then
    v_right := public.normalize_answer(t.answers ->> 0);
    v_max := length(v_right);
    for i in 1 .. v_max loop
      v_items := v_items || to_jsonb(substr(v_norm, i, 1) = substr(v_right, i, 1));
      if substr(v_norm, i, 1) = substr(v_right, i, 1) then v_score := v_score + 1; end if;
    end loop;
    v_ok := v_score = v_max and length(v_norm) = v_max;
  else
    for a in select jsonb_array_elements_text(t.answers) loop
      if public.normalize_answer(a) = v_norm then v_ok := true; end if;
    end loop;
    v_score := case when v_ok then 1 else 0 end;
  end if;

  insert into public.attempts (user_id, task_id, section_id, answer, is_correct, score, max_score)
  values (auth.uid(), t.id, t.section_id, left(trim(p_answer), 200), v_ok, v_score, v_max);

  update public.profiles
     set last_active_at = now(), current_section_id = t.section_id,
         current_passage_id = t.passage_id, current_task_id = t.id
   where id = auth.uid();

  return jsonb_build_object('correct', v_ok, 'score', v_score, 'max_score', v_max,
                            'answers', t.answers, 'explanation', t.explanation, 'items', v_items);
end;
$$;

-- Разборы для заданий, которые пользователь уже решал (или для преподавателя — любые).
create or replace function public.get_solutions(p_task_ids text[], p_user uuid default null)
returns table (task_id text, answers jsonb, explanation text)
language sql stable security definer set search_path = public as $$
  select t.id, t.answers, t.explanation
    from public.tasks t
   where t.id = any (p_task_ids)
     and (
       public.is_teacher()
       or exists (select 1 from public.attempts a where a.task_id = t.id and a.user_id = auth.uid())
     );
$$;

-- Отметка «ученик сейчас открыл этот текст».
create or replace function public.touch_activity(p_section_id text, p_passage_id text)
returns void language sql security definer set search_path = public as $$
  update public.profiles
     set last_active_at = now(), current_section_id = p_section_id, current_passage_id = p_passage_id
   where id = auth.uid();
$$;

-- Сводная таблица учеников для преподавателя.
create or replace function public.teacher_overview()
returns table (
  user_id uuid, display_name text, login text, role text, created_at timestamptz,
  last_active_at timestamptz, current_section_id text, current_passage_id text, current_task_id text,
  attempts_total bigint, tasks_attempted bigint, tasks_correct bigint, tasks_wrong bigint,
  first_try_correct bigint
)
language plpgsql stable security definer set search_path = public as $$
begin
  if not public.is_teacher() then raise exception 'Доступ только для преподавателя'; end if;
  return query
  with per_task as (
    select a.user_id, a.task_id,
           bool_or(a.is_correct) as any_ok,
           (array_agg(a.is_correct order by a.created_at, a.id))[1] as first_ok,
           count(*) as n
      from public.attempts a
     group by a.user_id, a.task_id
  )
  select p.id, p.display_name, p.login, p.role, p.created_at, p.last_active_at,
         p.current_section_id, p.current_passage_id, p.current_task_id,
         coalesce(sum(pt.n), 0)::bigint,
         count(pt.task_id)::bigint,
         count(pt.task_id) filter (where pt.any_ok)::bigint,
         count(pt.task_id) filter (where not pt.any_ok)::bigint,
         count(pt.task_id) filter (where pt.first_ok)::bigint
    from public.profiles p
    left join per_task pt on pt.user_id = p.id
   group by p.id
   order by p.last_active_at desc nulls last;
end;
$$;

-- =====================================================================
--  Права доступа (Row Level Security)
-- =====================================================================
alter table public.profiles enable row level security;
alter table public.sections enable row level security;
alter table public.passages enable row level security;
alter table public.tasks    enable row level security;
alter table public.attempts enable row level security;

drop policy if exists "profiles_select" on public.profiles;
create policy "profiles_select" on public.profiles for select to authenticated
  using (id = auth.uid() or public.is_teacher());
drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists "sections_read" on public.sections;
create policy "sections_read" on public.sections for select to authenticated using (true);
drop policy if exists "passages_read" on public.passages;
create policy "passages_read" on public.passages for select to authenticated using (true);
drop policy if exists "tasks_read" on public.tasks;
create policy "tasks_read" on public.tasks for select to authenticated using (true);

drop policy if exists "attempts_select" on public.attempts;
create policy "attempts_select" on public.attempts for select to authenticated
  using (user_id = auth.uid() or public.is_teacher());
-- Политик на insert/update/delete нет: попытка записывается только функцией check_answer.

-- Табличные права: гости не видят ничего; ответы и разборы закрыты на уровне столбцов.
revoke all on public.profiles, public.sections, public.passages, public.tasks, public.attempts from anon;
revoke all on public.profiles, public.sections, public.passages, public.tasks, public.attempts from authenticated;
grant select on public.profiles, public.sections, public.passages, public.attempts to authenticated;
grant update (display_name) on public.profiles to authenticated;
grant select (id, section_id, passage_id, sort, number, kind, prompt, word, options, topic) on public.tasks to authenticated;

revoke execute on function public.check_answer(text, text), public.get_solutions(text[], uuid),
  public.teacher_overview(), public.become_teacher(text), public.touch_activity(text, text) from anon, public;
grant execute on function public.check_answer(text, text), public.get_solutions(text[], uuid),
  public.teacher_overview(), public.become_teacher(text), public.touch_activity(text, text), public.is_teacher()
  to authenticated;

-- =====================================================================
--  Realtime: преподаватель видит новые попытки сразу
-- =====================================================================
do $$
begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'attempts') then
    alter publication supabase_realtime add table public.attempts;
  end if;
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'profiles') then
    alter publication supabase_realtime add table public.profiles;
  end if;
end $$;
