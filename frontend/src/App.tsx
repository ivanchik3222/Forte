import "./styles/workspace-polish.css";
import "./styles/model-architecture.css";
import { LanguageSwitcher, LanguageSettings } from "./components/LanguageSwitcher";
import { t, useLocale } from "./i18n";
import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { LandingPage } from "./pages/LandingPage";
import { ApiAccessPage } from "./pages/ApiAccessPage";
import { Icon, IconName } from "./components/Icon";
import { Modal } from "./components/Modal";
import { LoginPanel } from "./components/LoginPanel";
import { MobileNavigation, SidebarAccount, WorkspacePage } from "./components/WorkspaceNavigation";
import { useAuthStore } from "./store/useAuthStore";
import { useAnalysisStore } from "./store/useAnalysisStore";
import { AnalysisDetail } from "./features/analysis/AnalysisDetail";
import { HistoryTable } from "./features/analysis/HistoryTable";
import { UploadPanel } from "./features/analysis/UploadPanel";
import { LiveWorkspace } from "./features/workspace/LiveWorkspace";
import { regulatorySource } from "./data/demo";
import { OverviewPage } from "./pages/OverviewPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { MonitoringPage } from "./pages/MonitoringPage";
import { ShiftPage } from "./pages/ShiftPage";
import { useNotificationStore } from "./store/useNotificationStore";

const navigation: { id: string; label: string; icon: IconName }[] = [
  { id: "overview", label: "Обзор", icon: "grid" },
  { id: "shift", label: "Смена за минуту", icon: "play" },
  { id: "monitoring", label: "Контроль камер", icon: "eye" },
  { id: "notifications", label: "Оповещения", icon: "bell" },
  { id: "history", label: "История проверок", icon: "history" },
  { id: "sources", label: "Нормативная база", icon: "book" },
];

