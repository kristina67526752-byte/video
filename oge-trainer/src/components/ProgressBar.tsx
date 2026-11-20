import type { Counts } from '../lib/progress';
import { pct } from '../lib/progress';

export function ProgressBar({ c, thin }: { c: Pick<Counts, 'total' | 'correct' | 'wrong'>; thin?: boolean }) {
  return (
    <div className={'pbar' + (thin ? ' thin' : '')} role="img" aria-label={`Верно ${c.correct}, с ошибкой ${c.wrong}, всего ${c.total}`}>
      <span className="seg ok" style={{ width: `${(c.correct / Math.max(c.total, 1)) * 100}%` }} />
      <span className="seg bad" style={{ width: `${(c.wrong / Math.max(c.total, 1)) * 100}%` }} />
    </div>
  );
}

export function Legend({ c }: { c: Counts }) {
  return (
    <div className="legend">
      <span><i className="dot ok" />верно {c.correct}</span>
      <span><i className="dot bad" />с ошибкой {c.wrong}</span>
      <span><i className="dot rest" />осталось {c.left}</span>
      <span className="muted">· {pct(c.correct, c.total)}%</span>
    </div>
  );
}
