import type { Api } from './types';
import { createSupabaseApi } from './supabaseApi';

export class SetupError extends Error {}

export async function createApi(): Promise<Api> {
  if (__DEMO__) {
    const m = await import('./demoApi');
    return m.createDemoApi();
  }
  const url = import.meta.env.VITE_SUPABASE_URL;
  const key = import.meta.env.VITE_SUPABASE_ANON_KEY;
  if (!url || !key || url.includes('xxxxxxxx') || !url.startsWith('https://')) throw new SetupError('В файле НАСТРОЙКИ.txt не указаны адрес проекта Supabase и ключ anon.');
  const proxy = await detectProxy(key);
  return proxy ? createSupabaseApi(proxy, key, { proxied: true }) : createSupabaseApi(url, key);
}

// На опубликованном сайте (Netlify) запросы к Supabase идут через адрес самого сайта: /sb/… → supabase.co.
// Так ученикам не нужен прямой доступ к supabase.co, который у некоторых провайдеров работает нестабильно.
async function detectProxy(key: string): Promise<string | null> {
  const host = window.location.hostname;
  if (host === 'localhost' || host === '127.0.0.1' || window.location.protocol === 'file:') return null;
  const base = window.location.origin + '/sb';
  try {
    const ctrl = new AbortController();
    const t = window.setTimeout(() => ctrl.abort(), 5000);
    const r = await fetch(base + '/auth/v1/health', { headers: { apikey: key }, signal: ctrl.signal });
    window.clearTimeout(t);
    const type = r.headers.get('content-type') || '';
    return r.ok && type.includes('json') ? base : null;
  } catch {
    return null;
  }
}
