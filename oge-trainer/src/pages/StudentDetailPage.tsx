import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import type { Attempt, Profile } from '../lib/types';
import { buildStates, countFor, pct, timeAgo } from '../lib/progress';
import { Legend, ProgressBar } from '../components/ProgressBar';
import { AttemptLog, SectionBreakdown } from '../components/StatsBlocks';

export default function StudentDetailPage() {
  const { userId } = useParams();
  const { api, index } = useApp();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [onlyErrors, setOnlyErrors] = useState(false);
  const [sectionId, setSectionId] = useState('');
  const [updated, setUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    if (!userId) return;
    const [p, a] = await Promise.all([api.studentProfile(userId), api.studentAttempts(userId)]);
    setProfile(p); setAttempts(a); setUpdated(new Date()); setLoading(false);
  }, [api, userId]);

  useEffect(() => {
    void load();
    const off = api.subscribeAttempts((a) => {
      if (a.user_id !== userId) return;
      setAttempts((prev) => (prev.some((x) => x.id === a.id) ? prev : [...prev, a]));
      setUpdated(new Date());
      void api.studentProfile(userId!).then(setProfile).catch(() => undefined);
    });
    return off;
  }, [api, userId, load]);

  const states = useMemo(() => buildStates(attempts), [attempts]);
  const weak = useMemo(() => {
    if (!index) return [];
    const m = new Map<string, { wrong: number; tasks: Set<string> }>();
    for (const a of attempts) {
      if (a.is_correct) continue;
      const topic = index.tasksById.get(a.task_id)?.topic || 'Другое';
      const e = m.get(topic) || { wrong: 0, tasks: new Set<string>() };
      e.wrong++; e.tasks.add(a.task_id); m.set(topic, e);
    }
    return [...m.entries()].sort((a, b) => b[1].wrong - a[1].wrong).slice(0, 8);
  }, [attempts, index]);

  if (!index) return null;
  if (loading) return <div className="page"><div className="spinner" /></div>;
  if (!profile) return <div className="page"><p>Ученик не найден.</p><Link to="/teacher">← К списку</Link></div>;
  const total = countFor([...index.tasksById.values()], states);
  const sec = profile.current_section_id ? index.sectionById.get(profile.current_section_id) : undefined;
  const pas = profile.current_passage_id ? index.passageById.get(profile.current_passage_id) : undefined;

  return (
    <div className="page">
      <div className="crumbs"><Link to="/teacher">Кабинет преподавателя</Link> / {profile.display_name}</div>
      <div className="hello">
        <div>
          <h1>{profile.display_name}</h1>
          <p className="muted">{profile.login ? `Логин: ${profile.login} · ` : ''}последняя активность: {timeAgo(profile.last_active_at)}{sec ? ` · сейчас: ${sec.title}, ${pas?.title ?? ''}` : ''}</p>
        </div>
        <div className="live-box"><span className="live-dot" /> В реальном времени{updated && <span className="muted small"> · {updated.toLocaleTimeString('ru-RU')}</span>}
          <button className="btn ghost small" onClick={() => void load()}>Обновить</button></div>
      </div>
      <div className="card summary">
        <div className="summary-nums">
          <div><b>{pct(total.correct, total.total)}%</b><span>общий прогресс</span></div>
          <div><b>{total.correct}</b><span>верно</span></div>
          <div><b className="bad-t">{total.wrong}</b><span>не решено (ошибки)</span></div>
          <div><b>{pct(total.firstOk, total.attempted)}%</b><span>верно с 1-й попытки</span></div>
          <div><b>{attempts.length}</b><span>попыток</span></div>
        </div>
        <ProgressBar c={total} /><Legend c={total} />
      </div>
      <div className="two-col">
        <div>
          <h2>Прогресс по разделам</h2>
          <div className="card"><SectionBreakdown index={index} states={states} /></div>
        </div>
        <div>
          <h2>Слабые места</h2>
          <div className="card">
            {!weak.length ? <p className="muted">Ошибок пока нет.</p> : (
              <ul className="weak">{weak.map(([topic, v]) => <li key={topic}><span>{topic}</span><b className="bad-t">{v.wrong} ош. в {v.tasks.size} зад.</b></li>)}</ul>
            )}
          </div>
        </div>
      </div>
      <h2>Лог решений</h2>
      <div className="toolbar">
        <label className="check"><input type="checkbox" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} /> Только ошибки</label>
        <select value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
          <option value="">Все разделы</option>
          {index.sections.map((s) => <option key={s.id} value={s.id}>{s.title} · {s.subtitle}</option>)}
        </select>
      </div>
      <div className="card"><AttemptLog index={index} attempts={attempts} onlyErrors={onlyErrors} sectionId={sectionId} /></div>
    </div>
  );
}
