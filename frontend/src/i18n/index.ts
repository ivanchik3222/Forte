import { useSyncExternalStore } from 'react';
import messages from './messages.json';

export type Locale = 'kk' | 'ru' | 'en';
export const LANGUAGE_STORAGE_KEY = 'forte.locale';
export const languageNames: Record<Locale, string> = { kk: 'Қазақша', ru: 'Русский', en: 'English' };
const locales: Record<Locale, string> = { kk: 'kk-KZ', ru: 'ru-KZ', en: 'en-GB' };
const catalog: Record<string, { kk: string; en: string }> = Object.assign(Object.create(null), messages);
const listeners = new Set<() => void>();
const isLocale = (value: unknown): value is Locale => value === 'kk' || value === 'ru' || value === 'en';
function readPreference(): Locale {
  try {
    const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (isLocale(saved)) return saved;
  } catch { /* Private browsing may disable storage; switching still works. */ }
  return 'ru';
}
let currentLocale: Locale = readPreference();
export const getLocale = () => currentLocale;
export const localeCode = () => locales[currentLocale];
const normalize = (value: string) => value.replace(/\s+/g, ' ').trim();

/** Translate UI copy only. Unknown strings (including server/model content) pass through. */
export function translate(source: string, locale: Locale, values?: readonly unknown[]): string;
export function translate<T>(source: T, locale: Locale, values?: readonly unknown[]): T;
export function translate<T>(source: T, locale: Locale, values?: readonly unknown[]): T | string {
  if (typeof source !== 'string') return source;
  const entry = catalog[normalize(source)];
  let text: string = locale === 'ru' || !entry ? source : entry[locale];
  if (locale !== 'ru' && entry) {
    text = (source.match(/^\s+/)?.[0] || '') + text + (source.match(/\s+$/)?.[0] || '');
  }
  if (values) text = text.replace(/\{(\d+)\}/g, (match, index) =>
    Number(index) < values.length ? String(translate(values[Number(index)] ?? '', locale)) : match);
  return text;
}
export function t(source: string, values?: readonly unknown[]): string;
export function t<T>(source: T, values?: readonly unknown[]): T;
export function t<T>(source: T, values?: readonly unknown[]): T | string {
  return translate(source, currentLocale, values);
}

function updateDocument() {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = currentLocale;
  document.title = t('Forte Control — контроль кассовых операций');
  document.querySelector('meta[name="description"]')?.setAttribute('content',
    t('Forte Control — проверка кассовых операций по видео. События, таймкоды и доказательства в одном рабочем пространстве.'));
}
export function setLocale(locale: Locale) {
  if (!isLocale(locale)) return;
  currentLocale = locale;
  try { window.localStorage.setItem(LANGUAGE_STORAGE_KEY, locale); } catch { /* In-memory preference remains usable. */ }
  updateDocument();
  listeners.forEach(listener => listener());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function useLocale(): Locale {
  return useSyncExternalStore(subscribe, getLocale, () => 'ru');
}
if (typeof window !== 'undefined') {
  window.addEventListener('storage', event => {
    if (event.key !== LANGUAGE_STORAGE_KEY && event.key !== null) return;
    currentLocale = isLocale(event.newValue) ? event.newValue : 'ru';
    updateDocument();
    listeners.forEach(listener => listener());
  });
}
updateDocument();

export function eventLabel(count: number): string {
  if (currentLocale === 'kk') return 'оқиға';
  const category = new Intl.PluralRules(currentLocale).select(count);
  return currentLocale === 'en' ? (category === 'one' ? 'event' : 'events')
    : category === 'one' ? 'событие' : category === 'few' ? 'события' : 'событий';
}
export function eventCount(count: number): string {
  return `${count.toLocaleString(localeCode())} ${eventLabel(count)}`;
}

const kazakhMonths = ['қаңтар', 'ақпан', 'наурыз', 'сәуір', 'мамыр', 'маусым', 'шілде', 'тамыз', 'қыркүйек', 'қазан', 'қараша', 'желтоқсан'];
const kazakhWeekdays = ['жексенбі', 'дүйсенбі', 'сейсенбі', 'сәрсенбі', 'бейсенбі', 'жұма', 'сенбі'];
/** Some browsers advertise kk support but only supply placeholder months (M01…M12). */
export function formatDate(value: Date | string | number, options: Intl.DateTimeFormatOptions): string {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return '—';
  const settings = { timeZone: 'Asia/Almaty', ...options };
  if (currentLocale !== 'kk') return new Intl.DateTimeFormat(localeCode(), settings).format(date);
  const parts = new Intl.DateTimeFormat('en-GB', settings).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find(p => p.type === type)?.value;
  const day = part('day'), month = part('month'), year = part('year');
  let dayText = '';
  if (month) {
    const monthIndex = Number(new Intl.DateTimeFormat('en-GB', { timeZone: settings.timeZone, month: 'numeric' }).format(date)) - 1;
    const textual = options.month === 'short' || options.month === 'long' || options.month === 'narrow'
      || ['medium', 'long', 'full'].includes(options.dateStyle || '');
    dayText = textual
      ? [day, kazakhMonths[monthIndex], year].filter(Boolean).join(' ')
      : [day, month, year].filter(Boolean).join('.');
  } else dayText = [day, year].filter(Boolean).join(' ');
  if (part('weekday')) {
    const weekday = new Intl.DateTimeFormat('en-US', { timeZone: settings.timeZone, weekday: 'short' }).format(date);
    const index = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(weekday);
    dayText = [kazakhWeekdays[index], dayText].filter(Boolean).join(', ');
  }
  const clock = [part('hour'), part('minute'), part('second')].filter(v => v !== undefined).join(':');
  return [dayText, clock].filter(Boolean).join(', ');
}
