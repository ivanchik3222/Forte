import { formatDate, t, useLocale } from "../../i18n";
import { useState } from "react";
import { Icon } from "../../components/Icon";
import { Modal } from "../../components/Modal";
import { useNotificationStore } from "../../store/useNotificationStore";
import { safeSourceUrl, timecode } from "../analysis/types";
import { alertTime, CameraAlert } from "./types";

export function NotificationFeed({
  alerts,
  emptyText = "Событий за этот день пока нет.",
}: {
  alerts: CameraAlert[];
  emptyText?: string;
}) {
  useLocale();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = useNotificationStore((state) =>
    state.alerts.find((alert) => alert.id === selectedId),
  );
  const markRead = useNotificationStore((state) => state.markRead);
  const [frameIndex, setFrameIndex] = useState(0);
  const [imageFailed, setImageFailed] = useState(false);
  const frame = selected?.event.evidence_frames[frameIndex];
  const image =
    frame && /^[A-Za-z0-9+/=\s]+$/.test(frame.image_base64)
      ? `data:image/jpeg;base64,${frame.image_base64.replace(/\s/g, "")}`
      : undefined;
  const ruleUrl = safeSourceUrl(selected?.event.rule?.url);
  return (
    <>
      {alerts.length ? (
        <ul className="notification-feed" aria-label={t("События с камер")}>
          {alerts.map((alert) => (
            <li key={alert.id}>
              <button
                className={`notification-row ${!alert.readAt ? "is-unread" : ""}`}
                aria-label={t("Открыть событие: {0}, {1}, {2}{3}", [alert.event.type, alert.cameraName, alertTime(alert.detectedAt), !alert.readAt ? ", новое" : ""])}
                onClick={() => {
                  setSelectedId(alert.id);
                  setFrameIndex(0);
                  setImageFailed(false);
                  markRead([alert.id]);
                }}
              >
                <time className="notification-time" dateTime={alert.detectedAt}>
                  {t(alertTime(alert.detectedAt))}
                </time>
                <span className="notification-content">
                  <span className="notification-source">
                    {t(alert.cameraName)}
                    <span>·</span>
                    {t(alert.location)}
                  </span>
                  <strong>{t(alert.event.type)}</strong>
                  <span className="notification-meta">
                    <span
                      className={`notification-read-state ${!alert.readAt ? "new" : ""}`}
                    >
                      {t(alert.readAt ? "Просмотрено" : "Новое")}
                    </span>
                    {alert.mode === "demo" && <span>{t("Демо")}</span>}
                  </span>
                </span>
                <Icon className="notification-arrow" name="arrow" size={18} />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="notification-empty">
          <span>{t("Оповещения")}</span>
          <h3>{t(emptyText)}</h3>
          <p>{t("Новые события появятся здесь, когда поступит сигнал от камеры.")}</p>
        </div>
      )}
      {selected && (
        <Modal
          title={t("Событие с камеры")}
          onClose={() => setSelectedId(null)}
          closeLabel={t("Закрыть")}
        >
          <div className="notification-detail">
            <div className="notification-detail-heading">
              <span>
                {t(selected.cameraName)} · {t(selected.location)}
              </span>
              <h3>{t(selected.event.type)}</h3>
              <time dateTime={selected.detectedAt}>
                {formatDate(selected.detectedAt, {
                  timeZone: "Asia/Almaty",
                  dateStyle: "long",
                  timeStyle: "short",
                })}
              </time>
            </div>
            {selected.mode === "demo" && (
              <p className="notification-demo-note">{t("Демонстрационное событие. Камера не подключена; изображение создано для примера интерфейса.")}</p>
            )}
            <div className="notification-detail-grid">
              <figure className="notification-evidence">
                {image && !imageFailed ? (
                  <img
                    src={image}
                    alt={t("Кадр события в {0}", [timecode(frame!.timestamp_sec)])}
                    onError={() => setImageFailed(true)}
                  />
                ) : selected.mode === "demo" ? (
                  <img
                    src="/images/demo-cash-desk.jpg"
                    alt={t("Синтетическая иллюстрация кассовой зоны")}
                  />
                ) : (
                  <div className="notification-no-frame">
                    {t(imageFailed
                      ? "Не удалось открыть кадр"
                      : "Кадры события пока не переданы")}
                  </div>
                )}
                <figcaption>
                  {t(selected.mode === "demo"
                    ? "Иллюстрация · не кадр с камеры"
                    : "Кадр с камеры")}
                  <span>
                    {timecode(
                      frame?.timestamp_sec ?? selected.event.timecode_sec,
                    )}
                  </span>
                </figcaption>
                {selected.event.evidence_frames.length > 1 && (
                  <div
                    className="notification-frame-picker"
                    aria-label={t("Кадры события")}
                  >
                    {selected.event.evidence_frames.map((item, index) => (
                      <button
                        key={index}
                        className="button button-outline"
                        aria-pressed={frameIndex === index}
                        onClick={() => {
                          setFrameIndex(index);
                          setImageFailed(false);
                        }}
                      >{t("Кадр ")}{index + 1} · {timecode(item.timestamp_sec)}
                      </button>
                    ))}
                  </div>
                )}
              </figure>
              <div className="notification-explanation">
                <h4>{t("Что заметила модель")}</h4>
                <p>{t(selected.event.description)}</p>
                <h4>{t("Основание для проверки")}</h4>
                {selected.event.rule ? (
                  <>
                    <p>
                      {t(selected.event.rule.title)}
                      {t(selected.event.rule.section
                        ? ` · ${selected.event.rule.section}`
                        : "")}
                    </p>
                    <p>{t(selected.event.rule.explanation)}</p>
                    {t(ruleUrl && (
                      <a
                        className="text-button"
                        href={ruleUrl}
                        target="_blank"
                        rel="noreferrer"
                      >{t("Открыть источник ")}<Icon name="external" size={14} />
                      </a>
                    ))}
                  </>
                ) : (
                  <p>{t("Нормативный источник не передан. Его нужно уточнить при проверке.")}</p>
                )}
                <div className="notification-human-note">{t("Событие отмечено как просмотренное. Наличие нарушения определяет специалист после проверки записи.")}</div>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
