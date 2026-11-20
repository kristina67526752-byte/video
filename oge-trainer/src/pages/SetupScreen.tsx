export default function SetupScreen({ message }: { message: string }) {
  return (
    <div className="center-screen">
      <div className="card narrow">
        <h1>Сайт ещё не подключён к базе</h1>
        <p>{message}</p>
        <ol>
          <li>Скопируйте файл <code>.env.example</code> в <code>.env.local</code>.</li>
          <li>Вставьте адрес проекта и anon-ключ из Supabase → Project Settings → API.</li>
          <li>Перезапустите <code>npm run dev</code> или пересоберите сайт.</li>
        </ol>
        <p className="muted">Посмотреть сайт без базы можно командой <code>npm run demo</code>.</p>
      </div>
    </div>
  );
}
