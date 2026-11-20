import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useApp } from '../context/AppContext';
import type { ChoiceOption, MatchingOptions, Solution, Task } from '../lib/types';
import type { TaskState } from '../lib/progress';
import { dateTime, formatAnswer } from '../lib/progress';
import { normalizeAnswer } from '../lib/answers';
import Explanation from './Explanation';

interface Props { task: Task; state?: TaskState; solution?: Solution; onSolution(s: Solution): void; highlight?: boolean }

export function Prompt({ text }: { text: string }) {
  const parts = text.split('_____');
  return <>{parts.map((p, i) => <span key={i}>{p}{i < parts.length - 1 && <span className="gap">______</span>}</span>)}</>;
}

export default function TaskCard({ task, state, solution, onSolution, highlight }: Props) {
  const { api, addAttempt, profile } = useApp();
  const last = state?.attempts[state.attempts.length - 1];
  const [value, setValue] = useState<string>(last?.answer ?? '');
  const [result, setResult] = useState<{ correct: boolean; items: boolean[]; score: number; max: number } | null>(
    last ? { correct: last.is_correct, items: [], score: last.score, max: last.max_score } : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showExpl, setShowExpl] = useState<boolean>(!!last && !last.is_correct);
  const [showHistory, setShowHistory] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => { if (highlight) ref.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, [highlight]);

  const matching = task.kind === 'matching' ? (task.options as MatchingOptions) : null;
  const choices = task.kind === 'choice' ? (task.options as ChoiceOption[]) : null;
  const letters = matching?.letters ?? [];
  const mval = matching ? (value || '0'.repeat(letters.length)).padEnd(letters.length, '0') : '';

  // Для старых попыток подсветка ячеек соответствия считается по полученному разбору.
  const items = result?.items.length ? result.items
    : matching && result && solution ? letters.map((_, i) => normalizeAnswer(solution.answers[0])[i] === mval[i]) : [];

  const checked = result !== null;
  const canCheck = !busy && !checked && (matching ? !mval.includes('0') : value.trim().length > 0);

  async function check() {
    if (!canCheck) return;
    setBusy(true); setError(null);
    try {
      const r = await api.checkAnswer(task.id, value);
      setResult({ correct: r.correct, items: r.items || [], score: r.score, max: r.max_score });
      onSolution({ task_id: task.id, answers: r.answers, explanation: r.explanation });
      setShowExpl(!r.correct);
      addAttempt({ id: Date.now(), user_id: profile!.id, task_id: task.id, section_id: task.section_id, answer: value.trim(),
        is_correct: r.correct, score: r.score, max_score: r.max_score, created_at: new Date().toISOString() });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function retry() { setResult(null); setValue(''); setShowExpl(false); setError(null); }
  const onKey = (e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); void check(); } };
  const tone = !checked ? '' : result!.correct ? 'ok' : 'bad';
  const tries = state?.attempts.length ?? 0;

  return (
    <div ref={ref} id={`task-${task.id}`} className={`task card ${tone} ${highlight ? 'flash' : ''}`}>
      <div className="task-head">
        <span className="num">{task.number}</span>
        {task.kind === 'text' && task.word && <span className="word">{task.word}</span>}
        <span className="task-status">
          {state?.status === 'correct' && <span className="status ok">выполнено</span>}
          {state?.status === 'wrong' && <span className="status bad">есть ошибка</span>}
        </span>
      </div>

      {task.kind === 'text' && (
        <>
          <p className="prompt"><Prompt text={task.prompt} /></p>
          <div className="answer-row">
            <input className={'answer ' + tone} value={value} disabled={checked || busy} onChange={(e) => setValue(e.target.value)} onKeyDown={onKey}
              placeholder="Ваш ответ" autoCapitalize="none" autoCorrect="off" spellCheck={false} aria-label={`Ответ на задание ${task.number}`} />
            {!checked ? <button className="btn primary" disabled={!canCheck} onClick={check}>{busy ? '…' : 'Проверить'}</button>
              : <button className="btn ghost" onClick={retry}>Ещё раз</button>}
          </div>
        </>
      )}

      {task.kind === 'choice' && choices && (
        <>
          <p className="prompt statement">{task.prompt}</p>
          <div className="choices" role="radiogroup">
            {choices.map((o) => {
              const sel = value === o.value;
              const cls = sel ? (checked ? (result!.correct ? 'ok' : 'bad') : 'sel') : '';
              return (
                <button key={o.value} role="radio" aria-checked={sel} disabled={checked || busy} className={'choice ' + cls} onClick={() => setValue(o.value)}>
                  <b>{o.value}</b> {o.label}
                </button>
              );
            })}
            {!checked ? <button className="btn primary" disabled={!canCheck} onClick={check}>{busy ? '…' : 'Проверить'}</button>
              : <button className="btn ghost" onClick={retry}>Ещё раз</button>}
          </div>
        </>
      )}

      {task.kind === 'matching' && matching && (
        <>
          <ol className="questions">{matching.questions.map((q, i) => <li key={i}><b>{i + 1}.</b> {q}</li>)}</ol>
          <div className="match-table">
            {letters.map((L, i) => (
              <label key={L} className={'match-cell ' + (items.length ? (items[i] ? 'ok' : 'bad') : '')}>
                <span>Текст {L}</span>
                <select value={mval[i]} disabled={checked || busy} onChange={(e) => {
                  const arr = mval.split(''); arr[i] = e.target.value; setValue(arr.join(''));
                }}>
                  <option value="0">—</option>
                  {matching.questions.map((_, q) => <option key={q} value={String(q + 1)}>{q + 1}</option>)}
                </select>
              </label>
            ))}
          </div>
          <div className="answer-row end">
            {checked && <span className={'score ' + tone}>{result!.score} из {result!.max}</span>}
            {!checked ? <button className="btn primary" disabled={!canCheck} onClick={check}>{busy ? '…' : 'Проверить'}</button>
              : <button className="btn ghost" onClick={retry}>Ещё раз</button>}
          </div>
        </>
      )}

      {error && <div className="alert bad">{error}</div>}
      {checked && (
        <div className={'verdict ' + tone}>
          {result!.correct ? '✓ Верно!' : task.kind === 'matching' ? '✗ Есть ошибки — разберём' : '✗ Неверно — разберём решение'}
          {solution && <button className="link" onClick={() => setShowExpl(!showExpl)}>{showExpl ? 'Скрыть разбор' : 'Показать разбор'}</button>}
        </div>
      )}
      {checked && showExpl && solution && <Explanation task={task} answers={solution.answers} explanation={solution.explanation} />}
      {tries > 0 && (
        <div className="history">
          <button className="link small" onClick={() => setShowHistory(!showHistory)}>История попыток ({tries})</button>
          {showHistory && (
            <ul>
              {state!.attempts.map((a, i) => (
                <li key={a.id + '-' + i} className={a.is_correct ? 'ok-t' : 'bad-t'}>
                  {a.is_correct ? '✓' : '✗'} {formatAnswer(task, a.answer)} <span className="muted">· {dateTime(a.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
