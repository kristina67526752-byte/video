import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import type { OverviewRow } from '../lib/types';
import { pct, timeAgo } from '../lib/progress';
import { ProgressBar } from '../components/ProgressBar';

type SortKey = 'activity' | 'name' | 'progress' | 'first';

export default function TeacherPage() {
  const { api, index } = useApp();
  const nav = useNavigate();
  const [rows, setRows] = useState<OverviewRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [q, setQ] = useState('');
  const [showTeachers, setShowTeachers] = useState(false);
  const [sort, setSort] = useState<SortKey>('activity');
  const [live, setLive] = useState(0);
  const timer = useRef<number | undefined>(undefined);
  const totalTasks = index?.tasksById.size || 1;

  const load = useCallback(async () => {
    try { setRows(await api.teacherOverview()); setUpdated(new Date()); setError(null); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, [api]);

  useEffect(() => {
    void load();
    const off = api.subscribeAttempts(() => {
      setLive((n) => n + 1);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => { void load(); }, 1200);
    });
    const poll = window.setInterval(() => { void load(); }, 60000);
    return () => { off(); window.clearInterval(poll); window.clearTimeout(timer.current); };
  }, [api, load]);

  const list = rows
    .filter((r) => showTeachers || r.role === 'student')
    .filter((r) => !q || (r.display_name + ' ' + (r.login || '')).toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => {
      if (sort === 'name') return a.display_name.localeCompare(b.display_name, 'ru');
      if (sort === 'progress') return b.tasks_correct - a.tasks_correct;
      if (sort === 'first') return pct(b.first_try_correct, b.tasks_attempted) - pct(a.first_try_correct, a.tasks_attempted);
      return (b.last_active_at || '').localeCompare(a.last_active_at || '');
    });
  const students = rows.filter((r) => r.role === 'student');
  const today = students.filter((r) => r.last_active_at && Date.now() - new Date(r.last_active_at).getTime() < 86400000).length;

  return (
    <div className="page">
      <div className="hello">
        <div>
          <h1>Кабинет преподавателя</h1>
          <p className="muted">Учеников: {students.length} · активны за сутки: {today}</p>
        </div>
        <div className="live-box">
          <span className="live-dot" key={live} /> Обновляется автоматически
          {updated && <span className="muted small"> · {updated.toLocaleTimeString('ru-RU')}</span>}
          <button className="btn ghost small" onClick={() => { setLoading(true); void load(); }}>Обновить</button>
        </div>
      </div>
      <div className="toolbar">
        <input className="search" placeholder="Поиск по имени или логину" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
          <option value="activity">Сначала недавно активные</option>
          <option value="name">По имени</option>
          <option value="progress">По прогрессу</option>
          <option value="first">По точности с 1-й попытки</option>
        </select>
        <label className="check"><input type="checkbox" checked={showTeachers} onChange={(e) => setShowTeachers(e.target.checked)} /> показывать преподавателей</label>
      </div>
      {error && <div className="alert bad">{error}</div>}
      {loading && !rows.length ? <div className="spinner" /> : (
        <div className="card table-wrap">
          <table className="table students">
            <thead><tr><th>Ученик</th><th>Последняя активность</th><th>Сейчас решает</th><th>Общий прогресс</th><th>С 1-й попытки</th><th>Ошибок</th><th>Попыток</th></tr></thead>
            <tbody>
              {list.map((r) => {
                const sec = r.current_section_id ? index?.sectionById.get(r.current_section_id) : undefined;
                const pas = r.current_passage_id ? index?.passageById.get(r.current_passage_id) : undefined;
                const task = r.current_task_id ? index?.tasksById.get(r.current_task_id) : undefined;
                const recent = r.last_active_at && Date.now() - new Date(r.last_active_at).getTime() < 5 * 60000;
                return (
                  <tr key={r.user_id} className="clickable" onClick={() => nav(`/teacher/${r.user_id}`)}>
                    <td><b>{r.display_name}</b>{r.role === 'teacher' && <span className="badge">преп.</span>}<div className="muted small">{r.login || ''}</div></td>
                    <td className="nowrap" title={r.last_active_at ? new Date(r.last_active_at).toLocaleString('ru-RU') : ''}>
                      {recent && <span className="online" title="Активен в последние 5 минут" />}{timeAgo(r.last_active_at)}
                    </td>
                    <td>{sec ? <><div>{sec.title} · {sec.subtitle}</div><div className="muted small">{pas?.title}{task ? ` · № ${task.number}` : ''}</div></> : <span className="muted">—</span>}</td>
                    <td className="progress-cell"><ProgressBar c={{ total: totalTasks, correct: r.tasks_correct, wrong: r.tasks_wrong }} thin /><span className="small">{pct(r.tasks_correct, totalTasks)}% · {r.tasks_correct} из {totalTasks}</span></td>
                    <td><b>{r.tasks_attempted ? pct(r.first_try_correct, r.tasks_attempted) + '%' : '—'}</b><div className="muted small">{r.first_try_correct} из {r.tasks_attempted}</div></td>
                    <td className={r.tasks_wrong ? 'bad-t' : ''}>{r.tasks_wrong}</td>
                    <td>{r.attempts_total}</td>
                  </tr>
                );
              })}
              {!list.length && <tr><td colSpan={7} className="muted center">Пока нет учеников. Попросите их зарегистрироваться на сайте.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
