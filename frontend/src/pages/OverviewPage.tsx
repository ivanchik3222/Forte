import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";
import { HistoryTable } from "../features/analysis/HistoryTable";
import { AnalysisRecord } from "../features/analysis/types";
import { NotificationFeed } from "../features/notifications/NotificationFeed";
import { localDay, useCurrentDay } from "../features/notifications/types";
import { useNotificationStore } from "../store/useNotificationStore";

export function OverviewPage({
  records,
  onOpen,
  onNew,
  onHelp,
}: {
  records: AnalysisRecord[];
  onOpen: (id: string) => void;
  onNew: () => void;
  onHelp: () => void;
}) {
  const today = useCurrentDay();
  const { alerts, cameras, connection } = useNotificationStore();
  const daily = alerts.filter((alert) => localDay(alert.detectedAt) === today);
  const fresh = daily.filter((alert) => !alert.readAt).length;
  return (
    <div className="page-enter operations-overview">
      <div className="page-title-row workspace-title">
        <div>
          <p className="eyebrow">
            {new Date(`${today}T12:00:00+05:00`).toLocaleDateString("ru-RU", {
              day: "numeric",
              month: "long",
              year: "numeric",
              timeZone: "Asia/Almaty",
            })}
          </p>
          <h1>Контроль кассовых операций</h1>
          <p>
            Смотрите события с камер или загрузите видео для новой проверки.
          </p>
        </div>
        <button
          className="button button-primary new-check-button"
          onClick={onNew}
        >
          <Icon name="plus" size={20} />
          Новая проверка
        </button>
      </div>
      <section
        className="monitoring-summary"
        aria-label="Сводка событий за день"
      >
        <div className="monitoring-summary-copy">
          <span className="monitoring-kicker">
            КАМЕРЫ · СЕГОДНЯ{connection === "demo" && <span>ДЕМО</span>}
          </span>
          <h2>
            {fresh ? (
              <>
                Есть события для просмотра<span>{fresh}</span>
              </>
            ) : (
              "Новых событий нет"
            )}
          </h2>
          <p>
            {connection === "demo"
              ? "Пример непрерывного наблюдения. Реальные камеры пока не подключены."
              : connection === "connected"
                ? "Сигналы с камер поступают в оповещения в течение дня."
                : "Связь с камерами потеряна. Новые события могут поступать с задержкой."}
          </p>
          <Link to="/notifications" className="monitoring-link">
            Открыть оповещения
            <Icon name="arrow" size={19} />
          </Link>
        </div>
        <dl className="monitoring-totals">
          <div>
            <dt>Всего событий</dt>
            <dd>{daily.length.toString().padStart(2, "0")}</dd>
          </div>
          <div>
            <dt>Просмотрено</dt>
            <dd>{(daily.length - fresh).toString().padStart(2, "0")}</dd>
          </div>
          <div>
            <dt>{connection === "demo" ? "Камер в демо" : "Камер в списке"}</dt>
            <dd>{cameras.length.toString().padStart(2, "0")}</dd>
          </div>
        </dl>
      </section>
      <div className="operations-grid">
        <section className="panel overview-notifications">
          <div className="section-heading">
            <div>
              <h2>Последние оповещения</h2>
              <p>События, замеченные камерами сегодня</p>
            </div>
            <Link className="text-button" to="/notifications">
              Все события
              <Icon name="arrow" size={16} />
            </Link>
          </div>
          <NotificationFeed alerts={daily.slice(0, 3)} />
        </section>
        <aside className="operations-aside">
          <section className="panel camera-panel">
            <div className="section-heading">
              <h2>Камеры</h2>
              <span className="camera-mode-label">
                {connection === "demo"
                  ? "Демо"
                  : connection === "connected"
                    ? "Подключены"
                    : "Нет связи"}
              </span>
            </div>
            <ul>
              {cameras.map((camera) => (
                <li key={camera.id}>
                  <div>
                    <strong>{camera.name}</strong>
                    <p>{camera.location}</p>
                  </div>
                  <span
                    className={`camera-state ${camera.status}`}
                    aria-label={`${camera.name}: ${camera.status === "online" ? "наблюдение" : "нет связи"}`}
                  >
                    <span className="visually-hidden">
                      {camera.status === "online" ? "Наблюдение" : "Нет связи"}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="camera-panel-note">
              {connection === "demo"
                ? "Показаны примеры камер. Для реального наблюдения нужен поток событий от сервиса команды."
                : "Состояние камер передаёт сервис мониторинга."}
            </p>
          </section>
          <button className="workspace-help" onClick={onHelp}>
            <span>
              <strong>Как начать проверку?</strong>
              <small>От загрузки видео до результата</small>
            </span>
            <Icon name="arrow" size={18} />
          </button>
        </aside>
      </div>
      <section className="panel recent-panel">
        <div className="section-heading">
          <div className="heading-with-count">
            <h2>Проверки загруженных видео</h2>
            <span className="count-pill">{records.length}</span>
          </div>
          <Link to="/history" className="text-button">
            Вся история
            <Icon name="arrow" size={16} />
          </Link>
        </div>
        <HistoryTable records={records} onOpen={onOpen} />
      </section>
    </div>
  );
}
