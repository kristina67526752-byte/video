import { useEffect, useRef, useState } from 'react';
import type { OpenOptions, Task } from '../lib/types';

// Задания без автопроверки: письмо (35) и устная часть. Ученик выполняет задание и отправляет его преподавателю сам.
const countWords = (s: string) => (s.trim().match(/[A-Za-zА-Яа-яЁё0-9’'-]+/g) || []).length;
const draftKey = (id: string) => `draft.${id}`;

function readDraft(id: string): string {
  try { return localStorage.getItem(draftKey(id)) || ''; } catch { return ''; }
}
function saveDraft(id: string, v: string) {
  try { localStorage.setItem(draftKey(id), v); } catch { /* недоступно — не страшно */ }
}

function EmailPrompt({ text }: { text: string }) {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => /^From:/i.test(l));
  const end = lines.findIndex((l, i) => i > start && /^Write a message|^Write an? /i.test(l));
  if (start < 0) return <p className="prompt open-prompt">{text}</p>;
  const intro = lines.slice(0, start);
  const letter = lines.slice(start, end < 0 ? undefined : end);
  const tail = end < 0 ? [] : lines.slice(end);
  return (
    <div className="open-prompt">
      {intro.map((l, i) => <p key={'i' + i}>{l}</p>)}
      <div className="email-box">{letter.map((l, i) => <p key={'l' + i} className={/^(From|To|Subject):/i.test(l) ? 'email-head' : ''}>{l}</p>)}</div>
      {tail.map((l, i) => <p key={'t' + i}><b>{l}</b></p>)}
    </div>
  );
}

function EmailTask({ task, opts }: { task: Task; opts: OpenOptions }) {
  const [text, setText] = useState(() => readDraft(task.id));
  const [copied, setCopied] = useState(false);
  const words = countWords(text);
  const min = opts.minWords ?? 100, max = opts.maxWords ?? 120;
  const tone = words === 0 ? '' : words < min ? 'warn' : words > max ? 'bad' : 'ok';

  useEffect(() => { saveDraft(task.id, text); }, [task.id, text]);

  async function copy() {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* пусть выделит вручную */ }
  }

  return (
    <>
      <EmailPrompt text={task.prompt} />
      <textarea className="letter" value={text} onChange={(e) => setText(e.target.value)} rows={12} spellCheck={false}
        placeholder={'Dear …,\n\nThanks for your email! …\n\nBest wishes,\n…'} aria-label="Текст письма" />
      <div className="answer-row">
        <span className={'word-count ' + tone}>
          Слов: <b>{words}</b> · нужно {min}–{max}
          {tone === 'warn' && ' — маловато'}
          {tone === 'bad' && ' — слишком много: лишнее не будет оцениваться'}
        </span>
        <button className="btn primary" disabled={!text.trim()} onClick={copy}>{copied ? '✓ Скопировано' : 'Скопировать текст'}</button>
      </div>
      <p className="muted small">Черновик сохраняется в этом браузере. Когда закончите — скопируйте текст и отправьте преподавателю в личные сообщения.</p>
    </>
  );
}

function fmt(sec: number) { return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`; }

function SpeakingTask({ task, opts }: { task: Task; opts: OpenOptions }) {
  const prep = opts.prepSec ?? 90, speak = opts.speakSec ?? 120;
  const [phase, setPhase] = useState<'idle' | 'prep' | 'speak' | 'done'>('idle');
  const [left, setLeft] = useState(prep);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearInterval(timer.current), []);

  function run(p: 'prep' | 'speak') {
    window.clearInterval(timer.current);
    setPhase(p); setLeft(p === 'prep' ? prep : speak);
    timer.current = window.setInterval(() => {
      setLeft((x) => {
        if (x > 1) return x - 1;
        window.clearInterval(timer.current);
        if (p === 'prep') { window.setTimeout(() => run('speak'), 0); return speak; }
        setPhase('done'); return 0;
      });
    }, 1000);
  }

  const lines = task.prompt.split('\n');
  const isRead = opts.mode === 'read';
  return (
    <>
      <div className="open-prompt">
        <p className="muted">{lines[0]}</p>
        {isRead
          ? <p className="read-text">{lines.slice(1).join(' ')}</p>
          : <ul className="talk-plan">{lines.slice(1).map((l, i) => (/^Remember to say|^You have to talk/i.test(l) ? <li key={i} className="plain"><b>{l}</b></li> : <li key={i}>{l}</li>))}</ul>}
      </div>
      <div className={'timer ' + phase}>
        {phase === 'idle' && <button className="btn primary" onClick={() => run('prep')}>Начать: {fmt(prep)} на подготовку</button>}
        {phase === 'prep' && <><span>Подготовка: <b>{fmt(left)}</b></span><button className="btn ghost small" onClick={() => run('speak')}>Я готов — начать ответ</button></>}
        {phase === 'speak' && <><span>{isRead ? 'Читайте вслух' : 'Говорите'}: <b>{fmt(left)}</b></span><button className="btn ghost small" onClick={() => { window.clearInterval(timer.current); setPhase('done'); }}>Закончить</button></>}
        {phase === 'done' && <><span>✓ Время вышло</span><button className="btn ghost small" onClick={() => { setPhase('idle'); setLeft(prep); }}>Ещё раз</button></>}
      </div>
      <p className="muted small">
        Запишите ответ голосовым сообщением (в мессенджере или диктофоне), пока идёт время ответа, и отправьте преподавателю в личные сообщения.
        На экзамене {isRead ? 'на чтение даётся не больше 2 минут' : 'нужно говорить без остановок 10–12 предложений'}.
      </p>
    </>
  );
}

export default function OpenTaskCard({ task }: { task: Task }) {
  const opts = (task.options || { mode: 'email' }) as OpenOptions;
  return (
    <div className="task card open-task">
      <div className="task-head">
        <span className="num">{task.number}</span>
        <span className="status">без автопроверки</span>
      </div>
      {opts.mode === 'email' ? <EmailTask task={task} opts={opts} /> : <SpeakingTask task={task} opts={opts} />}
    </div>
  );
}
