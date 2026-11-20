import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { countFor } from '../lib/progress';
import type { Passage, Section, Solution, Task } from '../lib/types';
import type { TaskState } from '../lib/progress';
import TaskCard from '../components/TaskCard';
import { Legend, ProgressBar } from '../components/ProgressBar';

function TextPanel({ section, passage, tasks, states, onGapClick }: {
  section: Section; passage: Passage; tasks: Task[]; states: Map<string, TaskState>; onGapClick(id: string): void;
}) {
  if (section.kind === 'gap') {
    return (
      <div className="reading gap-text">
        {tasks.map((t) => {
          const st = states.get(t.id);
          const okAns = st?.attempts.find((a) => a.is_correct)?.answer;
          const parts = t.prompt.split('_____');
          return (
            <span key={t.id}>
              {parts.map((p, i) => (
                <span key={i}>{p}{i < parts.length - 1 && (
                  <button className={'gap-chip ' + (st?.status ?? '')} onClick={() => onGapClick(t.id)} title={t.word || ''}>
                    <sup>{t.number}</sup>{okAns ? okAns : <>&nbsp;{t.word}&nbsp;</>}
                  </button>
                )}</span>
              ))}{' '}
            </span>
          );
        })}
      </div>
    );
  }
  const paras = passage.body.split(/\n\s*\n/).filter(Boolean);
  if (section.kind === 'matching') {
    return (
      <div className="reading">
        {paras.map((p, i) => {
          const m = p.match(/^([A-H])\.\s*/);
          return <div key={i} className="lettered"><span className="letter">{m ? m[1] : ''}</span><p>{m ? p.slice(m[0].length) : p}</p></div>;
        })}
      </div>
    );
  }
  return (
    <div className="reading">
      {paras.map((p, i) => <p key={i} className="numbered"><span className="pnum">{i + 1}</span>{p}</p>)}
    </div>
  );
}

export default function PassagePage() {
  const { passageId } = useParams();
  const { index, states, api } = useApp();
  const [solutions, setSolutions] = useState<Record<string, Solution>>({});
  const [focus, setFocus] = useState<string | null>(null);
  const passage = index?.passageById.get(passageId || '');
  const section = passage ? index?.sectionById.get(passage.section_id) : undefined;
  const tasks = useMemo(() => (passage && index?.tasksByPassage.get(passage.id)) || [], [passage, index]);
  const [textOpen, setTextOpen] = useState(section?.kind !== 'gap');

  useEffect(() => {
    if (!passage) return;
    window.scrollTo(0, 0);
    setTextOpen(section?.kind !== 'gap');
    void api.touch(passage.section_id, passage.id).catch(() => undefined);
    const attempted = tasks.filter((t) => states.has(t.id)).map((t) => t.id);
    if (attempted.length) {
      api.getSolutions(attempted).then((list) => setSolutions((prev) => {
        const next = { ...prev }; list.forEach((s) => { next[s.task_id] = s; }); return next;
      })).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [passage?.id]);

  if (!index || !passage || !section) return <div className="page"><p>Текст не найден.</p></div>;
  const siblings = index.passagesBySection.get(section.id) || [];
  const pos = siblings.findIndex((p) => p.id === passage.id);
  const prev = siblings[pos - 1]; const next = siblings[pos + 1];
  const c = countFor(tasks, states);

  return (
    <div className="page passage-page">
      <div className="passage-header">
        <div className="crumbs"><Link to="/">Тренажёр</Link> / <Link to={`/s/${section.id}`}>{section.title} · {section.subtitle}</Link> / {pos + 1} из {siblings.length}</div>
        <div className="passage-title-row">
          <h1>{passage.title}</h1>
          <div className="pager">
            {prev ? <Link className="btn ghost small" to={`/p/${prev.id}`}>← Назад</Link> : <span />}
            {next ? <Link className="btn ghost small" to={`/p/${next.id}`}>Дальше →</Link> : <span />}
          </div>
        </div>
        <div className="mini-progress"><ProgressBar c={c} thin /><Legend c={c} /></div>
      </div>

      <div className="split">
        <section className={'text-pane' + (textOpen ? ' open' : '')}>
          <button className="text-toggle" onClick={() => setTextOpen(!textOpen)} aria-expanded={textOpen}>
            {textOpen ? '▾ Свернуть текст' : '▸ Показать текст'}
          </button>
          <div className="text-body">
            {section.instruction && <p className="instruction small">{section.instruction}</p>}
            <TextPanel section={section} passage={passage} tasks={tasks} states={states} onGapClick={(id) => { setFocus(id); setTimeout(() => setFocus(null), 1500); }} />
          </div>
        </section>
        <section className="tasks-pane">
          {tasks.map((t) => (
            <TaskCard key={t.id} task={t} state={states.get(t.id)} solution={solutions[t.id]} highlight={focus === t.id}
              onSolution={(s) => setSolutions((p) => ({ ...p, [s.task_id]: s }))} />
          ))}
          <div className="pager bottom">
            {prev ? <Link className="btn ghost" to={`/p/${prev.id}`}>← Предыдущий текст</Link> : <span />}
            {next ? <Link className="btn primary" to={`/p/${next.id}`}>Следующий текст →</Link> : <Link className="btn ghost" to={`/s/${section.id}`}>К списку текстов</Link>}
          </div>
        </section>
      </div>
    </div>
  );
}
