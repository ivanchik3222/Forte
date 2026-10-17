# Interface languages

Supported locales: `kk` (Қазақша), `ru` (Русский, default), `en` (English).
The choice is stored in `localStorage['forte.locale']`, synchronized between tabs,
and applied to `html.lang`, the page title and description. If storage is blocked,
the selection still works for the current session. No translation service or network
request is used. Kazakh glyphs are served from the local Open Sans Cyrillic Extended font.

## Adding copy

Add the Russian source text and its `kk` / `en` translations to `messages.json`.
Call `useLocale()` at the top of a component that renders translated UI, then use
`t('Исходный текст')`. The hook subscribes without remounting components or resetting
forms, filters, uploads, players or dialogs. Shared formatters use `localeCode()`.

Use numbered placeholders for variable text, e.g. `t('Открыть {0}', [fileName])`.
Translations may reorder placeholders. Do not concatenate sentences when word order
could differ. `eventLabel()` / `eventCount()` handle plural forms for all three languages.

The lookup normalizes whitespace only. Unknown source strings are returned unchanged;
there is no partial replacement or guessed translation. API identifiers and payloads
are not localized. ML findings, evidence explanations and normative quotations remain
verbatim on the real analysis page, with a note explaining their source language.
New backend-generated text needs an explicit localized label or an upstream language
contract; this interface change does not make the ML model multilingual.

## Checks

`npm test -- --watchAll=false --runInBand` includes language switching, upload/form
state preservation, history filters, cross-tab preferences, plural forms and placeholder
coverage. `npm run build` verifies TypeScript and produces the deployable frontend.