function WorkspaceApp() {
  useLocale();
  const { pathname } = useLocation();
  const routerNavigate = useNavigate();
  const route = pathname === "/workspace" ? "overview" : pathname.slice(1);
  const [modal, setModal] = useState<"help" | "account" | "upload" | null>(
    null,
  );
  const records = useAnalysisStore((state) => state.records);
  const mode = useAnalysisStore((state) => state.settings.mode);
  const user = useAuthStore((state) => state.user);
  const unread = useNotificationStore(
    (state) => state.alerts.filter((alert) => !alert.readAt).length,
  );
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  const navigate = (target: string) => {
    routerNavigate(target === "overview" ? "/workspace" : `/${target}`);
  };
  const open = (id: string) => navigate(`analysis/${id}`);
  const active = route.startsWith("analysis/") ? "history" : route;
  const currentRecord = route.startsWith("analysis/")
    ? records.find((item) => item.id === route.slice(9))
    : undefined;
  const pageName =
    navigation.find((item) => item.id === active)?.label ||
    (active === "settings" ? "Настройки" : "Обзор");
  const name = user?.full_name || user?.nickname || "Рабочее пространство";
  if (pathname === "/api-access") return <ApiAccessPage />;
  if (pathname === "/") return <LandingPage />;
  if (mode === "api" || pathname === "/login") return <LiveWorkspace />;
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >{t("Перейти к содержимому")}</a>
      <aside className="sidebar" aria-label={t("Основная навигация")}>
        <Link className="brand" to="/" aria-label={t("Forte Control — главная")}>
          <img src="/forte-logo.svg" width="112" height="34" alt="Forte" />
          <span className="brand-divider" />
          <span>control</span>
        </Link>
        <div className="workspace-label">
          <span className="workspace-symbol">
            <Icon name="shield" size={18} />
          </span>
          <div>
            <strong>{t("Кассовый контроль")}</strong>
            <span>{t("Рабочее пространство")}</span>
          </div>
        </div>
        <span className="nav-caption">{t("ПЛАТФОРМА")}</span>
        <nav>
          {navigation.map((item) => (
            <Link
              key={item.id}
              to={item.id === "overview" ? "/workspace" : `/${item.id}`}
              className={`nav-item ${active === item.id ? "active" : ""}`}
              aria-current={active === item.id ? "page" : undefined}
            >
              <Icon name={item.icon} size={19} />
              <span>{t(item.label)}</span>
              {item.id === "notifications" && unread > 0 && (
                <span
                  className="nav-count notification-count"
                  aria-label={t("Новых оповещений: {0}", [unread])}
                >
                  {unread}
                </span>
              )}
              {item.id === "history" && (
                <span className="nav-count">{records.length}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <span className="local-card-icon">
              <Icon name="shield" size={20} />
            </span>
            <strong>{t("Внутри вашего контура")}</strong>
            <p>{t("Видео обрабатывается локальным сервисом команды.")}</p>
            <span className="local-tag">
              <span />{t("Без облачных AI-сервисов")}</span>
          </div>
          <Link
            to="/settings"
            className={`nav-item ${active === "settings" ? "active" : ""}`}
            aria-current={active === "settings" ? "page" : undefined}
          >
            <Icon name="settings" size={19} />{t("Настройки")}</Link>
          <button className="nav-item" onClick={() => setModal("help")}>
            <Icon name="help" size={19} />{t("Как это работает")}<Icon name="external" size={14} />
          </button>
          <SidebarAccount onOpen={() => setModal("account")} />
          <div className="sidebar-foot">
            <span>FORTE CONTROL</span>
            <span>Datathon ’26</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <Link
            className="mobile-brand"
            to="/"
            aria-label={t("Forte Control — главная")}
          >
            <img src="/forte-logo.svg" width="76" height="23" alt="Forte" />
            <span>control</span>
          </Link>
          <div className="breadcrumbs">
            <span>{t("Рабочее пространство")}</span>
            <Icon name="chevron" size={12} />
            <strong>{t(pageName)}</strong>
          </div>
          <div className="topbar-actions">
            <LanguageSwitcher />
            <Link to="/settings" className="mode-badge">
              <span />
              {t(mode === "demo" ? "Демо-режим" : "Режим API")}
            </Link>
            <span className="topbar-divider" />
            <button
              className="profile-button workspace-profile-top"
              onClick={() => setModal("account")}
              aria-label={t(user ? "Открыть профиль" : "Войти в аккаунт")}
            >
              <span className="avatar">
                {t(user ? (
                  name.slice(0, 1).toUpperCase()
                ) : (
                  <Icon name="user" size={17} />
                ))}
              </span>
              <span>{t(user ? name : "Проверяющий")}</span>
              <Icon name="down" size={13} />
            </button>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
          <WorkspacePage>
          {route === "overview" && (
            <OverviewPage
              onNew={() => setModal("upload")}
              records={records}
              onOpen={open}
              onHelp={() => setModal("help")}
            />
          )}
          {route === "notifications" && (
            <NotificationsPage onNew={() => setModal("upload")} />
          )}
          {route === "monitoring" && <MonitoringPage />}
          {route === "shift" && <ShiftPage />}
          {route === "history" && (
            <div className="page-enter">
              <div className="page-title-row">
                <div>
                  <p className="eyebrow">{t("РАБОЧЕЕ ПРОСТРАНСТВО")}</p>
                  <h1>{t("История проверок")}</h1>
                  <p>{t("Результаты ручных проверок загруженных видео")}</p>
                </div>
                <button
                  className="button button-primary"
                  onClick={() => setModal("upload")}
                >
                  <Icon name="plus" size={17} />{t("Новая проверка")}</button>
              </div>
              <section className="panel history-panel">
                <HistoryTable records={records} onOpen={open} full />
              </section>
              <div className="page-footnote">
                <Icon name="info" size={15} />{t("История хранится в памяти этой вкладки. После обновления останутся только демо-примеры.")}</div>
            </div>
          )}
          {route === "sources" && <Sources />}
          {route === "settings" && <Settings />}
          {currentRecord && (
            <AnalysisDetail
              key={currentRecord.id}
              record={currentRecord}
              onOpen={open}
              onNew={() => navigate("history")}
            />
          )}
          {![
            "overview",
            "notifications",
            "monitoring",
            "shift",
            "history",
            "sources",
            "settings",
          ].includes(route) &&
            !currentRecord && (
              <div className="panel empty-state">
                <Icon name="search" size={34} />
                <h1>{t("Проверка не найдена")}</h1>
                <p>{t("Возможно, вкладка была обновлена. История загруженных записей хранится только в текущей сессии.")}</p>
                <button
                  className="button button-primary"
                  onClick={() => navigate("overview")}
                >{t("Начать новую проверку")}</button>
              </div>
            )}
          </WorkspacePage>
        </main>
        <footer className="app-footer">
          <span>
            Forte Control <span className="footer-dot">·</span>{t(" Помогаем замечать важное")}</span>
          <span>{t("Прототип для Datathon 2026")}</span>
        </footer>
      </div>
      <MobileNavigation unread={unread} onAccount={() => setModal("account")} />
      {modal === "upload" && (
        <Modal title={t("Новая проверка")} onClose={() => setModal(null)}>
          <div className="new-check-layout">
            <UploadPanel
              onOpen={(id) => {
                setModal(null);
                open(id);
              }}
            />
            <aside className="new-check-guide">
              <span className="eyebrow">{t("ПРОВЕРКА ВИДЕО")}</span>
              <h3>{t("От записи")}<br />{t("к понятному результату")}</h3>
              <ol>
                <li>
                  <span>01</span>
                  <div>
                    <strong>{t("Добавьте файл")}</strong>
                    <p>{t("Запись с камеры в формате MOV, MP4 или WebM.")}</p>
                  </div>
                </li>
                <li>
                  <span>02</span>
                  <div>
                    <strong>{t("Запустите проверку")}</strong>
                    <p>{t("Сервис найдёт моменты, на которые стоит обратить внимание.")}</p>
                  </div>
                </li>
                <li>
                  <span>03</span>
                  <div>
                    <strong>{t("Посмотрите результат")}</strong>
                    <p>{t("События, кадры и объяснение собраны в одном отчёте.")}</p>
                  </div>
                </li>
              </ol>
              <p className="new-check-guide-note">{t("Нужны события с камер за день? Они находятся в разделе «Оповещения».")}</p>
            </aside>
          </div>
        </Modal>
      )}
      {modal === "account" && (
        <Modal title={t("Учётная запись")} onClose={() => setModal(null)}>
          <LoginPanel />
        </Modal>
      )}
      {modal === "help" && (
        <Modal
          title={t("От записи к понятному результату")}
          closeLabel={t("Всё понятно")}
          onClose={() => setModal(null)}
        >
          <div className="help-content">
            <p>{t("Forte Control помогает специалисту проверять визуально наблюдаемые действия при кассовых операциях. События непрерывного наблюдения собраны в «Оповещениях». Для проверки отдельного видео нажмите «Новая проверка».")}</p>
            <ol>
              <li>
                <strong>{t("Загрузите видео.")}</strong>{t(" Обязательный формат — MOV; MP4 и WebM поддерживаются интерфейсом, если их принимает ваш сервер.")}</li>
              <li>
                <strong>{t("Дождитесь обработки.")}</strong>{t(" В режиме API запись отправляется в сервис команды. Лимит ожидания — 5 минут.")}</li>
              <li>
                <strong>{t("Проверьте события.")}</strong>{t(" Откройте таймкод, кадры и источник. Результат сервиса требует оценки человеком.")}</li>
            </ol>
            <div className="notice">
              <Icon name="info" size={18} />
              <span>{t("В демо-режиме анализ не выполняется. Результаты иллюстрируют возможности интерфейса.")}</span>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Sources() {
  useLocale();
  return (
    <div className="page-enter">
      <div className="page-title-row">
        <div>
          <p className="eyebrow">{t("ОБОСНОВАННЫЙ КОНТРОЛЬ")}</p>
          <h1>{t("Нормативная база")}</h1>
          <p>{t("Открытые источники Республики Казахстан для исследования правил")}</p>
        </div>
        <span className="source-count">{t("01 источник")}</span>
      </div>
      <div className="notice">
        <Icon name="info" size={19} />
        <span>{t("Ссылка на документ сама по себе не подтверждает нарушение. Применимый пункт и связь с наблюдаемым событием должны быть указаны в результате анализа.")}</span>
      </div>
      <article className="panel source-card">
        <div className="source-document-icon">
          <Icon name="book" size={31} />
        </div>
        <div className="source-content">
          <div className="source-meta">
            <span>{t("НАЦИОНАЛЬНЫЙ БАНК РК")}</span>
            <span>{t("Официальный источник")}</span>
          </div>
          <h2>{t(regulatorySource.title)}</h2>
          <p>
            {t(regulatorySource.number)}{t(" от ")}{t(regulatorySource.date)}
          </p>
          <div className="source-tags">
            <span>{t("Кассовые операции")}</span>
            <span>{t("Инкассация")}</span>
            <span>{t("Хранение ценностей")}</span>
          </div>
          <a
            className="button button-outline"
            href={regulatorySource.url}
            target="_blank"
            rel="noreferrer"
          >{t("Открыть в «Әділет»")}<Icon name="external" size={16} />
          </a>
        </div>
      </article>
      <div className="source-guidelines">
        <section className="panel">
          <Icon name="eye" size={25} />
          <h2>{t("Только то, что видно")}</h2>
          <p>{t("Вывод должен опираться на действия в кадре. По видео нельзя подтвердить корректность проводки, системной сверки или полномочия человека.")}</p>
        </section>
        <section className="panel">
          <Icon name="book" size={25} />
          <h2>{t("От события к правилу")}</h2>
          <p>{t("Для каждого события интерфейс показывает название документа, пункт и ссылку, если их передал сервис. Отсутствующее обоснование явно отмечается.")}</p>
        </section>
      </div>
      <div className="page-footnote">
        <Icon name="info" size={16} />{t("Перед использованием проверьте актуальную редакцию акта. Демо-категории не являются юридической квалификацией.")}</div>
    </div>
  );
}

function Settings() {
  useLocale();
  const navigate = useNavigate();
  return (
    <div className="page-enter settings-page">
      <h1>{t("Настройки подключения")}</h1>
      <LanguageSettings />
      <section className="panel settings-panel">
        <h2>{t("Демонстрационный режим")}</h2>
        <p>{t("Примеры показывают возможности интерфейса. Файлы остаются в браузере, ИИ-анализ не выполняется.")}</p>
        <button
          className="button button-primary"
          onClick={() => {
            useAnalysisStore
              .getState()
              .setSettings({ mode: "api", apiKey: "" });
            navigate("/workspace");
          }}
        >{t("Открыть рабочий режим")}</button>
        <p>{t("Войдите в аккаунт команды, чтобы сохранять видео и получать историю с сервера.")}</p>
      </section>
    </div>
  );
}

function App() {
  useLocale();
  return (
    <BrowserRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <WorkspaceApp />
    </BrowserRouter>
  );
}

export default App;
