import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { countFor, pct } from '../lib/progress';
import { ProgressBar } from './ProgressBar';

export default function Layout() {
  const { profile, api, index, states } = useApp();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const teacher = profile?.role === 'teacher';
  const wide = loc.pathname.startsWith('/p/');

  return (
    <div className="app">
      <header className="topbar">
        <button className="icon-btn menu-btn" onClick={() => setOpen(!open)} aria-label="Меню">☰</button>
        <NavLink to="/" className="brand"><span className="brand-mark">En</span><span className="brand-text">ОГЭ · English</span></NavLink>
        <nav className="topnav">
          <NavLink to="/" end>Тренажёр</NavLink>
          <NavLink to="/stats">Мой прогресс</NavLink>
          {teacher && <NavLink to="/teacher">Преподаватель</NavLink>}
        </nav>
        <div className="user">
          <span className="user-name" title={profile?.login || ''}>{profile?.display_name}{teacher && <span className="badge">преподаватель</span>}</span>
          <button className="btn ghost small" onClick={() => { window.location.hash = '#/'; void api.signOut(); }}>Выйти</button>
        </div>
      </header>
      {api.mode === 'demo' && <div className="demo-banner">Демо-режим: данные сохраняются только в этом браузере</div>}
      <div className={'shell' + (wide ? ' wide' : '')}>
        <aside className={'sidebar' + (open ? ' open' : '')} onClick={() => setOpen(false)}>
          <div className="side-title">Разделы</div>
          {index?.sections.map((s) => {
            const c = countFor(index.tasksBySection.get(s.id) || [], states);
            return (
              <NavLink key={s.id} to={`/s/${s.id}`} className="side-item">
                <div className="side-head"><b>{s.title}</b><span className="muted small">{pct(c.correct, c.total)}%</span></div>
                <div className="small muted">{s.subtitle}</div>
                <ProgressBar c={c} thin />
              </NavLink>
            );
          })}
          <div className="side-sep" />
          <NavLink to="/stats" className="side-link">📈 Мой прогресс и ошибки</NavLink>
          {teacher && <NavLink to="/teacher" className="side-link">👩‍🏫 Кабинет преподавателя</NavLink>}
        </aside>
        {open && <div className="scrim" onClick={() => setOpen(false)} />}
        <main className="main"><Outlet /></main>
      </div>
    </div>
  );
}
