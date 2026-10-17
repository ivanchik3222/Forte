import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { LandingPage } from "./pages/LandingPage";
import { Icon, IconName } from "./components/Icon";
import { Modal } from "./components/Modal";
import { LoginPanel } from "./components/LoginPanel";
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

const mobileNavigation: { id: string; label: string; icon: IconName }[] = [
  { id: "overview", label: "Обзор", icon: "grid" },
  { id: "notifications", label: "События", icon: "bell" },
  { id: "history", label: "История", icon: "history" },
  { id: "sources", label: "Правила", icon: "book" },
  { id: "settings", label: "Настройки", icon: "settings" },
];

function WorkspaceApp() {
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
  const mobileActive = ["shift", "monitoring"].includes(active)
    ? "overview"
    : active;
  const currentRecord = route.startsWith("analysis/")
    ? records.find((item) => item.id === route.slice(9))
    : undefined;
  const pageName =
    navigation.find((item) => item.id === active)?.label ||
    (active === "settings" ? "Настройки" : "Обзор");
  const name = user?.full_name || user?.nickname || "Рабочее пространство";
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
      >
        Перейти к содержимому
      </a>
      <aside className="sidebar" aria-label="Основная навигация">
        <Link className="brand" to="/" aria-label="Forte Control — главная">
          <img src="/forte-logo.svg" width="112" height="34" alt="Forte" />
          <span className="brand-divider" />
          <span>control</span>
        </Link>
        <div className="workspace-label">
          <span className="workspace-symbol">
            <Icon name="shield" size={18} />
          </span>
          <div>
            <strong>Кассовый контроль</strong>
            <span>Рабочее пространство</span>
          </div>
        </div>
        <span className="nav-caption">ПЛАТФОРМА</span>
        <nav>
          {navigation.map((item) => (
            <Link
              key={item.id}
              to={item.id === "overview" ? "/workspace" : `/${item.id}`}
              className={`nav-item ${active === item.id ? "active" : ""}`}
              aria-current={active === item.id ? "page" : undefined}
            >
              <Icon name={item.icon} size={19} />
              <span>{item.label}</span>
              {item.id === "notifications" && unread > 0 && (
                <span
                  className="nav-count notification-count"
                  aria-label={`Новых оповещений: ${unread}`}
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
            <strong>Внутри вашего контура</strong>
            <p>Видео обрабатывается локальным сервисом команды.</p>
            <span className="local-tag">
              <span />
              Без облачных AI-сервисов
            </span>
          </div>
          <Link
            to="/settings"
            className={`nav-item ${active === "settings" ? "active" : ""}`}
            aria-current={active === "settings" ? "page" : undefined}
          >
            <Icon name="settings" size={19} />
            Настройки
          </Link>
          <button className="nav-item" onClick={() => setModal("help")}>
            <Icon name="help" size={19} />
            Как это работает
            <Icon name="external" size={14} />
          </button>
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
            aria-label="Forte Control — главная"
          >
            <img src="/forte-logo.svg" width="76" height="23" alt="Forte" />
            <span>control</span>
          </Link>
          <div className="breadcrumbs">
            <span>Рабочее пространство</span>
            <Icon name="chevron" size={12} />
            <strong>{pageName}</strong>
          </div>
          <div className="topbar-actions">
            <Link to="/settings" className="mode-badge">
              <span />
              {mode === "demo" ? "Демо-режим" : "Режим API"}
            </Link>
            <span className="topbar-divider" />
            <button
              className="profile-button"
              onClick={() => setModal("account")}
              aria-label={user ? "Открыть профиль" : "Войти в аккаунт"}
            >
              <span className="avatar">
                {user ? (
                  name.slice(0, 1).toUpperCase()
                ) : (
                  <Icon name="user" size={17} />
                )}
              </span>
              <span>{user ? name : "Проверяющий"}</span>
              <Icon name="down" size={13} />
            </button>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
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
                  <p className="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</p>
                  <h1>История проверок</h1>
                  <p>Результаты ручных проверок загруженных видео</p>
                </div>
                <button
                  className="button button-primary"
                  onClick={() => setModal("upload")}
                >
                  <Icon name="plus" size={17} />
                  Новая проверка
                </button>
              </div>
              <section className="panel history-panel">
                <HistoryTable records={records} onOpen={open} full />
              </section>
              <div className="page-footnote">
                <Icon name="info" size={15} />
                История хранится в памяти этой вкладки. После обновления
                останутся только демо-примеры.
              </div>
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
                <h1>Проверка не найдена</h1>
                <p>
                  Возможно, вкладка была обновлена. История загруженных записей
                  хранится только в текущей сессии.
                </p>
                <button
                  className="button button-primary"
                  onClick={() => navigate("overview")}
                >
                  Начать новую проверку
                </button>
              </div>
            )}
        </main>
        <footer className="app-footer">
          <span>
            Forte Control <span className="footer-dot">·</span> Помогаем
            замечать важное
          </span>
          <span>Прототип для Datathon 2026</span>
        </footer>
      </div>
      <nav className="mobile-bottom-nav" aria-label="Навигация по кабинету">
        {mobileNavigation.map((item) => (
          <Link
            key={item.id}
            to={item.id === "overview" ? "/workspace" : `/${item.id}`}
            className="mobile-tab"
            aria-label={
              item.id === "notifications"
                ? `Оповещения, новых: ${unread}`
                : undefined
            }
            aria-current={mobileActive === item.id ? "page" : undefined}
          >
            <span className="mobile-tab-icon">
              <Icon name={item.icon} size={23} />
              {item.id === "notifications" && unread > 0 && (
                <span className="mobile-notification-count" aria-hidden="true">
                  {unread > 99 ? "99+" : unread}
                </span>
              )}
            </span>
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
      {modal === "upload" && (
        <Modal title="Новая проверка" onClose={() => setModal(null)}>
          <div className="new-check-layout">
            <UploadPanel
              onOpen={(id) => {
                setModal(null);
                open(id);
              }}
            />
            <aside className="new-check-guide">
              <span className="eyebrow">ПРОВЕРКА ВИДЕО</span>
              <h3>
                От записи
                <br />к понятному результату
              </h3>
              <ol>
                <li>
                  <span>01</span>
                  <div>
                    <strong>Добавьте файл</strong>
                    <p>Запись с камеры в формате MOV, MP4 или WebM.</p>
                  </div>
                </li>
                <li>
                  <span>02</span>
                  <div>
                    <strong>Запустите проверку</strong>
                    <p>
                      Сервис найдёт моменты, на которые стоит обратить внимание.
                    </p>
                  </div>
                </li>
                <li>
                  <span>03</span>
                  <div>
                    <strong>Посмотрите результат</strong>
                    <p>События, кадры и объяснение собраны в одном отчёте.</p>
                  </div>
                </li>
              </ol>
              <p className="new-check-guide-note">
                Нужны события с камер за день? Они находятся в разделе
                «Оповещения».
              </p>
            </aside>
          </div>
        </Modal>
      )}
      {modal === "account" && (
        <Modal title="Учётная запись" onClose={() => setModal(null)}>
          <LoginPanel />
        </Modal>
      )}
      {modal === "help" && (
        <Modal
          title="От записи к понятному результату"
          closeLabel="Всё понятно"
          onClose={() => setModal(null)}
        >
          <div className="help-content">
            <p>
              Forte Control помогает специалисту проверять визуально наблюдаемые
              действия при кассовых операциях. События непрерывного наблюдения
              собраны в «Оповещениях». Для проверки отдельного видео нажмите
              «Новая проверка».
            </p>
            <ol>
              <li>
                <strong>Загрузите видео.</strong> Обязательный формат — MOV; MP4
                и WebM поддерживаются интерфейсом, если их принимает ваш сервер.
              </li>
              <li>
                <strong>Дождитесь обработки.</strong> В режиме API запись
                отправляется в сервис команды. Лимит ожидания — 5 минут.
              </li>
              <li>
                <strong>Проверьте события.</strong> Откройте таймкод, кадры и
                источник. Результат сервиса требует оценки человеком.
              </li>
            </ol>
            <div className="notice">
              <Icon name="info" size={18} />
              <span>
                В демо-режиме анализ не выполняется. Результаты иллюстрируют
                возможности интерфейса.
              </span>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Sources() {
  return (
    <div className="page-enter">
      <div className="page-title-row">
        <div>
          <p className="eyebrow">ОБОСНОВАННЫЙ КОНТРОЛЬ</p>
          <h1>Нормативная база</h1>
          <p>Открытые источники Республики Казахстан для исследования правил</p>
        </div>
        <span className="source-count">01 источник</span>
      </div>
      <div className="notice">
        <Icon name="info" size={19} />
        <span>
          Ссылка на документ сама по себе не подтверждает нарушение. Применимый
          пункт и связь с наблюдаемым событием должны быть указаны в результате
          анализа.
        </span>
      </div>
      <article className="panel source-card">
        <div className="source-document-icon">
          <Icon name="book" size={31} />
        </div>
        <div className="source-content">
          <div className="source-meta">
            <span>НАЦИОНАЛЬНЫЙ БАНК РК</span>
            <span>Официальный источник</span>
          </div>
          <h2>{regulatorySource.title}</h2>
          <p>
            {regulatorySource.number} от {regulatorySource.date}
          </p>
          <div className="source-tags">
            <span>Кассовые операции</span>
            <span>Инкассация</span>
            <span>Хранение ценностей</span>
          </div>
          <a
            className="button button-outline"
            href={regulatorySource.url}
            target="_blank"
            rel="noreferrer"
          >
            Открыть в «Әділет»
            <Icon name="external" size={16} />
          </a>
        </div>
      </article>
      <div className="source-guidelines">
        <section className="panel">
          <Icon name="eye" size={25} />
          <h2>Только то, что видно</h2>
          <p>
            Вывод должен опираться на действия в кадре. По видео нельзя
            подтвердить корректность проводки, системной сверки или полномочия
            человека.
          </p>
        </section>
        <section className="panel">
          <Icon name="book" size={25} />
          <h2>От события к правилу</h2>
          <p>
            Для каждого события интерфейс показывает название документа, пункт и
            ссылку, если их передал сервис. Отсутствующее обоснование явно
            отмечается.
          </p>
        </section>
      </div>
      <div className="page-footnote">
        <Icon name="info" size={16} />
        Перед использованием проверьте актуальную редакцию акта. Демо-категории
        не являются юридической квалификацией.
      </div>
    </div>
  );
}

function Settings() {
  const navigate = useNavigate();
  return (
    <div className="page-enter settings-page">
      <h1>Настройки подключения</h1>
      <section className="panel settings-panel">
        <h2>Демонстрационный режим</h2>
        <p>
          Примеры показывают возможности интерфейса. Файлы остаются в браузере,
          ИИ-анализ не выполняется.
        </p>
        <button
          className="button button-primary"
          onClick={() => {
            useAnalysisStore
              .getState()
              .setSettings({ mode: "api", apiKey: "" });
            navigate("/workspace");
          }}
        >
          Открыть рабочий режим
        </button>
        <p>
          Войдите в аккаунт команды, чтобы сохранять видео и получать историю с
          сервера.
        </p>
      </section>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <WorkspaceApp />
    </BrowserRouter>
  );
}

export default App;
