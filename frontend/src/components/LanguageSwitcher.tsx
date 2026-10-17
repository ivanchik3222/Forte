import { languageNames, Locale, setLocale, t, useLocale } from '../i18n';

export function LanguageSwitcher({ expanded = false }: { expanded?: boolean }) {
  const locale = useLocale();
  return (
    <label className={`language-switcher${expanded ? ' language-switcher-expanded' : ''}`}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" />
        <path d="M3 12h18M5 6.5h14M5 17.5h14" />
      </svg>
      {expanded && <span>{t('Язык интерфейса')}</span>}
      <select aria-label={t('Язык интерфейса')} value={locale} onChange={event => setLocale(event.target.value as Locale)}>
        {(['kk', 'ru', 'en'] as const).map(code => <option key={code} value={code} lang={code}>{languageNames[code]}</option>)}
      </select>
      {!expanded && <span className="language-code" aria-hidden="true">{locale === 'kk' ? 'ҚАЗ' : locale === 'ru' ? 'РУС' : 'ENG'}</span>}
      <svg className="language-chevron" width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m3 4.5 3 3 3-3" /></svg>
    </label>
  );
}

export function LanguageSettings() {
  useLocale();
  return <section className="panel language-settings">
    <LanguageSwitcher expanded />
    <p>{t('Язык сохраняется на этом устройстве.')}</p>
  </section>;
}
