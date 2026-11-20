import type { Task } from '../lib/types';
import { formatAnswer } from '../lib/progress';

function renderLine(line: string) {
  const parts = line.split(/(«[^»]*»)/g);
  return parts.map((p, i) => (p.startsWith('«') ? <q key={i}>{p.slice(1, -1)}</q> : <span key={i}>{p}</span>));
}

export default function Explanation({ task, answers, explanation }: { task: Task; answers: string[]; explanation: string }) {
  const main = answers[0] ?? '';
  const extra = answers.slice(1);
  const steps = explanation.split('\n').filter(Boolean);
  return (
    <div className="explain">
      <div className="explain-answer">
        Правильный ответ: <b>{formatAnswer(task, main)}</b>
        {extra.length > 0 && <span className="muted small"> · также засчитывается: {extra.join(', ')}</span>}
      </div>
      {steps.length > 0 && (
        <ol className="steps">
          {steps.map((s, i) => <li key={i} className={/^(Ответ|Помните)/.test(s) ? 'final' : ''}>{renderLine(s)}</li>)}
        </ol>
      )}
    </div>
  );
}
