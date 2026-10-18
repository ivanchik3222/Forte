import { LoadingState } from "../components/LoadingState";
import { localeCode, t, useLocale } from "../i18n";
import { useEffect, useState } from "react";
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
import { parseMonitoring, reviewCameras } from "../api/review";
import { useResource } from "../features/workspace/useResource";
import { Camera } from "../api/workspace";

export function MonitoringPage({ live = false }: { live?: boolean }) {
  useLocale();
  const today = useCurrentDay();
  const now = useMonitoringNow();
  const [selectedDay, setSelectedDay] = useState("");
  const [cameraId, setCameraId] = useState("all");
  const [demoCamera, setDemoCamera] = useState("");
  const [demoKind, setDemoKind] = useState<HealthIssue>("occluded");
  const [announcement, setAnnouncement] = useState("");
  const [page, setPage] = useState(1);
  const demo = useNotificationStore();
  const { simulateCameraIssue, restoreDemoCamera } = demo;
  const day = selectedDay || today;
  const query = new URLSearchParams({ date: day, page: String(page) });
  if (cameraId !== "all") query.set("camera_id", cameraId);
  const resource = useResource(
    live ? `/monitoring?${query}` : null,
    parseMonitoring,
    true,
  );
  const [knownCameras, setKnownCameras] = useState<Camera[]>([]);
  const cameraOptions = resource.data?.cameras;
  useEffect(() => {
    if (cameraOptions) setKnownCameras(cameraOptions);
  }, [cameraOptions]);
  const cameras = live
    ? reviewCameras(cameraOptions || knownCameras)
    : demo.cameras;
  const healthSignals = live
    ? resource.data?.signals || {}
    : demo.healthSignals;
  const healthIncidents = live
    ? resource.data?.incidents.items || []
    : demo.healthIncidents;
  const connection = live
    ? resource.error || !resource.data
      ? "disconnected"
      : "connected"
    : demo.connection;
  const journalNow =
    live && resource.data ? Date.parse(resource.data.as_of) : now;
  const scope = cameras.filter((c) => cameraId === "all" || cameraId === c.id);
  const incidents = healthIncidents
    .filter(
      (i) =>
        scope.some((c) => c.id === i.cameraId) &&
        incidentWindow(i, day, journalNow),
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
          <p className="eyebrow">{t("КОНТРОЛЬ САМОГО КОНТРОЛЯ")}</p>
          <h1>{t("Всё ли в поле зрения?")}</h1>
          <p>{t("Проверяем не только события, но и возможность их заметить.")}</p>
        </div>
        <Link className="button button-outline" to="/shift">
          <Icon name="play" size={17} />{t("Смена за минуту")}</Link>
      </div>
      {live && resource.loading && (
        <LoadingState label="Загрузка проверок камер…" variant={resource.data ? "inline" : "panel"} />
      )}
      {t(live && resource.error && (
        <div className="notice" role="alert">
          {t(resource.error)}{" "}
          <button className="text-button" onClick={resource.refresh}>{t("Повторить")}</button>
        </div>
      ))}
      <div className="health-intro">
        <span className="health-intro-symbol">
          <Icon name="eye" size={30} />
        </span>
        <div>
          <strong>{t("Нет событий — ещё не значит, что всё спокойно.")}</strong>
          <p>
            {t(connection === "demo"
              ? "Демо: примеры сбоев и проверок качества. Реальные камеры не подключены."
              : live && resource.loading && !resource.error
                ? "Получаем состояние камер и историю проверок."
                : connection === "disconnected"
                  ? "Связь с сервисом потеряна. Текущее состояние камер неизвестно."
                  : "Свежая проверка изображения подтверждает наблюдение. Без неё состояние камеры неизвестно.")}
          </p>
        </div>
        <span className="health-mode">
          {t(connection === "demo" ? "ДЕМО" : "МОНИТОРИНГ")}
        </span>
      </div>
      <div className="health-metrics">
        <div>
          <span>{t("Требуют внимания сейчас")}</span>
          <strong>
            {t(live && !resource.data ? "—" : String(problems).padStart(2, "0"))}
          </strong>
          <small>{t("Среди выбранных камер")}</small>
        </div>
        <div>
          <span>{t("Нет свежих данных")}</span>
          <strong>
            {t(live && !resource.data ? "—" : String(unknown).padStart(2, "0"))}
          </strong>
          <small>{t("Доступность не подтверждена")}</small>
        </div>
        <div>
          <span>{t("Перерывы за выбранный день")}</span>
          <strong>
            {t(live && !resource.data
              ? "—"
              : (live
                  ? (resource.data?.summary.unavailable_minutes ?? 0)
                  : unavailableMinutes(incidents, day, now)
                ).toLocaleString(localeCode(), {
                  maximumFractionDigits: 1,
                }))}
            <em>{t("камера·мин")}</em>
          </strong>
          <small>{t("Сумма перерывов по камерам, без двойного счёта")}</small>
        </div>
      </div>
      {live && resource.data && (
        <p className="notification-session-note">{t("За выбранный день: без подтверждения наблюдения —")}{" "}
          {t(resource.data.summary.unknown_minutes.toLocaleString(localeCode(), {
            maximumFractionDigits: 1,
          }))}{" "}{t("камера·мин; сниженная видимость —")}{" "}
          {t(resource.data.summary.degraded_minutes.toLocaleString(localeCode(), {
            maximumFractionDigits: 1,
          }))}{" "}{t("камера·мин. Время до первой проверки камеры не включено в расчёт.")}</p>
      )}
      <section className="panel health-cameras" aria-label={t("Состояние камер")}>
        <div className="section-heading">
          <div>
            <h2>{t("Камеры сейчас")}</h2>
            <p>{t("Связь, движение кадра и видимость рабочей зоны")}</p>
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
                  <span className="health-camera-number">{t(camera.name)}</span>
                  <span className="health-dot" />
                </div>
                <p className="health-location">{t(camera.location)}</p>
                <strong className="health-state-label">
                  {t(healthLabels[status])}
                </strong>
                <p className="health-description">
                  {t(healthDescriptions[status])}
                </p>
                <div className="health-last-check">
                  {t(camera.mode === "demo"
                    ? "Демонстрационное состояние"
                    : healthSignals[camera.id]
                      ? t("Последняя проверка · {0}", [alertTime(healthSignals[camera.id].checkedAt)])
                      : "Проверка качества не передана")}
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
                          t("{0}: наблюдение восстановлено в демо.", [camera.name]),
                        );
                      }}
                    >{t("Восстановить в демо")}<Icon name="refresh" size={15} />
                    </button>
                  )}
              </article>
            );
          })}
          {!scope.length && (
            <p className="health-empty">{t("Камеры пока не переданы сервисом.")}</p>
          )}
        </div>
      </section>
      {connection === "demo" && (
        <details className="health-demo-controls">
          <summary>{t("Проверить сценарий сбоя ")}<span>{t("Демо для презентации")}</span>
          </summary>
          <div className="health-demo-form">
            <label>{t("Камера")}<select
                aria-label={t("Камера для демо-сбоя")}
                value={demoId}
                onChange={(e) => setDemoCamera(e.target.value)}
              >
                {cameras
                  .filter((c) => c.mode === "demo")
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {t(c.name)}
                    </option>
                  ))}
              </select>
            </label>
            <label>{t("Что произошло")}<select
                aria-label={t("Тип демо-сбоя")}
                value={demoKind}
                onChange={(e) => setDemoKind(e.target.value as HealthIssue)}
              >
                {issueKinds.map((kind) => (
                  <option key={kind} value={kind}>
                    {t(healthLabels[kind])}
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
            >{t("Показать сбой")}</button>
          </div>
        </details>
      )}
      <p role="status" className="notification-announcement">
        {t(announcement)}
      </p>
      <section className="panel health-journal">
        <div className="section-heading">
          <div>
            <h2>{t("Когда наблюдение прерывалось")}</h2>
            <p>{t("Эти интервалы нужно учитывать при проверке смены")}</p>
          </div>
        </div>
        <div className="review-filters">
          <label>{t("День")}<input
              aria-label={t("День контроля камер")}
              type="date"
              max={today}
              value={day}
              onChange={(e) => {
                setSelectedDay(e.target.value);
                setPage(1);
              }}
            />
          </label>
          <label>{t("Камера")}<select
              aria-label={t("Камера контроля")}
              value={cameraId}
              onChange={(e) => {
                setCameraId(e.target.value);
                setPage(1);
              }}
            >
              <option value="all">{t("Все камеры")}</option>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {t(c.name)} · {t(c.location)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <ol className="health-incident-list">
          {incidents.map((incident) => {
            const window = incidentWindow(incident, day, journalNow)!;
            const ongoing =
              !incident.endedAt && day === today && (!live || !resource.error);
            const degraded = incident.kind === "poor_visibility";
            return (
              <li key={incident.id} className={degraded ? "is-degraded" : ""}>
                <div className="health-incident-time">
                  <time>{t(alertTime(new Date(window.start).toISOString()))}</time>
                  <span>
                    {t(ongoing
                      ? "сейчас"
                      : alertTime(new Date(window.end).toISOString()))}
                  </span>
                </div>
                <div className="health-incident-copy">
                  <span>
                    {t(cameras.find((c) => c.id === incident.cameraId)?.name ||
                      incident.cameraId)}{" "}
                    · {t(healthLabels[incident.kind])}
                    {t(incident.mode === "demo" && " · Демо")}
                  </span>
                  <h3>
                    {t(incident.kind === "unknown"
                      ? "Доступность наблюдения не подтверждена"
                      : degraded
                        ? "Видимость рабочей зоны снижена"
                        : "Наблюдение было недоступно")}
                  </h3>
                  <p>
                    {t(ongoing
                      ? incident.kind === "unknown"
                        ? "Новые проверки не поступали"
                        : "Проблема ещё не устранена"
                      : window.end - window.start < 60_000
                        ? "Меньше минуты в выбранном дне"
                        : t("{0} мин в выбранном дне", [Math.round((window.end - window.start) / 60_000)]))}
                    {t(!degraded && " · События могли остаться незамеченными")}
                  </p>
                </div>
                <span
                  className={`health-incident-badge ${ongoing ? "is-open" : ""}`}
                >
                  {t(ongoing
                    ? "Открыт"
                    : incident.endedAt
                      ? "Завершён"
                      : "Продолжался")}
                </span>
              </li>
            );
          })}
        </ol>
        {!incidents.length &&
          (!live || (!resource.loading && !resource.error)) && (
            <div className="health-empty">
              <h3>{t("В журнале нет сбоев за этот день")}</h3>
              <p>{t("Это не подтверждает непрерывное наблюдение: для него нужна история проверок качества.")}</p>
            </div>
          )}
        {live && resource.data && resource.data.incidents.total > 50 && (
          <div className="table-toolbar">
            <span>{t("Интервалов: ")}{resource.data.incidents.total}{t(" · Страница ")}{page}
            </span>
            <button
              className="button button-outline"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >{t("Назад")}</button>
            <button
              className="button button-outline"
              disabled={page * 50 >= resource.data.incidents.total}
              onClick={() => setPage(page + 1)}
            >{t("Далее")}</button>
          </div>
        )}
      </section>
      <p className="notification-session-note">
        {t(live &&
          resource.data &&
          t("Журнал обновлён в {0}. ", [alertTime(resource.data.as_of)]))}{t("Время по Астане. Проблемы видимости не считаются полным перерывом. Без обновления проверки более 90 секунд состояние реальной камеры становится неизвестным.")}</p>
    </div>
  );
}
