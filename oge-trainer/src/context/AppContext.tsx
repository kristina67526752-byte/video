import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Api, Attempt, Profile } from '../lib/types';
import { buildIndex, buildStates, type Index, type TaskState } from '../lib/progress';

interface AppState {
  api: Api;
  profile: Profile | null;
  authLoading: boolean;
  index: Index | null;
  catalogError: string | null;
  attempts: Attempt[];
  states: Map<string, TaskState>;
  addAttempt(a: Attempt): void;
  refreshProfile(): Promise<void>;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ api, children }: { api: Api; children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [index, setIndex] = useState<Index | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);

  const refreshProfile = useCallback(async () => {
    try { setProfile(await api.getProfile()); } catch { setProfile(null); }
    setAuthLoading(false);
  }, [api]);

  useEffect(() => {
    void refreshProfile();
    return api.onAuthChange(() => { void refreshProfile(); });
  }, [api, refreshProfile]);

  const userId = profile?.id;
  useEffect(() => {
    if (!userId) { setAttempts([]); return; }
    let cancelled = false;
    (async () => {
      try {
        const [cat, att] = await Promise.all([index ? Promise.resolve(null) : api.loadCatalog(), api.myAttempts()]);
        if (cancelled) return;
        if (cat) {
          if (!cat.tasks.length) setCatalogError('В базе пока нет заданий. Загрузите их командой npm run push-tasks (см. README).');
          setIndex(buildIndex(cat));
        }
        setAttempts(att);
      } catch (e) {
        if (!cancelled) setCatalogError((e as Error).message);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, userId]);

  const addAttempt = useCallback((a: Attempt) => setAttempts((prev) => [...prev, a]), []);
  const states = useMemo(() => buildStates(attempts), [attempts]);

  const value = useMemo<AppState>(() => ({ api, profile, authLoading, index, catalogError, attempts, states, addAttempt, refreshProfile }),
    [api, profile, authLoading, index, catalogError, attempts, states, addAttempt, refreshProfile]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp outside provider');
  return v;
}
