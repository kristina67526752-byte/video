import { Link } from 'react-router-dom';
import type { Attempt, Task } from '../lib/types';
import { countFor, dateTime, formatAnswer, pct, type Index, type TaskState } from '../lib/progress';
import { ProgressBar } from './ProgressBar';

export function taskLabel(index: Index, t: Task | undefined): string {
  if (!t) return 'Задание удалено';
  const p = t.passage_id ? index.passageById.get(t.passage_id) : undefined;
  return `№ ${t.number} · ${p?.title ?? ''}`;
}

export function shortPrompt(t: Task | undefined): string {
  if (!t) return '';
  if (t.kind === 'matching') return 'Соответствие текстов A–F и вопросов';
  const s = t.prompt.replace(/_____/g, '___');
  return s.length > 140 ? '…' + s.slice(-140) : s;
}

export function SectionBreakdown({ index, states }: { index: Index; states: Map<string, TaskState> }) {
  return (
    <div className="breakdown">
      {index.sections.filter((s) => s.kind !== 'open').map((s) => {
        const c = countFor(index.tasksBySection.get(s.id) || [], states);
        return (
          <div key={s.id} className="bd-row">
            <div className="bd-name"><b>{s.title}</b><span className="muted small">{s.subtitle}</span></div>
            <ProgressBar c={c} />
            <div className="bd-nums small">
              <span className="ok-t">✓ {c.correct}</span><span className="bad-t">✗ {c.wrong}</span><span className="muted">осталось {c.left}</span>
              <span>{pct(c.correct, c.total)}%</span>
              <span className="muted" title="Верно с первой попытки">1-я попытка: {pct(c.firstOk, c.attempted)}%</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function AttemptLog({ index, attempts, onlyErrors, sectionId, linkTasks }: {
  index: Index; attempts: Attempt[]; onlyErrors: boolean; sectionId: string; linkTasks?: boolean;
}) {
  const order = new Map<string, number>();
  const numbered = [...attempts].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id).map((a) => {
    const n = (order.get(a.task_id) || 0) + 1; order.set(a.task_id, n); return { a, n };
  });
  const rows = numbered.reverse().filter(({ a }) => (!onlyErrors || !a.is_correct) && (!sectionId || a.section_id === sectionId));
  if (!rows.length) return <p className="muted">Попыток пока нет.</p>;
  return (
    <div className="table-wrap">
      <table className="table log">
        <thead><tr><th>Время</th><th>Задание</th><th>Ответ ученика</th><th>Результат</th><th>Попытка</th></tr></thead>
        <tbody>
          {rows.slice(0, 500).map(({ a, n }) => {
            const t = index.tasksById.get(a.task_id);
            const sec = index.sectionById.get(a.section_id || '');
            return (
              <tr key={a.id + '-' + a.created_at}>
                <td className="nowrap">{dateTime(a.created_at)}</td>
                <td>
                  <div className="small muted">{sec?.title} · {sec?.subtitle}</div>
                  {linkTasks && t?.passage_id ? <Link to={`/p/${t.passage_id}`}>{taskLabel(index, t)}</Link> : <span>{taskLabel(index, t)}</span>}
                  <div className="small muted">{shortPrompt(t)}{t?.word ? ` (${t.word})` : ''}</div>
                </td>
                <td><code className={a.is_correct ? 'ok-t' : 'bad-t'}>{formatAnswer(t, a.answer)}</code></td>
                <td>{a.is_correct ? <span className="status ok">верно</span> : <span className="status bad">{a.max_score > 1 ? `ошибка (${a.score}/${a.max_score})` : 'ошибка'}</span>}</td>
                <td className="center">{n}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.length > 500 && <p className="muted small">Показаны последние 500 попыток из {rows.length}.</p>}
    </div>
  );
}
