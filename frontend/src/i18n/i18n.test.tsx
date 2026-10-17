import { act, fireEvent, render, screen } from '@testing-library/react';
import App from '../App';
import { createDemoRecords } from '../data/demo';
import { useAnalysisStore } from '../store/useAnalysisStore';
import { useAuthStore } from '../store/useAuthStore';
import { eventCount, formatDate, getLocale, LANGUAGE_STORAGE_KEY, localeCode, setLocale, t, translate } from './index';
import messages from './messages.json';
import { fileSize, MAX_FILE_SIZE } from '../features/analysis/types';

beforeEach(() => {
  setLocale('ru');
  window.scrollTo = jest.fn();
  window.history.replaceState(null, '', '/');
  useAuthStore.setState({ initialized: true, user: null, status: 'idle', error: null });
  useAnalysisStore.setState({ records: createDemoRecords(), settings: { mode: 'demo', apiKey: '' } });
});
afterEach(() => act(() => setLocale('ru')));
function choose(locale: string) {
  fireEvent.change(screen.getAllByRole('combobox', { name: /Язык интерфейса|Interface language|Интерфейс тілі/ })[0], { target: { value: locale } });
}

test('switches landing and FAQ across all languages, persists preference and updates page language', () => {
  const view = render(<App />);
  choose('kk');
  expect(screen.getByRole('heading', { name: /Маңыздының бәрі.*Назарда/ })).toBeInTheDocument();
  expect(screen.getByText('Қандай бейнелерді жүктеуге болады?')).toBeInTheDocument();
  expect(document.documentElement.lang).toBe('kk');
  expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('kk');
  choose('en');
  expect(screen.getByRole('heading', { name: /Everything that matters.*In focus/ })).toBeInTheDocument();
  expect(screen.getByText(/Upload MOV, MP4 or WebM files up to 1 GB/)).toBeInTheDocument();
  expect(document.title).toBe('Forte Control — cash operation oversight');
  view.unmount();
  render(<App />);
  expect(screen.getByRole('link', { name: 'Start a review' })).toBeInTheDocument();
  choose('ru');
  expect(screen.getByRole('link', { name: 'Начать проверку' })).toBeInTheDocument();
});

test('the merged API route remains reachable from the translated landing page', () => {
  render(<App />);
  choose('en');
  fireEvent.click(screen.getByRole('link', { name: 'API' }));
  expect(window.location.pathname).toBe('/api-access');
  expect(screen.getByRole('heading', { name: 'API без регистрации' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('link', { name: /Forte Control/ }));
  expect(window.location.pathname).toBe('/');
  expect(screen.getByRole('link', { name: 'Start a review' })).toBeInTheDocument();
  expect(getLocale()).toBe('en');
});

test('language changes preserve selected upload and open sheet', () => {
  window.history.replaceState(null, '', '/workspace');
  render(<App />);
  choose('en');
  fireEvent.click(screen.getByRole('button', { name: 'New review' }));
  const input = screen.getByLabelText('Choose a video file');
  const file = new File(['video'], 'test.mov', { type: 'video/quicktime' });
  fireEvent.change(input, { target: { files: [file] } });
  expect(screen.getByText('test.mov')).toBeInTheDocument();
  act(() => setLocale('kk'));
  expect(screen.getByRole('dialog', { name: 'Жаңа тексеру' })).toBeInTheDocument();
  expect(screen.getByText('test.mov')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Демоны бастау' })).toBeEnabled();
  expect(screen.getByLabelText('Бейнефайл таңдау')).toBe(input);
});

test('switching preserves history filters and translates empty states', () => {
  window.history.replaceState(null, '', '/history');
  render(<App />);
  fireEvent.change(screen.getByRole('textbox', { name: 'Поиск по имени файла' }), { target: { value: 'not-present' } });
  choose('en');
  expect(screen.getByRole('textbox', { name: 'Search by file name' })).toHaveValue('not-present');
  expect(screen.getByRole('heading', { name: 'No reviews found' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Reset filters' }));
  expect(screen.getByText('cash_desk_01.mov')).toBeInTheDocument();
});

test('localizes counts, size limits and parameters without changing unknown source content', () => {
  setLocale('en');
  expect(eventCount(1)).toBe('1 event');
  expect(eventCount(21)).toBe('21 events');
  expect(fileSize(MAX_FILE_SIZE)).toBe('1 GB');
  expect(t('Выделено эпизодов: {0}. Ниже — основания каждого вывода.', [2])).toBe('Episodes identified: 2. Supporting evidence for each is below.');
  expect(t('Кассир уходит, клиент остаётся.')).toBe('Кассир уходит, клиент остаётся.');
  expect(t('__proto__')).toBe('__proto__');
  expect(t('constructor')).toBe('constructor');
  setLocale('kk');
  expect(eventCount(5)).toBe('5 оқиға');
  expect(localeCode()).toBe('kk-KZ');
  setLocale('ru');
  expect(eventCount(21)).toBe('21 событие');
  expect(eventCount(22)).toBe('22 события');
  expect(eventCount(25)).toBe('25 событий');
});

test('syncs other tabs and tolerates storage being unavailable', () => {
  render(<App />);
  act(() => window.dispatchEvent(new StorageEvent('storage', { key: LANGUAGE_STORAGE_KEY, newValue: 'kk' })));
  expect(getLocale()).toBe('kk');
  expect(screen.getByRole('link', { name: 'Тексеруді бастау' })).toBeInTheDocument();
  const save = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('disabled'); });
  choose('en');
  expect(getLocale()).toBe('en');
  expect(document.documentElement.lang).toBe('en');
  save.mockRestore();
});

test('every message has both translations and retains every placeholder', () => {
  const params = (value: string) => (value.match(/\{\d+\}/g) || []).sort();
  for (const [ru, translations] of Object.entries(messages)) {
    for (const locale of ['kk', 'en'] as const) {
      expect(translations[locale].trim()).not.toBe('');
      expect(params(translations[locale])).toEqual(params(ru));
      expect(translate(ru, locale)).toBe(translations[locale]);
    }
  }
});


test('Kazakh dates use real month names and the Astana calendar day', () => {
  setLocale('kk');
  expect(formatDate('2026-10-17T20:30:00Z', { year: 'numeric', month: 'long', day: 'numeric' })).toBe('18 қазан 2026');
  expect(formatDate('2026-10-17T20:30:00Z', { dateStyle: 'medium', timeStyle: 'short' })).toBe('18 қазан 2026, 01:30');
});
