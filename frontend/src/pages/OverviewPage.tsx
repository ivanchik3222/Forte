import { formatDate, t, useLocale } from "../i18n";
import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";
import { HistoryTable } from "../features/analysis/HistoryTable";
import { AnalysisRecord } from "../features/analysis/types";
import { NotificationFeed } from "../features/notifications/NotificationFeed";
import { localDay, useCurrentDay } from "../features/notifications/types";
import { useNotificationStore } from "../store/useNotificationStore";
import {
  cameraHealth,
  healthLabels,
  incidentWindow,
  useMonitoringNow,
} from "../features/monitoring/health";

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
  useLocale();
  const today = useCurrentDay();
  const { alerts, cameras, connection, healthSignals, healthIncidents } =
    useNotificationStore();
  const now = useMonitoringNow();
  const interruptions = healthIncidents.filter((i) =>
    incidentWindow(i, today, now),
  );
  const uncertainCameras = cameras.filter(
    (c) =>
      cameraHealth(c, healthSignals[c.id], connection, now) !== "observing",
  ).length;
  const daily = alerts.filter((alert) => localDay(alert.detectedAt) === today);
  const fresh = daily.filter((alert) => !alert.readAt).length;
  return (
    <div className="page-enter operations-overview">
      <div className="page-title-row workspace-title">
        <div>
          <p className="eyebrow">
            {formatDate(`${today}T12:00:00+05:00`, {
              day: "numeric",
              month: "long",
              year: "numeric",
              timeZone: "Asia/Almaty",
            })}
          </p>
          <h1>{t("Контроль кассовых операций")}</h1>
          <p>{t("Смотрите события с камер или загрузите видео для новой проверки.")}</p>
        </div>
        <button
          className="button button-primary new-check-button"
          onClick={onNew}
        >
          <Icon name="plus" size={20} />{t("Новая проверка")}</button>
      </div>
      <section
        className="monitoring-summary"
        aria-label={t("Сводка событий за день")}
      >
        <div className="monitoring-summary-copy">
          <span className="monitoring-kicker">{t("КАМЕРЫ · СЕГОДНЯ")}{connection === "demo" && <span>{t("ДЕМО")}</span>}
          </span>
          <h2>
            {t(fresh ? (
              <>{t("Есть события для просмотра")}<span>{fresh}</span>
              </>
            ) : (
              "Новых событий нет"
            ))}
          </h2>
          <p>
            {t(connection === "demo"
              ? "Пример непрерывного наблюдения. Реальные камеры пока не подключены."
              : connection === "connected"
                ? "Сигналы с камер поступают в оповещения в течение дня."
                : "Связь с камерами потеряна. Новые события могут поступать с задержкой.")}
          </p>
          <Link to="/notifications" className="monitoring-link">{t("Открыть оповещения")}<Icon name="arrow" size={19} />
          </Link>
        </div>
        <dl className="monitoring-totals">
          <div>
            <dt>{t("Всего событий")}</dt>
            <dd>{t(daily.length.toString().padStart(2, "0"))}</dd>
          </div>
          <div>
            <dt>{t("Просмотрено")}</dt>
            <dd>{t((daily.length - fresh).toString().padStart(2, "0"))}</dd>
          </div>
          <div>
            <dt>{t(connection === "demo" ? "Камер в демо" : "Камер в списке")}</dt>
            <dd>{t(cameras.length.toString().padStart(2, "0"))}</dd>
          </div>
        </dl>
      </section>
      <div className="review-feature-grid">
        <Link className="review-feature review-feature-shift" to="/shift">
          <div className="review-feature-top">
            <span>{t("ВАЖНОЕ ЗА ДЕНЬ")}</span>
            <Icon name="arrow" size={21} />
          </div>
          <div className="review-feature-main">
            <span className="review-play-orb">
              <Icon name="play" size={24} />
            </span>
            <div>
              <h2>{t("Смена за минуту")}</h2>
              <p>
                {t(daily.length
                  ? t("До {0} эпизодов. Смотрите важное, открывайте контекст.", [Math.min(daily.length, 6)])
                  : "Короткая подборка появится, когда поступят события.")}
              </p>
            </div>
          </div>
          <div className="review-feature-bottom">
            <span>{t("Смотреть обзор")}</span>
            <span>{t("Эпизоды → контекст")}</span>
          </div>
        </Link>
        <Link className="review-feature review-feature-health" to="/monitoring">
          <div className="review-feature-top">
            <span>{t("КОНТРОЛЬ КАМЕР")}</span>
            <Icon name="arrow" size={21} />
          </div>
          <div className="review-feature-main">
            <span className="review-health-number">
              {String(uncertainCameras).padStart(2, "0")}
            </span>
            <div>
              <h2>
                {t(uncertainCameras
                  ? "Наблюдение под вопросом"
                  : "Доступность наблюдения")}
              </h2>
              <p>
                {t(uncertainCameras
                  ? "Камеры с проблемами или без свежего подтверждения."
                  : "Проверки изображения и журнал перерывов за день.")}
              </p>
            </div>
          </div>
          <div className="review-feature-bottom">
            <span>{t("Проверить камеры")}</span>
            <span>{t("Сбоев за день: ")}{interruptions.length}</span>
          </div>
        </Link>
      </div>
      <div className="operations-grid">
        <section className="panel overview-notifications">
          <div className="section-heading">
            <div>
              <h2>{t("Последние оповещения")}</h2>
              <p>{t("События, замеченные камерами сегодня")}</p>
            </div>
            <Link className="text-button" to="/notifications">{t("Все события")}<Icon name="arrow" size={16} />
            </Link>
          </div>
          <NotificationFeed alerts={daily.slice(0, 3)} />
        </section>
        <aside className="operations-aside">
          <section className="panel camera-panel">
            <div className="section-heading">
              <h2>{t("Камеры")}</h2>
              <span className="camera-mode-label">
                {t(connection === "demo"
                  ? "Демо"
                  : connection === "connected"
                    ? "Подключены"
                    : "Нет связи")}
              </span>
            </div>
            <ul>
              {cameras.map((camera) => (
                <li key={camera.id}>
                  <div>
                    <strong>{t(camera.name)}</strong>
                    <p>{t(camera.location)}</p>
                  </div>
                  <span
                    className={`camera-health-tag health-${cameraHealth(camera, healthSignals[camera.id], connection, now)}`}
                  >
                    {t(healthLabels[
                        cameraHealth(
                          camera,
                          healthSignals[camera.id],
                          connection,
                          now,
                        )
                      ])}
                  </span>
                </li>
              ))}
            </ul>
            <p className="camera-panel-note">
              {t(connection === "demo"
                ? "Показаны примеры камер. Для реального наблюдения нужен поток событий от сервиса команды."
                : "Состояние камер передаёт сервис мониторинга.")}
            </p>
          </section>
          <button className="workspace-help" onClick={onHelp}>
            <span>
              <strong>{t("Как начать проверку?")}</strong>
              <small>{t("От загрузки видео до результата")}</small>
            </span>
            <Icon name="arrow" size={18} />
          </button>
        </aside>
      </div>
      <section className="panel recent-panel">
        <div className="section-heading">
          <div className="heading-with-count">
            <h2>{t("Проверки загруженных видео")}</h2>
            <span className="count-pill">{records.length}</span>
          </div>
          <Link to="/history" className="text-button">{t("Вся история")}<Icon name="arrow" size={16} />
          </Link>
        </div>
        <HistoryTable records={records} onOpen={onOpen} />
      </section>
    </div>
  );
}
