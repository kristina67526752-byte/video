import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { countFor, pct } from '../lib/progress';
import type { Solution } from '../lib/types';
import { ProgressBar, Legend } from '../components/ProgressBar';
import { AttemptLog, SectionBreakdown, shortPrompt, taskLabel } from '../components/StatsBlocks';
import Explanation from '../components/Explanation';
import { formatAnswer } from '../lib/progress';

function TeacherCode() {
  const { api, refreshProfile } = useApp();
  const [code, setCode] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  async function go() {
    try { const ok = await api.becomeTeacher(code.trim()); setMsg(ok ? 'Готово! Теперь у вас есть кабинет преподавателя.' : 'Неверный код.'); if (ok) await refreshProfile(); }
    catch (e) { setMsg((e as Error).message); }
  }
  return (
    <details className="card teacher-code">
      <summary>Я преподаватель — у меня есть код доступа</summary>
      <div className="toolbar" style={{ marginTop: 10 }}>
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Код преподавателя" />
        <button className="btn ghost" disabled={!code.trim()} onClick={go}>Получить доступ</button>
        {msg && <span className="small">{msg}</span>}
      </div>
    </details>
  );
}

export default function StatsPage() {
  const { index, states, attempts, api, profile } = useApp();
  const [tab, setTab] = useState<'errors' | 'log'>('errors');
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [solutions, setSolutions] = useState<Record<string, Solution>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const errorTasks = useMemo(() => {
    if (!index) return [];
    return [...states.entries()].filter(([, s]) => s.attempts.some((a) => !a.is_correct))
      .map(([id, s]) => ({ t: index.tasksById.get(id)!, s })).filter((x) => x.t)
      .sort((a, b) => b.s.attempts[b.s.attempts.length - 1].created_at.localeCompare(a.s.attempts[a.s.attempts.length - 1].created_at));
  }, [index, states]);

  useEffect(() => {
    const need = errorTasks.map((x) => x.t.id).filter((id) => !solutions[id]);
    if (!need.length) return;
    api.getSolutions(need).then((list) => setSolutions((p) => { const n = { ...p }; list.forEach((s) => { n[s.task_id] = s; }); return n; })).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [errorTasks.length]);

  if (!index) return null;
  const total = countFor([...index.tasksById.values()], states);
  const shown = errorTasks.filter((x) => !onlyOpen || x.s.status === 'wrong');

  return (
    <div className="page">
      <h1>Мой прогресс</h1>
      <div className="card summary">
        <div className="summary-nums">
          <div><b>{pct(total.correct, total.total)}%</b><span>выполнено</span></div>
          <div><b>{total.correct}</b><span>заданий верно</span></div>
          <div><b className="bad-t">{total.wrong}</b><span>с ошибкой</span></div>
          <div><b>{pct(total.firstOk, total.attempted)}%</b><span>верно с 1-й попытки</span></div>
          <div><b>{attempts.length}</b><span>всего попыток</span></div>
        </div>
        <ProgressBar c={total} /><Legend c={total} />
      </div>
      <h2>По разделам</h2>
      <div className="card"><SectionBreakdown index={index} states={states} /></div>

      <div className="tabs inline">
        <button className={tab === 'errors' ? 'active' : ''} onClick={() => setTab('errors')}>Разбор ошибок ({errorTasks.length})</button>
        <button className={tab === 'log' ? 'active' : ''} onClick={() => setTab('log')}>История попыток</button>
      </div>

      {tab === 'errors' && (
        <>
          <label className="check"><input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} /> Только задания, которые ещё не решены верно</label>
          {!shown.length && <p className="muted">Ошибок нет — отличная работа!</p>}
          <div className="error-list">
            {shown.map(({ t, s }) => {
              const sec = index.sectionById.get(t.section_id);
              const sol = solutions[t.id];
              return (
                <div key={t.id} className="card error-item">
                  <div className="error-head">
                    <span className="muted small">{sec?.title} · {sec?.subtitle}</span>
                    {s.status === 'correct' ? <span className="status ok">исправлено</span> : <span className="status bad">не решено</span>}
                  </div>
                  <Link to={`/p/${t.passage_id}`} className="error-title">{taskLabel(index, t)}</Link>
                  <p className="small">{shortPrompt(t)} {t.word && <b className="word inline">{t.word}</b>}</p>
                  <div className="small">Мои ответы: {s.attempts.map((a, i) => (
                    <code key={i} className={a.is_correct ? 'ok-t' : 'bad-t'}>{formatAnswer(t, a.answer)}</code>))}</div>
                  {sol && <button className="link" onClick={() => setOpen((o) => ({ ...o, [t.id]: !o[t.id] }))}>{open[t.id] ? 'Скрыть разбор' : 'Показать разбор'}</button>}
                  {sol && open[t.id] && <Explanation task={t} answers={sol.answers} explanation={sol.explanation} />}
                </div>
              );
            })}
          </div>
        </>
      )}
      {tab === 'log' && <div className="card"><AttemptLog index={index} attempts={attempts} onlyErrors={false} sectionId="" linkTasks /></div>}
      {profile?.role !== 'teacher' && <div style={{ marginTop: 32 }}><TeacherCode /></div>}
    </div>
  );
}
