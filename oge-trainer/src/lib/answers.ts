// Нормализация как в функции normalize_answer на сервере: регистр и пробелы не важны, орфография важна.
export function normalizeAnswer(s: string): string {
  return (s || '').toLowerCase().replace(/[’‘`´]/g, "'").replace(/\s+/g, '');
}

export function loginToEmail(login: string): string {
  const v = login.trim();
  if (v.includes('@')) return v.toLowerCase();
  return `${v.toLowerCase()}@oge-trainer.local`;
}

export function isValidLogin(v: string): boolean {
  const s = v.trim();
  if (s.includes('@')) return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
  return /^[a-zA-Z0-9._-]{3,32}$/.test(s);
}
