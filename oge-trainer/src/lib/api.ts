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
  return createSupabaseApi(url, key);
}
