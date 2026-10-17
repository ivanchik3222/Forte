import { useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";
import {
  HealthIssue,
  cameraHealth,
  healthLabels,
  healthDescriptions,
  incidentWindow,
  issueKinds,
  unavailableMinutes,
  useMonitoringNow,
} from "../features/monitoring/health";
import { alertTime, useCurrentDay } from "../features/notifications/types";
import { useNotificationStore } from "../store/useNotificationStore";

export function MonitoringPage() {
  const today = useCurrentDay();
  const now = useMonitoringNow();
  const [selectedDay, setSelectedDay] = useState("");
  const [cameraId, setCameraId] = useState("all");
  const [demoCamera, setDemoCamera] = useState("");
  const [demoKind, setDemoKind] = useState<HealthIssue>("occluded");
  const [announcement, setAnnouncement] = useState("");
  const {
    cameras,
    healthSignals,
    healthIncidents,
    connection,
    simulateCameraIssue,
    restoreDemoCamera,
  } = useNotificationStore();
  const day = selectedDay || today;
  const scope = cameras.filter((c) => cameraId === "all" || cameraId === c.id);
  const incidents = healthIncidents
    .filter(
      (i) =>
        scope.some((c) => c.id === i.cameraId) && incidentWindow(i, day, now),
    )
    .sort((a, b) => Date.parse(b.startedAt) - Date.parse(a.startedAt));
  const states = scope.map((camera) =>
    cameraHealth(camera, healthSignals[camera.id], connection, now),
  );
  const unknown = states.filter((s) => s === "unknown").length;
  const problems = states.filter(
    (s) => s !== "observing" && s !== "unknown",
  ).length;
  const demoId = demoCamera || cameras.find((c) => c.mode === "demo")?.id || "";
  return (
    <div className="page-enter health-page">
      <div className="page-title-row workspace-title">
        <div>
          <p className="eyebrow">КОНТРОЛЬ САМОГО КОНТРОЛЯ</p>
          <h1>Всё ли в поле зрения?</h1>
          <p>Проверяем не только события, но и возможность их заметить.</p>
        </div>
        <Link className="button button-outline" to="/shift">
          <Icon name="play" size={17} />
          Смена за минуту
        </Link>
      </div>
      <div className="health-intro">
        <span className="health-intro-symbol">
          <Icon name="eye" size={30} />
        </span>
        <div>
          <strong>Нет событий — ещё не значит, что всё спокойно.</strong>
          <p>
            {connection === "demo"
              ? "Демо: примеры сбоев и проверок качества. Реальные камеры не подключены."
              : connection === "disconnected"
                ? "Связь с сервисом потеряна. Текущее состояние камер неизвестно."
                : "Свежая проверка изображения подтверждает наблюдение. Без неё состояние камеры неизвестно."}
          </p>
        </div>
        <span className="health-mode">
          {connection === "demo" ? "ДЕМО" : "МОНИТОРИНГ"}
        </span>
      </div>
      <div className="health-metrics">
        <div>
          <span>Требуют внимания сейчас</span>
          <strong>{String(problems).padStart(2, "0")}</strong>
          <small>Среди выбранных камер</small>
        </div>
        <div>
          <span>Нет свежих данных</span>
          <strong>{String(unknown).padStart(2, "0")}</strong>
          <small>Доступность не подтверждена</small>
        </div>
        <div>
          <span>Перерывы за выбранный день</span>
          <strong>
            {unavailableMinutes(incidents, day, now).toLocaleString("ru-RU", {
              maximumFractionDigits: 1,
            })}
            <em>камера·мин</em>
          </strong>
          <small>Сумма перерывов по камерам, без двойного счёта</small>
        </div>
      </div>
      <section className="panel health-cameras" aria-label="Состояние камер">
        <div className="section-heading">
          <div>
            <h2>Камеры сейчас</h2>
            <p>Связь, движение кадра и видимость рабочей зоны</p>
          </div>
        </div>
        <div className="health-camera-grid">
          {scope.map((camera) => {
            const status = cameraHealth(
              camera,
              healthSignals[camera.id],
              connection,
              now,
            );
            return (
              <article
                className={`health-camera health-${status}`}
                key={camera.id}
              >
                <div className="health-camera-top">
                  <span className="health-camera-number">{camera.name}</span>
                  <span className="health-dot" />
                </div>
                <p className="health-location">{camera.location}</p>
                <strong className="health-state-label">
                  {healthLabels[status]}
                </strong>
                <p className="health-description">
                  {healthDescriptions[status]}
                </p>
                <div className="health-last-check">
                  {camera.mode === "demo"
                    ? "Демонстрационное состояние"
                    : healthSignals[camera.id]
                      ? `Последняя проверка · ${alertTime(healthSignals[camera.id].checkedAt)}`
                      : "Проверка качества не передана"}
                </div>
                {connection === "demo" &&
                  camera.mode === "demo" &&
                  status !== "observing" &&
                  status !== "unknown" && (
                    <button
                      className="text-button"
                      onClick={() => {
                        restoreDemoCamera(camera.id);
                        setAnnouncement(
                          `${camera.name}: наблюдение восстановлено в демо.`,
                        );
                      }}
                    >
                      Восстановить в демо
                      <Icon name="refresh" size={15} />
                    </button>
                  )}
              </article>
            );
          })}
          {!scope.length && (
            <p className="health-empty">Камеры пока не переданы сервисом.</p>
          )}
        </div>
      </section>
      {connection === "demo" && (
        <details className="health-demo-controls">
          <summary>
            Проверить сценарий сбоя <span>Демо для презентации</span>
          </summary>
          <div className="health-demo-form">
            <label>
              Камера
              <select
                aria-label="Камера для демо-сбоя"
                value={demoId}
                onChange={(e) => setDemoCamera(e.target.value)}
              >
                {cameras
                  .filter((c) => c.mode === "demo")
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Что произошло
              <select
                aria-label="Тип демо-сбоя"
                value={demoKind}
                onChange={(e) => setDemoKind(e.target.value as HealthIssue)}
              >
                {issueKinds.map((kind) => (
                  <option key={kind} value={kind}>
                    {healthLabels[kind]}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="button button-primary"
              disabled={!demoId}
              onClick={() => {
                simulateCameraIssue(demoId, demoKind);
                setSelectedDay("");
                setCameraId("all");
                setAnnouncement(
                  "Демо-сбой начался. Состояние камеры и журнал обновлены.",
                );
              }}
            >
              Показать сбой
            </button>
          </div>
        </details>
      )}
      <p role="status" className="notification-announcement">
        {announcement}
      </p>
      <section className="panel health-journal">
        <div className="section-heading">
          <div>
            <h2>Когда наблюдение прерывалось</h2>
            <p>Эти интервалы нужно учитывать при проверке смены</p>
          </div>
        </div>
        <div className="review-filters">
          <label>
            День
            <input
              aria-label="День контроля камер"
              type="date"
              max={today}
              value={day}
              onChange={(e) => setSelectedDay(e.target.value)}
            />
          </label>
          <label>
            Камера
            <select
              aria-label="Камера контроля"
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
        <ol className="health-incident-list">
          {incidents.map((incident) => {
            const window = incidentWindow(incident, day, now)!;
            const ongoing = !incident.endedAt && day === today;
            const degraded = incident.kind === "poor_visibility";
            return (
              <li key={incident.id} className={degraded ? "is-degraded" : ""}>
                <div className="health-incident-time">
                  <time>{alertTime(new Date(window.start).toISOString())}</time>
                  <span>
                    {ongoing
                      ? "сейчас"
                      : alertTime(new Date(window.end).toISOString())}
                  </span>
                </div>
                <div className="health-incident-copy">
                  <span>
                    {cameras.find((c) => c.id === incident.cameraId)?.name ||
                      incident.cameraId}{" "}
                    · {healthLabels[incident.kind]}
                    {incident.mode === "demo" && " · Демо"}
                  </span>
                  <h3>
                    {degraded
                      ? "Видимость рабочей зоны снижена"
                      : "Наблюдение было недоступно"}
                  </h3>
                  <p>
                    {ongoing
                      ? "Проблема ещё не устранена"
                      : window.end - window.start < 60_000
                        ? "Меньше минуты в выбранном дне"
                        : `${Math.round((window.end - window.start) / 60_000)} мин в выбранном дне`}
                    {!degraded && " · События могли остаться незамеченными"}
                  </p>
                </div>
                <span
                  className={`health-incident-badge ${ongoing ? "is-open" : ""}`}
                >
                  {ongoing
                    ? "Открыт"
                    : incident.endedAt
                      ? "Завершён"
                      : "Продолжался"}
                </span>
              </li>
            );
          })}
        </ol>
        {!incidents.length && (
          <div className="health-empty">
            <h3>В журнале нет сбоев за этот день</h3>
            <p>
              Это не подтверждает непрерывное наблюдение: для него нужна история
              проверок качества.
            </p>
          </div>
        )}
      </section>
      <p className="notification-session-note">
        Время по Астане. Проблемы видимости не считаются полным перерывом. Без
        обновления проверки более 90 секунд состояние реальной камеры становится
        неизвестным.
      </p>
    </div>
  );
}
