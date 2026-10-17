import { useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import {
  dayBounds,
  incidentWindow,
  useMonitoringNow,
} from "../features/monitoring/health";
import {
  alertTime,
  CameraAlert,
  useCurrentDay,
} from "../features/notifications/types";
import { EpisodeContext, EpisodePlayer } from "../features/shift/EpisodePlayer";
import { shiftEpisodes } from "../features/shift/model";
import { useNotificationStore } from "../store/useNotificationStore";

export function ShiftPage() {
  const today = useCurrentDay();
  const [selectedDay, setSelectedDay] = useState("");
  const [cameraId, setCameraId] = useState("all");
  const { alerts, cameras, connection } = useNotificationStore();
  const day = selectedDay || today;
  const all = shiftEpisodes(alerts, day, cameraId, Number.MAX_SAFE_INTEGER);
  const episodes = all.slice(-6);
  // Reset playback on a changed selection, new playlist, or updated media contract.
  const playlistKey = JSON.stringify([
    day,
    cameraId,
    episodes.map((a) => [a.id, a.recording, a.event.timecode_sec]),
  ]);
  return (
    <div className="page-enter shift-page">
      <div className="page-title-row workspace-title">
        <div>
          <p className="eyebrow">ВАЖНОЕ ЗА ДЕНЬ</p>
          <h1>Смена за минуту</h1>
          <p>
            От события к событию. С объяснением и возможностью увидеть контекст.
          </p>
        </div>
        <Link className="button button-outline" to="/monitoring">
          <Icon name="eye" size={18} />
          Контроль камер
        </Link>
      </div>
      <div className="panel shift-filter-panel">
        <div className="review-filters">
          <label>
            День
            <input
              aria-label="День обзора смены"
              type="date"
              max={today}
              value={day}
              onChange={(e) => setSelectedDay(e.target.value)}
            />
          </label>
          <label>
            Камера
            <select
              aria-label="Камера обзора смены"
              value={cameraId}
              onChange={(e) => setCameraId(e.target.value)}
            >
              <option value="all">Все камеры</option>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {c.location}
                </option>
              ))}
            </select>
          </label>
        </div>
        <span className="shift-selection-note">
          {connection === "demo" ? "ДЕМО · " : ""}
          {all.length > 6
            ? `Последние 6 из ${all.length} событий`
            : `Эпизодов в подборке: ${all.length}`}
          {episodes.length > 0 && ` · до ${episodes.length * 10} сек`}
        </span>
      </div>
      <ShiftReview
        key={playlistKey}
        episodes={episodes}
        day={day}
        cameraId={cameraId}
      />
      <p className="notification-session-note">
        Подборка включает до шести последних событий дня. Она не заменяет полный
        просмотр смены. Все события доступны в{" "}
        <Link to="/notifications">оповещениях</Link>.
      </p>
    </div>
  );
}

