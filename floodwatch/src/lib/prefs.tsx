import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { formatDate } from './observations';
import { FR } from './i18n.fr';

// Display preferences for field and office use: language (EN/FR), text size,
// contrast for bright light, and reduced motion. English strings are the keys,
// so English output is identical to the original interface text.
export type Lang = 'en' | 'fr';
export type TextSize = 1 | 2 | 3;
export interface Prefs { lang: Lang; textSize: TextSize; contrast: boolean; reduceMotion: boolean }
type Vars = Record<string, string | number>;
interface PrefsApi extends Prefs {
  set: (next: Partial<Prefs>) => void;
  reset: () => void;
  t: (en: string, vars?: Vars) => string;
  fd: (date: string, year?: boolean) => string;
  fn: (value: number, digits: number) => string;
}

const KEY = 'floodwatch.display-preferences';
const media = (query: string) => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(query).matches;
const defaults = (): Prefs => ({ lang: 'en', textSize: 1, contrast: media('(prefers-contrast: more)'), reduceMotion: media('(prefers-reduced-motion: reduce)') });

function load(): Prefs {
  const base = defaults();
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return base;
    const saved = JSON.parse(raw) as Partial<Prefs>;
    return {
      lang: saved.lang === 'fr' ? 'fr' : 'en',
      textSize: saved.textSize === 2 || saved.textSize === 3 ? saved.textSize : 1,
      contrast: typeof saved.contrast === 'boolean' ? saved.contrast : base.contrast,
      reduceMotion: typeof saved.reduceMotion === 'boolean' ? saved.reduceMotion : base.reduceMotion,
    };
  } catch { return base; }
}

const fill = (text: string, vars?: Vars) => vars ? text.replace(/\{(\w+)\}/g, (match, name: string) => name in vars ? String(vars[name]) : match) : text;

const Ctx = createContext<PrefsApi | null>(null);

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(load);
  useEffect(() => {
    const root = document.documentElement;
    root.lang = prefs.lang;
    root.dataset.textSize = String(prefs.textSize);
    if (prefs.contrast) root.dataset.contrast = 'more'; else delete root.dataset.contrast;
    if (prefs.reduceMotion) root.dataset.motion = 'reduce'; else delete root.dataset.motion;
    document.title = prefs.lang === 'fr' ? 'FloodWatch · Kalari Abdu (FR)' : 'FloodWatch · Kalari Abdu';
    try { window.localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* Storage can be unavailable; preferences still apply for this visit. */ }
  }, [prefs]);
  const set = useCallback((next: Partial<Prefs>) => setPrefs((current) => ({ ...current, ...next })), []);
  const reset = useCallback(() => setPrefs((current) => ({ ...defaults(), lang: current.lang })), []);
  const value = useMemo<PrefsApi>(() => ({
    ...prefs, set, reset,
    t: (en, vars) => fill(prefs.lang === 'fr' ? (FR[en] ?? en) : en, vars),
    fd: (date, year = true) => prefs.lang === 'fr'
      ? new Date(date + 'T00:00:00Z').toLocaleDateString('fr-CA', { day: 'numeric', month: 'short', ...(year ? { year: 'numeric' as const } : {}), timeZone: 'UTC' })
      : formatDate(date, year),
    fn: (value, digits) => prefs.lang === 'fr'
      ? value.toLocaleString('fr-CA', { minimumFractionDigits: digits, maximumFractionDigits: digits })
      : value.toFixed(digits),
  }), [prefs, set, reset]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePrefs(): PrefsApi {
  const value = useContext(Ctx);
  if (!value) throw new Error('usePrefs must be used inside PrefsProvider');
  return value;
}
