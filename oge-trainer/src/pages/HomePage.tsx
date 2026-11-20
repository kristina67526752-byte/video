import { Link } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { countFor, pct } from '../lib/progress';
import { Legend, ProgressBar } from '../components/ProgressBar';

export default function HomePage() {
  const { profile, index, states, attempts } = useApp();
  if (!index) return null;
  const all = [...index.tasksById.values()];
  const total = countFor(all, states);
  const last = attempts.length ? index.tasksById.get(attempts[attempts.length - 1].task_id) : undefined;
  const lastPassage = last?.passage_id ? index.passageById.get(last.passage_id) : undefined;

  return (
    <div className="page">
      <div className="hello">
        <div>
          <h1>Здравствуйте, {profile?.display_name.split(' ')[0]}!</h1>
          <p className="muted">Выберите раздел или продолжите с того места, где остановились.</p>
        </div>
        {lastPassage && <Link className="btn primary" to={`/p/${lastPassage.id}`}>Продолжить: {lastPassage.title}</Link>}
      </div>

      <div className="card summary">
        <div className="summary-nums">
          <div><b>{pct(total.correct, total.total)}%</b><span>выполнено</span></div>
          <div><b>{total.correct}</b><span>верно</span></div>
          <div><b className="bad-t">{total.wrong}</b><span>с ошибкой</span></div>
          <div><b>{pct(total.firstOk, total.attempted)}%</b><span>верно с 1-й попытки</span></div>
        </div>
        <ProgressBar c={total} />
        <Legend c={total} />
      </div>

      <div className="grid sections">
        {index.sections.map((s) => {
          const c = countFor(index.tasksBySection.get(s.id) || [], states);
          const n = index.passagesBySection.get(s.id)?.length || 0;
          return (
            <Link key={s.id} to={`/s/${s.id}`} className="card section-card">
              <div className="section-num">{s.title}</div>
              <h2>{s.subtitle}</h2>
              <p className="muted small">{n} {s.kind === 'matching' ? 'наборов текстов' : 'текстов'} · {c.total} заданий</p>
              <ProgressBar c={c} />
              <Legend c={c} />
            </Link>
          );
        })}
      </div>
    </div>
  );
}
