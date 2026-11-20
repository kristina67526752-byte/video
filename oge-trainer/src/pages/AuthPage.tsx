import { useState, type FormEvent } from 'react';
import { useApp } from '../context/AppContext';
import { isValidLogin } from '../lib/answers';

export default function AuthPage() {
  const { api } = useApp();
  const [mode, setMode] = useState<'in' | 'up'>('in');
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [name, setName] = useState('');
  const [isTeacher, setIsTeacher] = useState(false);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null); setInfo(null);
    if (!isValidLogin(login)) { setError('Введите email или логин: 3–32 латинские буквы, цифры, точка, дефис или подчёркивание.'); return; }
    if (mode === 'up') {
      if (name.trim().length < 2) { setError('Укажите имя и фамилию — так вас увидит преподаватель.'); return; }
      if (password.length < 6) { setError('Пароль должен быть не короче 6 символов.'); return; }
      if (password !== password2) { setError('Пароли не совпадают.'); return; }
      if (isTeacher && !code.trim()) { setError('Введите код преподавателя.'); return; }
    }
    setBusy(true);
    try {
      if (mode === 'in') await api.signIn(login, password);
      else {
        const r = await api.signUp({ login, password, displayName: name, teacherCode: isTeacher ? code : '' });
        if (r.needsConfirmation) setInfo('Аккаунт создан. Подтвердите email по ссылке из письма, затем войдите.');
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-hero">
        <div className="brand big"><span className="brand-mark">En</span> ОГЭ · English</div>
        <h1>Тренажёр по английскому языку</h1>
        <p>1338 заданий из открытого банка ФИПИ: чтение, грамматика и словообразование. Проверка как на экзамене и подробный разбор каждой ошибки.</p>
        <ul className="hero-list">
          <li><b>Задание 12</b> — тексты и вопросы</li>
          <li><b>Задания 13–19</b> — True / False / Not stated</li>
          <li><b>Задания 20–28</b> — грамматика</li>
          <li><b>Задания 29–34</b> — словообразование</li>
        </ul>
      </div>
      <form className="card auth-card" onSubmit={submit}>
        <div className="tabs">
          <button type="button" className={mode === 'in' ? 'active' : ''} onClick={() => { setMode('in'); setError(null); }}>Вход</button>
          <button type="button" className={mode === 'up' ? 'active' : ''} onClick={() => { setMode('up'); setError(null); }}>Регистрация</button>
        </div>
        {api.mode === 'demo' && (
          <div className="note">Демо-режим: данные хранятся только в этом браузере. Код преподавателя: <code>demo-teacher</code></div>
        )}
        {mode === 'up' && (
          <label>Имя и фамилия
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Анна Иванова" autoComplete="name" />
          </label>
        )}
        <label>Email или логин
          <input value={login} onChange={(e) => setLogin(e.target.value)} placeholder="anna.ivanova или anna@mail.ru" autoComplete="username" autoCapitalize="none" />
        </label>
        <label>Пароль
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === 'in' ? 'current-password' : 'new-password'} />
        </label>
        {mode === 'up' && (
          <>
            <label>Повторите пароль
              <input type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} autoComplete="new-password" />
            </label>
            <label className="check">
              <input type="checkbox" checked={isTeacher} onChange={(e) => setIsTeacher(e.target.checked)} /> Я преподаватель
            </label>
            {isTeacher && (
              <label>Код преподавателя
                <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Выдаётся администратором сайта" />
                <span className="hint">Если код неверный, будет создан аккаунт ученика.</span>
              </label>
            )}
          </>
        )}
        {error && <div className="alert bad">{error}</div>}
        {info && <div className="alert ok">{info}</div>}
        <button className="btn primary block" disabled={busy}>{busy ? 'Подождите…' : mode === 'in' ? 'Войти' : 'Создать аккаунт'}</button>
      </form>
    </div>
  );
}
