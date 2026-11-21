export default function SetupScreen({ message }: { message: string }) {
  return (
    <div className="center-screen">
      <div className="card narrow">
        <h1>Сайт ещё не подключён к базе</h1>
        <p>{message}</p>
        <ol>
          <li>Откройте файл <code>НАСТРОЙКИ.txt</code> в папке проекта.</li>
          <li>Вставьте адрес проекта и ключи из Supabase → Project Settings → API Keys → «View legacy API keys» и сохраните файл.</li>
          <li>Остановите сайт (Ctrl+C в Терминале) и снова запустите <code>npm run dev</code>.</li>
        </ol>
        <p className="muted">Посмотреть сайт без базы можно командой <code>npm run demo</code>.</p>
      </div>
    </div>
  );
}
