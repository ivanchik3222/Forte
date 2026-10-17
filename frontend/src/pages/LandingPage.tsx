import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { t, useLocale } from "../i18n";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAnalysisStore } from "../store/useAnalysisStore";
import { Icon } from "../components/Icon";
import { MAX_FILE_SIZE_LABEL } from "../features/analysis/types";

const capabilities = [
  {
    art: "moment",
    title: "Точный момент",
    text: "Сразу к важному фрагменту. Каждое событие отмечено таймкодом.",
    color: "pink",
  },
  {
    art: "evidence",
    title: "Наглядный результат",
    text: "Кадры и объяснение рядом. Видно, на чём основан вывод.",
    color: "blue",
  },
  {
    art: "rules",
    title: "Связь с правилом",
    text: "Нормативный источник и наблюдаемое действие в одном результате.",
    color: "lilac",
  },
];

function ProductArt({
  name,
  className = "",
}: {
  name: string;
  className?: string;
}) {
  useLocale();
  return (
    <img
      className={className}
      src={`/images/${name}-960.webp`}
      srcSet={`/images/${name}-480.webp 480w, /images/${name}-960.webp 960w`}
      sizes={
        name === "review"
          ? "(max-width: 700px) 90vw, 550px"
          : "(max-width: 700px) 90vw, (max-width: 1150px) 33vw, 450px"
      }
      alt=""
      width="960"
      height="960"
      loading="lazy"
      decoding="async"
    />
  );
}

const questions = () => [
  {
    question: "Что именно проверяет сервис?",
    answer:
      "Визуально наблюдаемые действия на записи кассовой операции. Сервис помогает найти признаки возможных нарушений, показывает время события, кадры и объяснение. Он не проверяет бухгалтерские проводки, внутренние журналы или другие данные за пределами видео.",
  },
  {
    question: "Можно попробовать без подключения модели?",
    answer:
      "Да. В демонстрационном кабинете доступны загрузка, пример обработки и два результата: с событиями и без них. Демо-ответы заданы заранее, не связаны с содержимым вашего видео и явно помечены. Для настоящего анализа команда подключает свой локальный сервис.",
  },
  {
    question: "Какие видео можно загрузить?",
    answer: t("Интерфейс принимает MOV, MP4 и WebM до {0}. Основной формат кейса — MOV. Поддержка дополнительных форматов зависит от подключённого сервера. Если кодек не воспроизводится в браузере, исходный MOV всё равно можно отправить на анализ.", [MAX_FILE_SIZE_LABEL]),
  },
  {
    question: "Видео передаётся в облачные AI-сервисы?",
    answer:
      "Нет. В демо-режиме файл остаётся в браузере. В режиме API он отправляется только на настроенный сервер команды. По условиям кейса модели должны работать локально, без внешних AI-сервисов. Развёртывание и сетевой контур настраивает команда.",
  },
  {
    question: "Результат подтверждает нарушение?",
    answer:
      "Результат — подсказка специалисту, а не окончательное юридическое или дисциплинарное заключение. Проверяющий изучает видео, обоснование и применимое правило. Сервис не идентифицирует людей по лицам.",
  },
];

