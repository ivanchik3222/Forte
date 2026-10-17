import { useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";
import { NotificationFeed } from "../features/notifications/NotificationFeed";
import { localDay, useCurrentDay } from "../features/notifications/types";
import { useNotificationStore } from "../store/useNotificationStore";

export function NotificationsPage({ onNew }: { onNew: () => void }) {
  const today = useCurrentDay();
  const [selectedDay, setSelectedDay] = useState<string>();
  const [camera, setCamera] = useState("all");
  const [filter, setFilter] = useState("all");
  const [announcement, setAnnouncement] = useState("");
  const { alerts, cameras, connection, markRead, addDemoAlert } =
    useNotificationStore();
  const day = selectedDay || today;
  const daily = alerts.filter(
    (alert) =>
      localDay(alert.detectedAt) === day &&
      (camera === "all" || alert.cameraId === camera),
  );
  const fresh = daily.filter((alert) => !alert.readAt);
  const filtered = daily.filter(
    (alert) =>
      filter === "all" || (filter === "new" ? !alert.readAt : alert.readAt),
  );
  const tabs = [
    { id: "all", label: "Все", count: daily.length },
    { id: "new", label: "Новые", count: fresh.length },
    { id: "read", label: "Просмотрены", count: daily.length - fresh.length },
  ];
  return (
    <div className="page-enter notifications-page">
      <div className="page-title-row workspace-title">
        <div>
          <p className="eyebrow">СОБЫТИЯ С КАМЕР</p>
          <h1>Оповещения</h1>
          <p>Всё, что требует внимания, — в одной ленте за день.</p>
        </div>
        <button
          className="button button-primary new-check-button"
          onClick={onNew}
        >
          <Icon name="plus" size={19} />
          Новая проверка
        </button>
      </div>
      <div className={`camera-connection-note connection-${connection}`}>
        <div>
          <span className="connection-dot" />
          <strong>
            {connection === "demo"
              ? "Демонстрация мониторинга"
              : connection === "connected"
                ? "Поток камер подключён"
                : "Связь с потоком потеряна"}
          </strong>
          <p>
            {connection === "demo"
              ? "Камеры пока не подключены. Посмотрите, как новое событие попадает в ленту."
              : connection === "connected"
                ? "Новые события добавляются по мере поступления от камер."
                : "Показаны уже полученные события. Новые могут поступать с задержкой."}
          </p>
        </div>
        {connection === "demo" && (
          <button
            className="button button-outline"
            onClick={() => {
              addDemoAlert();
              setSelectedDay(undefined);
              setCamera("all");
              setFilter("all");
              setAnnouncement("Новое демо-событие добавлено в начало ленты.");
            }}
          >
            Показать новое событие
            <Icon name="plus" size={16} />
          </button>
        )}
      </div>
      <p role="status" className="notification-announcement">
        {announcement}
      </p>
      <div className="notification-review-links">
        <Link to="/shift">
          <Icon name="play" size={17} />
          Смотреть смену за минуту
          <Icon name="arrow" size={16} />
        </Link>
        <Link to="/monitoring">
          <Icon name="eye" size={18} />
          Проверить доступность камер
          <Icon name="arrow" size={16} />
        </Link>
      </div>
      <section className="panel inbox-panel" aria-label="Лента оповещений">
        <div className="inbox-toolbar">
          <div className="inbox-date">
            <label>
              <span>День</span>
              <input
                type="date"
                aria-label="День оповещений"
                value={day}
                max={today}
                onChange={(event) =>
                  setSelectedDay(event.target.value || undefined)
                }
              />
            </label>
            {day !== today && (
              <button
                className="text-button"
                onClick={() => setSelectedDay(undefined)}
              >
                Сегодня
              </button>
            )}
          </div>
          <label className="inbox-camera">
            <span>Камера</span>
            <select
              aria-label="Камера оповещений"
              value={camera}
              onChange={(event) => setCamera(event.target.value)}
            >
              <option value="all">Все камеры</option>
              {cameras.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {item.location}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="inbox-controls">
          <div
            className="inbox-filters"
            role="group"
            aria-label="Состояние оповещений"
          >
            {tabs.map((tab) => (
              <button
                key={tab.id}
                aria-pressed={filter === tab.id}
                onClick={() => setFilter(tab.id)}
              >
                {tab.label}
                <span>{tab.count}</span>
              </button>
            ))}
          </div>
          <button
            className="text-button inbox-mark-read"
            disabled={!filtered.some((alert) => !alert.readAt)}
            onClick={() => {
              markRead(filtered.map((alert) => alert.id));
              setAnnouncement("Показанные события отмечены как просмотренные.");
            }}
          >
            Прочитать показанные
            <Icon name="check" size={16} />
          </button>
        </div>
        <NotificationFeed
          alerts={filtered}
          emptyText={
            filter === "new"
              ? "Новых оповещений нет"
              : filter === "read"
                ? "Просмотренных событий пока нет"
                : "За этот день событий нет"
          }
        />
      </section>
      <p className="notification-session-note">
        Время указано по Астане. В прототипе события и отметки просмотра
        сохраняются до обновления вкладки.
      </p>
    </div>
  );
}
