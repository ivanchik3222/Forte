import { ReactNode } from "react";
import { t, useLocale } from "../i18n";
import registry from "../data/regulations.json";
import { regulatoryNotes } from "../data/regulatoryNotes";
import { Icon } from "./Icon";
import "../styles/regulatory-guide.css";

export function RegulatoryGuide({ children }: { children?: ReactNode }) {
  useLocale();
  const enabled = registry.rules.filter(rule => rule.auto_enabled);
  const manual = registry.rules.filter(rule => !rule.auto_enabled);
  return <div className="regulatory-guide">
    <div className="page-title-row"><div>
      <p className="eyebrow">{t("ОТ НАБЛЮДЕНИЯ К ОСНОВАНИЮ")}</p>
      <h1>{t("Нормативная база")}</h1>
      <p>{t("Какие нормы использует проект, что проверяется по видео и где требуется решение специалиста.")}</p>
    </div></div>
    <div className="regulatory-overview" aria-label={t("Состав нормативной базы")}>
      <div><strong>01</strong><span>{t("основной нормативный акт")}</span></div>
      <div><strong>{String(enabled.length).padStart(2, "0")}</strong><span>{t("сценариев в реестре проверки")}</span></div>
      <div><strong>{String(manual.length).padStart(2, "0")}</strong><span>{t("сценария только для ручной проверки")}</span></div>
    </div>
    <article className="panel regulatory-source" aria-labelledby="regulatory-source-title">
      <div className="regulatory-source-top"><span className="regulatory-book"><Icon name="book" size={27} /></span><div>
        <p className="eyebrow">{t("НАЦИОНАЛЬНЫЙ БАНК РЕСПУБЛИКИ КАЗАХСТАН")}</p>
        <h2 id="regulatory-source-title">{t("Постановление № 231")}</h2>
        <p>{t("29 ноября 2019 · государственная регистрация № 19680")}</p>
      </div><span className="regulatory-source-label">{t("Основа реестра")}</span></div>
      <h3>{t("Правила осуществления кассовых операций и операций по инкассации банкнот, монет и ценностей")}</h3>
      <p>{t("Открытый нормативный акт НБРК устанавливает требования к кассовым операциям, хранению наличных и инкассации, в том числе в банках второго уровня. Для проекта выбраны нормы, отдельные признаки соблюдения которых можно сопоставить с изображением.")}</p>
      <div className="regulatory-source-links">
        <a className="button button-primary" href={registry.source.url} target="_blank" rel="noreferrer">{t("Открыть в «Әділет»")}<Icon name="external" size={16} /></a>
        <a className="button button-outline" href={registry.source.snapshot_url} target="_blank" rel="noreferrer">{t("Экспорт ЭКБ · PDF")}<Icon name="download" size={16} /></a>
      </div>
      <dl className="regulatory-version"><div><dt>{t("Редакция в проекте")}</dt><dd>{registry.source.revision}</dd></div><div><dt>{t("Версия реестра")}</dt><dd>{registry.version}</dd></div><div><dt>{t("Снимок получен")}</dt><dd>{registry.source.retrieved_on}</dd></div></dl>
      <p className="regulatory-version-note"><Icon name="info" size={17} />{t("Это редакция, закреплённая в проекте. Последующие изменения акта полностью не сверены; перед применением нужно проверить действующую редакцию и дату операции.")}</p>
      <details className="regulatory-provenance"><summary>{t("Как можно проверить источник")}<Icon name="plus" size={16} /></summary><div>
        <p>{t("В проекте сохранены полный PDF и извлечённый текст. Перед проверкой правил сервер сверяет контрольную сумму PDF. Она подтверждает неизменность файла, но не юридическую актуальность и не подлинность электронной подписи.")}</p>
        <code>SHA-256: {registry.source.snapshot_sha256}</code>
        <p>{t("При первоначальном скачивании снимка цепочка TLS-сертификата государственного сервера не проверялась. Проверка электронной подписи ЭКБ отдельно не проводилась; источник можно независимо сверить по официальным ссылкам выше.")}</p>
      </div></details>
    </article>
    <section className="regulatory-method" aria-labelledby="regulatory-method-title">
      <div className="regulatory-section-heading"><p className="eyebrow">{t("ПРИНЦИП СОПОСТАВЛЕНИЯ")}</p><h2 id="regulatory-method-title">{t("Норма → условия → кадр → вывод")}</h2><p>{t("Наличие ссылки на закон недостаточно. Для каждого вывода нужна проверяемая связь с конкретным действием.")}</p></div>
      <ol>
        <li><span>01</span><h3>{t("Выбираем применимую норму")}</h3><p>{t("Название документа, пункт и ссылка берутся из фиксированного реестра. Модель не может придумать нормативное основание.")}</p></li>
        <li><span>02</span><h3>{t("Проверяем видимые условия")}</h3><p>{t("Модель должна объяснить каждое обязательное условие и исключить альтернативные объяснения. Неясный предмет, роль или граница операции не считаются установленным фактом.")}</p></li>
        <li><span>03</span><h3>{t("Прикладываем доказательства")}</h3><p>{t("К событию привязываются таймкод и 1–3 исходных кадра с объяснением. Сервер проверяет структуру ответа и ссылки на кадры; правильность понимания сцены оценивает человек.")}</p></li>
      </ol>
    </section>
    <section aria-labelledby="enabled-rules-title">
      <div className="regulatory-section-heading"><p className="eyebrow">{t("ВКЛЮЧЕНЫ В РЕЕСТР МОДЕЛИ")}</p><h2 id="enabled-rules-title">{t("Какие признаки проверяем")}</h2><p>{t("Ниже — пересказ норм и наша визуальная трактовка, а не цитаты закона. Эти сценарии используются при включённом этапе нормативной оценки; наличие их в интерфейсе не означает, что полная модель уже развёрнута на сервере.")}</p></div>
      <div className="regulatory-rules">{enabled.map(rule => {
        const note = regulatoryNotes[rule.id];
        return <article className="panel regulatory-rule" key={rule.id} id={`rule-${rule.id}`}>
          <div className="regulatory-rule-meta"><span>{t("Пункт {0}", [rule.section])}</span><Icon name="scan" size={18} /></div>
          <h3>{t(rule.title)}</h3><p className="regulatory-basis">{t(rule.basis)}</p>
          <details><summary>{t("Что ищем в кадре и что исключаем")}<Icon name="plus" size={17} /></summary><div className="regulatory-rule-details">
            <h4><Icon name="eye" size={16} />{t("Нужны видимые признаки")}</h4><p>{t(note.observed)}</p>
            <h4><Icon name="shield" size={16} />{t("Когда вывод недопустим")}</h4><p>{t(note.exclusions)}</p>
            {note.interpretation && <p className="regulatory-interpretation">{t(note.interpretation)}</p>}
            <a href={registry.source.url} target="_blank" rel="noreferrer">{t("Источник: № 231, пункт {0}", [rule.section])}<Icon name="external" size={13} /></a>
          </div></details>
        </article>;
      })}</div>
    </section>
    <section className="panel regulatory-manual" aria-labelledby="manual-rules-title">
      <div className="regulatory-section-heading"><p className="eyebrow">{t("АВТОМАТИЧЕСКИЙ ВЫВОД ОТКЛЮЧЁН")}</p><h2 id="manual-rules-title">{t("Что нельзя установить по одному видео")}</h2><p>{t("Эти нормы исследованы и сохранены в реестре, но не используются для автоматического вывода о нарушении.")}</p></div>
      {manual.map(rule => <details key={rule.id} className="regulatory-manual-rule"><summary><span><small>{t("Пункт {0}", [rule.section])}</small><strong>{t(rule.title)}</strong></span><Icon name="plus" size={18} /></summary><div>
        <p>{t(rule.basis)}</p><p><strong>{t("Почему отключено:")}</strong> {t(regulatoryNotes[rule.id].exclusions)}</p>
      </div></details>)}
    </section>
    <section className="regulatory-boundaries" aria-labelledby="regulatory-boundaries-title">
      <Icon name="shield" size={25} /><div><h2 id="regulatory-boundaries-title">{t("Граница результата")}</h2><p>{t("Сервис выделяет признаки возможного процедурного нарушения. Он не устанавливает кражу, виновность, намерения человека, полномочия работников или корректность бухгалтерских проводок. Сигнал классификатора без подтверждённого правила остаётся эпизодом для ручной проверки.")}</p><p>{t("Полный внутренний регламент ForteBank не предоставлен по условиям кейса. Мы не подменяем его догадками. Итог требует просмотра исходной записи, применимого пункта и контекста специалистом.")}</p></div>
    </section>
    <details className="regulatory-research"><summary>{t("Что ещё исследовали")}<Icon name="plus" size={17} /></summary><p>{t("Постановление НБРК № 14 от 24.02.2020 изучалось как источник требований к устройству и охране помещений. Оно не входит в действующий реестр автоматической оценки. Открытая дверь сама по себе не доказывает нарушение требований к оборудованию помещения.")}</p><a href="https://adilet.zan.kz/rus/docs/V2000020075" target="_blank" rel="noreferrer">{t("Открыть постановление № 14")}<Icon name="external" size={14} /></a></details>
    {children}
  </div>;
}
