import { useEffect, useRef, useState } from "react";
import { Icon } from "../../components/Icon";
import { Modal } from "../../components/Modal";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import {
  AnalysisRecord,
  fileSize,
  safeSourceUrl,
  timecode,
  Violation,
} from "./types";
import { DemoScene } from "./DemoScene";
import { StatusBadge } from "./HistoryTable";

function frameSource(base64: string): string | undefined {
  return base64 && /^[A-Za-z0-9+/=\s]+$/.test(base64)
    ? `data:image/jpeg;base64,${base64.replace(/\s/g, "")}`
    : undefined;
}

function exportReport(record: AnalysisRecord) {
  const report = {
    job_id: record.jobId || record.id,
    status: record.status,
    verdict: record.verdict,
    violations: record.violations,
    file_name: record.fileName,
    created_at: record.createdAt,
    mode: record.mode,
    notice:
      record.mode === "demo"
        ? "Демонстрационные данные. Видео не анализировалось."
        : "Результат требует проверки человеком.",
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `forte-report-${record.id}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function AnalysisDetail({
  record,
  onOpen,
  onNew,
}: {
  record: AnalysisRecord;
  onOpen: (id: string) => void;
  onNew: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [selected, setSelected] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [mediaError, setMediaError] = useState(false);
  const [largeFrame, setLargeFrame] = useState<{
    src: string;
    time: number;
  } | null>(null);
  const [largeDemo, setLargeDemo] = useState(false);
  const [retryError, setRetryError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const cancel = useAnalysisStore((state) => state.cancel);
  const retry = useAnalysisStore((state) => state.retry);
  const setDuration = useAnalysisStore((state) => state.setDuration);
  const busy = ["uploading", "processing"].includes(record.status);
  useEffect(() => {
    if (!busy) return;
    const update = () =>
      setElapsed(
        Math.floor((Date.now() - new Date(record.createdAt).getTime()) / 1000),
      );
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [record.createdAt, busy]);
  const goTo = (seconds: number) => {
    setCurrentTime(seconds);
    if (video.current) video.current.currentTime = seconds;
  };
  const selectEvent = (index: number) => {
    setSelected(index);
    goTo(record.violations[index].timecode_sec);
  };
  const event = record.violations[selected];
  const duration =
    record.duration ||
    Math.max(60, ...record.violations.map((item) => item.timecode_sec + 10));

  return (
    <div className="page-enter">
      <button className="back-link" onClick={onNew}>
        <Icon name="arrow" size={16} />К проверкам
      </button>
      <div className="page-title-row result-title">
        <div>
          <p className="eyebrow">РЕЗУЛЬТАТ ПРОВЕРКИ</p>
          <h1>{record.fileName}</h1>
          <p>
            {fileSize(record.fileSize)}
            {record.duration ? ` · ${timecode(record.duration)}` : ""} ·{" "}
            {new Date(record.createdAt).toLocaleString("ru-RU", {
              timeZone: "Asia/Almaty",
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </p>
        </div>
        {record.status === "done" && (
          <button
            className="button button-outline"
            onClick={() => exportReport(record)}
          >
            <Icon name="download" size={17} />
            Скачать JSON
          </button>
        )}
      </div>
      {record.mode === "demo" && (
        <div className="notice demo-notice">
          <Icon name="info" size={18} />
          <span>
            <strong>Демонстрационный результат.</strong> События заданы заранее
            и не относятся к содержимому выбранного видео. Изображения созданы
            для иллюстрации интерфейса.
          </span>
        </div>
      )}
      {busy ? (
        <section className="panel processing-panel" aria-live="polite">
          <div className="processing-orbit">
            <Icon name="scan" size={40} />
          </div>
          <span className="eyebrow">
            {record.mode === "demo" ? "ДЕМОНСТРАЦИЯ" : "ПРОВЕРКА В ПРОЦЕССЕ"}
          </span>
          <h2>
            {record.status === "uploading"
              ? "Загружаем видеозапись"
              : "Изучаем запись по кадрам"}
          </h2>
          <p>
            {record.stage ||
              "Сервис проверяет визуально наблюдаемые действия. Это может занять до 5 минут."}
          </p>
          <div
            className={`progress-track ${record.progress === undefined ? "indeterminate" : ""}`}
            role="progressbar"
            aria-label="Обработка видео"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={record.progress}
          >
            <span
              style={{
                width:
                  record.progress === undefined ? "35%" : `${record.progress}%`,
              }}
            />
          </div>
          <div className="processing-meta">
            <span>Прошло {timecode(elapsed)}</span>
            <span>
              {record.progress === undefined
                ? "Ожидаем результат"
                : `${record.progress}%`}
            </span>
          </div>
          <div className="processing-steps">
            <span>
              <Icon name="checkCircle" size={18} />
              Видео выбрано
            </span>
            <span className="active">
              <Icon name="scan" size={18} />
              Анализ событий
            </span>
            <span>
              <Icon name="file" size={18} />
              Отчёт
            </span>
          </div>
          <button
            className="button button-outline"
            onClick={() => cancel(record.id)}
          >
            Остановить ожидание
          </button>
          <small>
            Можно перейти в другой раздел. Проверка продолжится в этой вкладке.
          </small>
        </section>
      ) : ["failed", "cancelled"].includes(record.status) ? (
        <section className="panel empty-state error-state">
          <span className="state-icon">
            <Icon
              name={record.status === "failed" ? "alert" : "clock"}
              size={34}
            />
          </span>
          <h2>
            {record.status === "failed"
              ? "Проверка не завершена"
              : "Ожидание остановлено"}
          </h2>
          <p>
            {record.error ||
              "Получение результата остановлено в браузере. Если файл был отправлен, обработка на сервере может продолжаться."}
          </p>
          {retryError && (
            <p role="alert" className="inline-error">
              {retryError}
            </p>
          )}
          <div className="button-group">
            <button
              className="button button-primary"
              onClick={() => {
                try {
                  onOpen(retry(record.id));
                } catch (err) {
                  setRetryError(
                    err instanceof Error
                      ? err.message
                      : "Не удалось повторить проверку.",
                  );
                }
              }}
            >
              <Icon name="refresh" size={17} />
              Повторить проверку
            </button>
            <button className="button button-outline" onClick={onNew}>
              Выбрать другое видео
            </button>
          </div>
        </section>
      ) : (
        <>
          <section
            className={`verdict-banner ${record.verdict === "no_violation" ? "verdict-clear" : ""}`}
          >
            <span className="verdict-icon">
              <Icon
                name={record.verdict === "violation" ? "alert" : "checkCircle"}
                size={25}
              />
            </span>
            <div>
              <h2>
                {record.verdict === "violation"
                  ? "Обнаружены признаки возможных нарушений"
                  : "Нарушение не обнаружено"}
              </h2>
              <p>
                {record.verdict === "violation"
                  ? `Событий для проверки: ${record.violations.length}. Просмотрите фрагменты и оцените контекст.`
                  : "Сервис не отметил событий. Результат не исключает ошибок распознавания."}
              </p>
            </div>
            <StatusBadge record={record} />
          </section>
          <div className="result-grid">
            <div className="result-media-column">
              <section className="panel video-panel">
                <div className="section-heading">
                  <h2>
                    {record.videoUrl
                      ? "Видеозапись"
                      : "Демонстрация рабочего места"}
                  </h2>
                  <span className="small-label">
                    {record.videoUrl
                      ? "Исходный файл"
                      : "Синтетическая иллюстрация"}
                  </span>
                </div>
                <div className="video-stage">
                  {record.videoUrl ? (
                    <video
                      ref={video}
                      src={record.videoUrl}
                      controls
                      playsInline
                      preload="metadata"
                      onTimeUpdate={(event) =>
                        setCurrentTime(event.currentTarget.currentTime)
                      }
                      onLoadedMetadata={(event) =>
                        setDuration(record.id, event.currentTarget.duration)
                      }
                      onError={() => setMediaError(true)}
                      aria-label="Видеозапись кассовой операции"
                    />
                  ) : (
                    <DemoScene event={selected} />
                  )}
                </div>
                {mediaError && (
                  <p role="alert" className="media-warning">
                    Браузер не поддерживает кодек этого видео. Загрузка MOV в
                    API доступна; проверьте событие по кадрам ниже или откройте
                    оригинал в локальном плеере.
                  </p>
                )}
                <div className="timeline">
                  <div className="timeline-heading">
                    <span>
                      <Icon name="clock" size={14} />
                      Карта событий
                    </span>
                    <strong>
                      {timecode(currentTime)}{" "}
                      <span>
                        /{" "}
                        {record.duration
                          ? timecode(record.duration)
                          : "длительность неизвестна"}
                      </span>
                    </strong>
                  </div>
                  <div className="timeline-track">
                    <span
                      style={{
                        width: `${Math.min(100, (currentTime / duration) * 100)}%`,
                      }}
                    />
                    {record.violations.map((item, index) => (
                      <button
                        key={index}
                        className={`timeline-marker ${selected === index ? "active" : ""}`}
                        style={{
                          left: `${Math.min(97, (item.timecode_sec / duration) * 100)}%`,
                        }}
                        title={`${timecode(item.timecode_sec)} · ${item.type}`}
                        aria-label={`Перейти к событию ${index + 1}, ${timecode(item.timecode_sec)}`}
                        onClick={() => selectEvent(index)}
                      />
                    ))}
                  </div>
                  <div className="timeline-labels">
                    <span>00:00</span>
                    <span>
                      {record.duration ? timecode(record.duration) : "—"}
                    </span>
                  </div>
                </div>
              </section>
              {event && (
                <section className="panel evidence-panel">
                  <div className="section-heading">
                    <div>
                      <h2>Кадры-доказательства</h2>
                      <p>
                        Событие {selected + 1} · {timecode(event.timecode_sec)}
                      </p>
                    </div>
                    <Icon name="image" size={20} />
                  </div>
                  {event.evidence_frames.length ? (
                    <div className="evidence-grid">
                      {event.evidence_frames.map((frame, index) => {
                        const src = frameSource(frame.image_base64);
                        return src ? (
                          <button
                            className="evidence-frame"
                            key={index}
                            aria-label={`Увеличить кадр на ${timecode(frame.timestamp_sec)}`}
                            onClick={() =>
                              setLargeFrame({ src, time: frame.timestamp_sec })
                            }
                          >
                            <img
                              src={src}
                              alt={`Кадр события ${selected + 1} на ${timecode(frame.timestamp_sec)}`}
                              onError={(e) => {
                                e.currentTarget.alt =
                                  "Не удалось декодировать кадр JPEG";
                              }}
                            />
                            <span>
                              <Icon name="scan" size={13} />
                              {timecode(frame.timestamp_sec)}
                            </span>
                          </button>
                        ) : (
                          <p className="media-warning" key={index}>
                            Некорректный формат кадра {index + 1}.
                          </p>
                        );
                      })}
                    </div>
                  ) : record.mode === "demo" ? (
                    <div className="demo-evidence">
                      <button
                        className="evidence-frame"
                        onClick={() => setLargeDemo(true)}
                        aria-label="Увеличить демо-иллюстрацию"
                      >
                        <DemoScene event={selected} />
                        <span>
                          <Icon name="scan" size={13} />
                          Иллюстрация
                        </span>
                      </button>
                      <div>
                        <strong>Иллюстрация для демо</strong>
                        <p>
                          Изображение сгенерировано, это не кадр из записи.
                          Настоящие кадры появятся после подключения анализа.
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="evidence-empty">
                      <Icon name="image" size={28} />
                      <div>
                        <strong>Сервис не передал кадры</strong>
                        <p>
                          Кадры-доказательства обязательны по ТЗ. Результат
                          требует дополнения со стороны сервиса.
                        </p>
                      </div>
                    </div>
                  )}
                </section>
              )}
              <div className="review-note">
                <Icon name="shield" size={19} />
                <p>
                  Результат помогает проверить запись. Окончательный вывод
                  делает специалист с учётом контекста и применимых правил.
                </p>
              </div>
            </div>
            <section className="panel events-panel">
              <div className="section-heading">
                <h2>События</h2>
                <span className="count-pill">
                  {record.violations.length.toString().padStart(2, "0")}
                </span>
              </div>
              {record.violations.length ? (
                record.violations.map((item, index) => (
                  <EventCard
                    key={index}
                    event={item}
                    index={index}
                    selected={selected === index}
                    onSelect={() => selectEvent(index)}
                  />
                ))
              ) : (
                <div className="empty-state">
                  <Icon name="checkCircle" size={36} />
                  <h3>Событий не обнаружено</h3>
                  <p>
                    В отчёте нет фрагментов с признаками возможных нарушений.
                  </p>
                </div>
              )}
            </section>
          </div>
        </>
      )}
      {largeFrame && (
        <Modal
          title={`Кадр-доказательство · ${timecode(largeFrame.time)}`}
          wide
          onClose={() => setLargeFrame(null)}
        >
          <img
            className="full-evidence"
            src={largeFrame.src}
            alt={`Кадр-доказательство на ${timecode(largeFrame.time)}`}
          />
        </Modal>
      )}
      {largeDemo && (
        <Modal
          title="Демонстрационная иллюстрация"
          wide
          onClose={() => setLargeDemo(false)}
        >
          <DemoScene event={selected} />
          <p className="page-footnote">
            Иллюстрация интерфейса. Не является кадром-доказательством.
          </p>
        </Modal>
      )}
    </div>
  );
}

function EventCard({
  event,
  index,
  selected,
  onSelect,
}: {
  event: Violation;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const source = safeSourceUrl(event.rule?.url);
  return (
    <article className={`event-card ${selected ? "selected" : ""}`}>
      <button
        className="event-select"
        onClick={onSelect}
        aria-expanded={selected}
      >
        <span className="event-number">
          {(index + 1).toString().padStart(2, "0")}
        </span>
        <span>
          <span className="event-time">
            <Icon name="play" size={11} />
            {timecode(event.timecode_sec)}
          </span>
          <strong>{event.type}</strong>
        </span>
        <Icon name="down" size={17} />
      </button>
      {selected && (
        <div className="event-body">
          <p>{event.description}</p>
          <div className="rule-reference">
            <span className="rule-label">
              <Icon name="book" size={15} />
              Нормативное основание
            </span>
            {event.rule ? (
              <>
                <strong>{event.rule.title}</strong>
                <span>{event.rule.section || "Точный пункт не указан"}</span>
                {event.rule.explanation && <p>{event.rule.explanation}</p>}
                {source && (
                  <a
                    href={source}
                    target="_blank"
                    rel="noreferrer"
                    className="text-button"
                  >
                    Открыть источник
                    <Icon name="external" size={13} />
                  </a>
                )}
              </>
            ) : (
              <p>
                Сервис не передал нормативный источник. Для оценки события
                необходимо дополнить обоснование.
              </p>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