export function ShiftReview({
  episodes,
  day,
  cameraId,
}: {
  episodes: CameraAlert[];
  day: string;
  cameraId: string;
}) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [run, setRun] = useState(0);
  const [context, setContext] = useState(false);
  const [cursorMinute, setCursorMinute] = useState(() =>
    episodes[0]
      ? Math.min(
          1439,
          Math.floor(
            (Date.parse(episodes[0].detectedAt) - dayBounds(day).start) /
              60_000,
          ),
        )
      : 0,
  );
  const now = useMonitoringNow();
  const { healthIncidents, markRead, alerts } = useNotificationStore();
  const selected = episodes[index];
  const read = alerts.find((a) => a.id === selected?.id)?.readAt;
  const bounds = dayBounds(day);
  const incidents = healthIncidents.filter(
    (i) =>
      (cameraId === "all" || i.cameraId === cameraId) &&
      incidentWindow(i, day, now),
  );
  const choose = (next: number, syncCursor = true) => {
    setIndex(next);
    setRun((r) => r + 1);
    setCompleted(false);
    if (syncCursor)
      setCursorMinute(
        Math.min(
          1439,
          Math.floor(
            (Date.parse(episodes[next].detectedAt) - bounds.start) / 60_000,
          ),
        ),
      );
  };
  return (
    <>
      {selected ? (
        <section className="panel shift-review" aria-label="Обзор смены">
          <div className="shift-review-heading">
            <span>
              <span className="shift-live-dot" />
              {playing
                ? "ПОДБОРКА ИДЁТ"
                : completed
                  ? "ПОДБОРКА ЗАВЕРШЕНА"
                  : "ГОТОВО К ПРОСМОТРУ"}
            </span>
            <strong>
              {String(index + 1).padStart(2, "0")}
              <span> / {String(episodes.length).padStart(2, "0")}</span>
            </strong>
          </div>
          <div className="shift-playback">
            <button
              className="shift-skip"
              aria-label="Предыдущий эпизод"
              disabled={index === 0}
              onClick={() => choose(index - 1)}
            >
              <Icon name="chevron" className="shift-back-icon" size={20} />
            </button>
            <button
              className="button button-primary shift-play-button"
              onClick={() => {
                if (completed) {
                  choose(0);
                  setPlaying(true);
                } else setPlaying(!playing);
              }}
            >
              <Icon
                name={playing ? "pause" : completed ? "refresh" : "play"}
                size={18}
              />
              {playing
                ? "Пауза"
                : completed
                  ? "Смотреть ещё раз"
                  : "Смотреть подборку"}
            </button>
            <button
              className="shift-skip"
              aria-label="Следующий эпизод"
              disabled={index === episodes.length - 1}
              onClick={() => choose(index + 1)}
            >
              <Icon name="chevron" size={20} />
            </button>
            <span className="shift-playback-note" aria-live="polite">
              {completed ? "Все эпизоды показаны" : "До 10 секунд на эпизод"}
            </span>
          </div>
          <div className="shift-stage">
            <EpisodePlayer
              key={`${selected.id}-${run}`}
              alert={selected}
              playing={playing}
              onPause={() => setPlaying(false)}
              onFinish={() => {
                if (index < episodes.length - 1) choose(index + 1);
                else {
                  setPlaying(false);
                  setCompleted(true);
                }
              }}
            />
            <div className="shift-explanation">
              <span className="shift-event-source">
                {selected.cameraName} ·{" "}
                {selected.mode === "demo" ? "Демо-событие" : "Событие модели"}
              </span>
              <time className="shift-event-time" dateTime={selected.detectedAt}>
                {alertTime(selected.detectedAt)}
              </time>
              <h2>{selected.event.type}</h2>
              <p>{selected.event.description}</p>
              <button
                className="button button-outline"
                onClick={() => {
                  setPlaying(false);
                  setContext(true);
                }}
              >
                Что было до и после
                <Icon name="arrow" size={17} />
              </button>
              <button
                className="text-button shift-mark-read"
                disabled={Boolean(read)}
                onClick={() => markRead([selected.id])}
              >
                <Icon name="check" size={16} />
                {read ? "Отмечено как просмотренное" : "Отметить просмотренным"}
              </button>
            </div>
          </div>
        </section>
      ) : (
        <section className="panel health-empty">
          <h2>За этот день событий нет</h2>
          <p>
            Выберите другую дату или камеру. Отсутствие событий не подтверждает
            непрерывное наблюдение.
          </p>
          <Link className="text-button" to="/notifications">
            Открыть оповещения
            <Icon name="arrow" size={16} />
          </Link>
        </section>
      )}
      <section className="panel shift-timeline-panel" aria-label="Шкала смены">
        <div className="section-heading">
          <div>
            <h2>Смена целиком</h2>
            <p>События и перерывы на одной шкале · время по Астане</p>
          </div>
          <span className="shift-day">
            {day.split("-").reverse().join(".")}
          </span>
        </div>
        <div className="shift-timeline">
          <div className="shift-time-track" aria-hidden="true">
            {incidents.map((i) => {
              const w = incidentWindow(i, day, now)!;
              return (
                <span
                  className={`shift-blind-band ${i.kind === "poor_visibility" ? "is-degraded" : ""}`}
                  key={i.id}
                  style={{
                    left: `${(w.start - bounds.start) / 864000}%`,
                    width: `${Math.max(0.35, (w.end - w.start) / 864000)}%`,
                  }}
                />
              );
            })}
            {episodes.map((a, i) => (
              <span
                key={a.id}
                className={`shift-event-marker ${i === index ? "is-selected" : ""}`}
                style={{
                  left: `${(Date.parse(a.detectedAt) - bounds.start) / 864000}%`,
                }}
              />
            ))}
          </div>
          <input
            type="range"
            min="0"
            max="1439"
            step="1"
            value={cursorMinute}
            disabled={!episodes.length}
            aria-label="Выбрать время на шкале смены"
            aria-valuetext={
              selected
                ? `${String(Math.floor(cursorMinute / 60)).padStart(2, "0")}:${String(cursorMinute % 60).padStart(2, "0")}, ближайшее событие: ${alertTime(selected.detectedAt)}, ${selected.event.type}`
                : "Нет событий"
            }
            onChange={(e) => {
              const target = bounds.start + Number(e.target.value) * 60_000;
              const nearest = episodes.reduce(
                (best, a, i) =>
                  Math.abs(Date.parse(a.detectedAt) - target) <
                  Math.abs(Date.parse(episodes[best].detectedAt) - target)
                    ? i
                    : best,
                0,
              );
              setCursorMinute(Number(e.target.value));
              setPlaying(false);
              choose(nearest, false);
            }}
          />
          <div className="shift-time-labels" aria-hidden="true">
            <span>00:00</span>
            <span>06:00</span>
            <span>12:00</span>
            <span>18:00</span>
            <span>24:00</span>
          </div>
        </div>
        <div className="shift-timeline-legend">
          <span>
            <i />
            Событие
          </span>
          <span>
            <i />
            Наблюдение недоступно
          </span>
          <span>
            <i />
            Плохая видимость
          </span>
        </div>
        <p className="shift-timeline-note">
          Нейтральные участки не подтверждают доступность наблюдения.
          {cameraId === "all" && " Перерывы показаны по всем камерам."}
        </p>
        {incidents.length > 0 && (
          <Link className="shift-health-warning" to="/monitoring">
            <Icon name="eye" size={20} />
            <span>
              <strong>В этот день были проблемы наблюдения</strong>
              <small>
                Откройте журнал, чтобы проверить камеры и интервалы.
              </small>
            </span>
            <Icon name="arrow" size={18} />
          </Link>
        )}
      </section>
      {episodes.length > 0 && (
        <section className="shift-episodes" aria-label="Эпизоды смены">
          <div className="section-heading">
            <h2>Маршрут просмотра</h2>
            <span>Эпизодов: {episodes.length}</span>
          </div>
          <ol>
            {episodes.map((alert, i) => (
              <li key={alert.id}>
                <button
                  aria-current={index === i ? "step" : undefined}
                  onClick={() => {
                    setPlaying(false);
                    choose(i);
                  }}
                >
                  <span className="shift-episode-number">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span>
                    <small>
                      {alertTime(alert.detectedAt)} · {alert.cameraName}
                    </small>
                    <strong>{alert.event.type}</strong>
                  </span>
                  <Icon
                    name={index === i && playing ? "pause" : "play"}
                    size={17}
                  />
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}
      {context && selected && (
        <Modal
          title="До и после события"
          wide
          onClose={() => setContext(false)}
        >
          <EpisodeContext alert={selected} />
        </Modal>
      )}
    </>
  );
}