export function LandingPage() {
  useLocale();
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="landing-page">
      <a className="skip-link" href="#landing-main">{t("Перейти к содержимому")}</a>
      <header className="landing-header">
        <div className="landing-container landing-nav">
          <Link
            className="brand landing-brand"
            to="/"
            aria-label={t("Forte Control — главная")}
          >
            <img src="/forte-logo.svg" alt="Forte" width="112" height="34" />
            <span className="brand-divider" />
            <span>control</span>
          </Link>
          <nav
            className={`landing-links ${menuOpen ? "is-open" : ""}`}
            aria-label={t("Навигация по проекту")}
          >
            <a href="#capabilities" onClick={() => setMenuOpen(false)}>{t("Возможности")}</a>
            <a href="#workflow" onClick={() => setMenuOpen(false)}>{t("Как работает")}</a>
            <a href="#security" onClick={() => setMenuOpen(false)}>{t("Безопасность")}</a>
            <a href="#questions" onClick={() => setMenuOpen(false)}>{t("Вопросы")}</a>
            <Link to="/api-access" onClick={() => setMenuOpen(false)}>API</Link>
          </nav>
          <LanguageSwitcher />
          <Link to="/workspace" className="button button-primary landing-login">{t("Открыть кабинет")}<Icon name="arrow" size={17} />
          </Link>
          <button
            className="icon-button landing-menu"
            aria-label={t(menuOpen ? "Закрыть меню" : "Открыть меню")}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(!menuOpen)}
          >
            <Icon name={menuOpen ? "close" : "menu"} />
          </button>
        </div>
      </header>
      <main id="landing-main">
        <section className="landing-hero">
          <div className="landing-container landing-hero-inner">
            <div className="landing-hero-art">
              <img
                src="/images/forte-control-hero.jpg"
                alt={t("Скульптурный объектив из стекла и металла в бордовой палитре Forte")}
                width="1536"
                height="1024"
                fetchPriority="high"
              />
            </div>
            <div className="landing-hero-copy">
              <span className="landing-kicker">
                <span />{t("ВИДЕОКОНТРОЛЬ КАССОВЫХ ОПЕРАЦИЙ")}</span>
              <h1>{t("Всё важное.")}<br />
                <span>{t("В поле зрения.")}</span>
              </h1>
              <p>{t("Превращаем видеозапись в понятный результат: событие, точный момент и доказательство. Чтобы ваше внимание оставалось на главном.")}</p>
              <div className="landing-hero-actions">
                <Link to="/workspace" className="button button-primary">{t("Начать проверку")}<Icon name="arrow" size={18} />
                </Link>
                <Link
                  to="/analysis/demo-001"
                  className="landing-demo-button"
                  onClick={() =>
                    useAnalysisStore
                      .getState()
                      .setSettings({ mode: "demo", apiKey: "" })
                  }
                >
                  <span>
                    <Icon name="play" size={14} />
                  </span>{t("Посмотреть демо")}</Link>
              </div>
              <div className="landing-hero-note">
                <Icon name="shield" size={15} />
                <span>{t("Локальная обработка. Решение — за человеком.")}</span>
              </div>
            </div>
            <div className="hero-bottom-caption">
              <span>FORTE CONTROL</span>
              <span>{t("Технология внимательного контроля")}</span>
              <span>DATATHON 2026</span>
            </div>
          </div>
        </section>
        <section
          className="landing-principles landing-container"
          aria-label={t("Принципы проекта")}
        >
          <div>
            <Icon name="server" size={23} />
            <span>
              <strong>{t("Внутри вашего контура")}</strong>
              <small>{t("Без облачных AI-сервисов")}</small>
            </span>
          </div>
          <div>
            <Icon name="scan" size={23} />
            <span>
              <strong>{t("Проверяемый результат")}</strong>
              <small>{t("От события до кадра и источника")}</small>
            </span>
          </div>
          <div>
            <Icon name="user" size={23} />
            <span>
              <strong>{t("Человек принимает решение")}</strong>
              <small>{t("Технология помогает заметить")}</small>
            </span>
          </div>
        </section>
        <section
          className="landing-section landing-container"
          id="capabilities"
        >
          <div className="landing-section-intro">
            <div>
              <p className="landing-eyebrow">{t("01 / ВОЗМОЖНОСТИ")}</p>
              <h2>{t("Меньше просмотра.")}<br />
                <span>{t("Больше ясности.")}</span>
              </h2>
            </div>
            <p>{t("В полной записи легко упустить важную деталь. Forte Control помогает перейти от долгого поиска к конкретным фрагментам, которые стоит проверить.")}</p>
          </div>
          <div className="capability-grid">
            {capabilities.map((item) => (
              <article
                key={item.title}
                className={`capability-card capability-${item.color}`}
              >
                <div className="capability-copy">
                  <h3>{t(item.title)}</h3>
                  <p>{t(item.text)}</p>
                </div>
                <ProductArt name={item.art} className="capability-art" />
              </article>
            ))}
          </div>
        </section>
        <section className="landing-showcase landing-container">
          <div className="showcase-copy">
            <p className="landing-eyebrow">{t("ДЕТАЛИ СКЛАДЫВАЮТСЯ В КАРТИНУ")}</p>
            <h2>{t("Каждый вывод")}<br />{t("можно проверить.")}</h2>
            <p>{t("Важен не только сигнал, но и то, что за ним стоит. Изучите момент на записи, посмотрите кадры и проверьте связь с правилом.")}</p>
            <div className="showcase-points">
              <span>{t("Событие")}</span>
              <span>{t("Кадр")}</span>
              <span>{t("Обоснование")}</span>
            </div>
            <Link
              to="/analysis/demo-001"
              className="button button-primary"
              onClick={() =>
                useAnalysisStore
                  .getState()
                  .setSettings({ mode: "demo", apiKey: "" })
              }
            >{t("Открыть пример проверки")}<Icon name="arrow" size={18} />
            </Link>
            <span className="showcase-demo-note">{t("Демонстрационный отчёт · без загрузки видео")}</span>
          </div>
          <div className="showcase-art">
            <ProductArt name="review" />
            <span className="showcase-timecode">
              <Icon name="play" size={15} />
              <strong>00:18</strong>
              <span>{t("Пример таймкода")}</span>
            </span>
          </div>
        </section>
        <section className="landing-section landing-container" id="workflow">
          <div className="landing-section-intro">
            <div>
              <p className="landing-eyebrow">{t("02 / КАК ЭТО РАБОТАЕТ")}</p>
              <h2>{t("От записи к ответу.")}<br />
                <span>{t("Три простых шага.")}</span>
              </h2>
            </div>
            <Link to="/workspace" className="button button-outline">{t("Попробовать сервис")}<Icon name="arrow" size={17} />
            </Link>
          </div>
          <div className="workflow-grid">
            {[
              {
                title: "Загрузите видео",
                text: "Выберите запись с компьютера или перетащите файл в окно проверки. Основной формат — MOV.",
                detail: "MOV · MP4 · WebM",
              },
              {
                title: "Запустите проверку",
                text: "Следите за статусом обработки. Локальный сервис анализирует визуально наблюдаемые действия.",
                detail: "Статус в реальном времени",
              },
              {
                title: "Изучите события",
                text: "Посмотрите фрагменты, кадры и правила. Сохраните результат проверки в JSON для дальнейшей работы.",
                detail: "Таймкод · Кадр · Источник",
              },
            ].map((step, index) => (
              <article key={step.title}>
                <div className="workflow-number">
                  <span>0{index + 1}</span>
                  {index < 2 && <Icon name="arrow" size={23} />}
                </div>
                <h3>{t(step.title)}</h3>
                <p>{t(step.text)}</p>
                <span className="workflow-detail">{t(step.detail)}</span>
              </article>
            ))}
          </div>
        </section>
        <section className="landing-security" id="security">
          <div className="landing-container security-inner">
            <div>
              <p className="landing-eyebrow">{t("03 / ДОВЕРИЕ И БЕЗОПАСНОСТЬ")}</p>
              <h2>{t("Ваши записи.")}<br />
                <span>{t("Ваш контур.")}</span>
              </h2>
              <p>{t("Контроль не должен создавать новые риски. Проект рассчитан на локальную обработку видео внутри инфраструктуры команды или банка.")}</p>
              <span className="security-signature">
                <Icon name="shield" size={21} />{t("Продумано для банковского контекста")}</span>
            </div>
            <div className="security-list">
              {[
                {
                  title: "Без внешних AI-сервисов",
                  text: "Обработка на локально развёрнутых моделях. Видео, кадры и их описания не передаются облачным AI-провайдерам.",
                },
                {
                  title: "Без распознавания лиц",
                  text: "В фокусе — наблюдаемые действия. Идентификация людей по лицам не входит в задачу сервиса.",
                },
                {
                  title: "Без категоричных обвинений",
                  text: "Сервис отмечает признаки возможного нарушения. Специалист проверяет контекст и принимает решение.",
                },
              ].map((item) => (
                <div key={item.title}>
                  <span>
                    <Icon name="check" size={18} />
                  </span>
                  <div>
                    <h3>{t(item.title)}</h3>
                    <p>{t(item.text)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
        <section
          className="landing-section landing-container landing-faq"
          id="questions"
        >
          <div>
            <p className="landing-eyebrow">{t("04 / ВОПРОСЫ И ОТВЕТЫ")}</p>
            <h2>{t("Важные детали.")}<br />
              <span>{t("Без мелкого шрифта.")}</span>
            </h2>
            <p>{t("Что умеет сервис и где проходят границы его возможностей.")}</p>
          </div>
          <div className="faq-list">
            {questions().map((item) => (
              <details key={item.question}>
                <summary>
                  {t(item.question)}
                  <Icon name="plus" size={19} />
                </summary>
                <p>{t(item.answer)}</p>
              </details>
            ))}
          </div>
        </section>
        <section className="landing-container landing-cta">
          <div className="landing-cta-copy">
            <p className="landing-eyebrow">{t("ПОСМОТРИТЕ НА ЗАПИСЬ ПО-НОВОМУ")}</p>
            <h2>{t("Важное начинается")}<br />{t("с вашего внимания.")}</h2>
            <p>{t("Откройте рабочее пространство и попробуйте первую проверку.")}</p>
            <Link to="/workspace" className="button button-primary">{t("Перейти к проверке")}<Icon name="arrow" size={20} />
            </Link>
          </div>
          <div className="landing-cta-art" aria-hidden="true" />
        </section>
      </main>
      <footer className="landing-footer landing-container">
        <div>
          <Link
            className="brand landing-brand"
            to="/"
            aria-label={t("Forte Control — главная")}
          >
            <img src="/forte-logo.svg" alt="Forte" width="112" height="34" />
            <span className="brand-divider" />
            <span>control</span>
          </Link>
          <p>{t("Технология внимательного контроля.")}</p>
        </div>
        <div>
          <span>{t("Проект для кейса ForteBank · Datathon 2026")}</span>
          <p>{t("Демонстрационный прототип. Не официальный банковский продукт.")}</p>
        </div>
        <a href="https://forte.kz" target="_blank" rel="noreferrer">{t("О ForteBank")}<Icon name="external" size={14} />
        </a>
      </footer>
    </div>
  );
}
