import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { countFor } from '../lib/progress';
import { Legend, ProgressBar } from '../components/ProgressBar';

type Filter = 'all' | 'new' | 'progress' | 'errors' | 'done';
const FILTERS: [Filter, string][] = [['all', 'Все'], ['new', 'Не начатые'], ['progress', 'В процессе'], ['errors', 'С ошибками'], ['done', 'Выполненные']];

export default function SectionPage() {
  const { sectionId } = useParams();
  const { index, states } = useApp();
  const [filter, setFilter] = useState<Filter>('all');
  const section = index?.sectionById.get(sectionId || '');
  if (!index || !section) return <div className="page"><p>Раздел не найден.</p></div>;
  const passages = index.passagesBySection.get(section.id) || [];
  const c = countFor(index.tasksBySection.get(section.id) || [], states);

  const items = passages.map((p) => ({ p, c: countFor(index.tasksByPassage.get(p.id) || [], states) })).filter(({ c: pc }) => {
    if (filter === 'new') return pc.attempted === 0;
    if (filter === 'progress') return pc.attempted > 0 && pc.correct < pc.total;
    if (filter === 'errors') return pc.wrong > 0;
    if (filter === 'done') return pc.correct === pc.total;
    return true;
  });

  return (
    <div className="page">
      <div className="crumbs"><Link to="/">Тренажёр</Link> / {section.title}</div>
      <h1>{section.title} <span className="muted">· {section.subtitle}</span></h1>
      {section.instruction && <p className="instruction">{section.instruction}</p>}
      {section.kind !== 'open' && <div className="card"><ProgressBar c={c} /><Legend c={c} /></div>}
      {section.kind !== 'open' && <div className="chips">
        {FILTERS.map(([k, label]) => <button key={k} className={'chip' + (filter === k ? ' active' : '')} onClick={() => setFilter(k)}>{label}</button>)}
      </div>}
      <div className="grid passages">
        {items.map(({ p, c: pc }) => {
          if (section.kind === 'open') {
            return (
              <Link key={p.id} to={`/p/${p.id}`} className="card passage-card">
                <div className="passage-top"><span className="muted small">№ {passages.indexOf(p) + 1}</span></div>
                <h3>{p.title}</h3>
              </Link>
            );
          }
          const status = pc.attempted === 0 ? 'Не начато' : pc.correct === pc.total ? 'Выполнено' : 'В процессе';
          return (
            <Link key={p.id} to={`/p/${p.id}`} className="card passage-card">
              <div className="passage-top"><span className="muted small">№ {passages.indexOf(p) + 1}</span><span className={'status ' + (pc.correct === pc.total ? 'ok' : pc.wrong ? 'bad' : pc.attempted ? 'warn' : '')}>{status}</span></div>
              <h3>{p.title}</h3>
              <ProgressBar c={pc} thin />
              <div className="small muted">{pc.correct} из {pc.total} верно{pc.wrong ? ` · ошибок: ${pc.wrong}` : ''}</div>
            </Link>
          );
        })}
        {!items.length && <p className="muted">Нет текстов под этот фильтр.</p>}
      </div>
    </div>
  );
}
