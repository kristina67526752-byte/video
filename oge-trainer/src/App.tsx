import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppProvider, useApp } from './context/AppContext';
import type { Api } from './lib/types';
import Layout from './components/Layout';
import AuthPage from './pages/AuthPage';
import HomePage from './pages/HomePage';
import SectionPage from './pages/SectionPage';
import PassagePage from './pages/PassagePage';
import StatsPage from './pages/StatsPage';
import TeacherPage from './pages/TeacherPage';
import StudentDetailPage from './pages/StudentDetailPage';

function Guarded() {
  const { profile, authLoading, index, catalogError } = useApp();
  if (authLoading) return <div className="center-screen"><div className="spinner" /></div>;
  if (!profile) return <AuthPage />;
  if (catalogError) {
    const network = /fetch|network|load failed/i.test(catalogError);
    return (
      <div className="center-screen"><div className="card narrow">
        <h2>{network ? 'Нет связи с базой данных' : 'Не удалось загрузить задания'}</h2>
        {network ? (
          <>
            <p>Браузер не смог достучаться до сервера Supabase. Обычно причина в интернете, VPN или блокировщике рекламы.</p>
            <ul>
              <li>Проверьте интернет и нажмите «Попробовать снова».</li>
              <li>Если включён VPN — попробуйте выключить его (или наоборот, включить).</li>
              <li>Отключите блокировщик рекламы для этого сайта.</li>
            </ul>
            <p className="muted small">Техническая причина: {catalogError}</p>
          </>
        ) : <p>{catalogError}</p>}
        <button className="btn primary" onClick={() => window.location.reload()}>Попробовать снова</button>
      </div></div>
    );
  }
  if (!index) return <div className="center-screen"><div className="spinner" /><p className="muted">Загружаю задания…</p></div>;
  const teacher = profile.role === 'teacher';
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/s/:sectionId" element={<SectionPage />} />
        <Route path="/p/:passageId" element={<PassagePage />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/teacher" element={teacher ? <TeacherPage /> : <Navigate to="/" />} />
        <Route path="/teacher/:userId" element={teacher ? <StudentDetailPage /> : <Navigate to="/" />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Route>
    </Routes>
  );
}

export default function App({ api }: { api: Api }) {
  return (
    <AppProvider api={api}>
      <HashRouter>
        <Guarded />
      </HashRouter>
    </AppProvider>
  );
}
