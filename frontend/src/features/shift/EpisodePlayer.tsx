import { useEffect, useMemo, useRef, useState } from "react";
import { CameraAlert } from "../notifications/types";
import { timecode } from "../analysis/types";
import { useEpisodeMedia } from "./useEpisodeMedia";
import {
  clipBounds,
  EPISODE_SECONDS,
  frameSource,
  safeMediaUrl,
} from "./model";

export function EpisodeFrames({ alert }: { alert: CameraAlert }) {
  const [index, setIndex] = useState(0);
  const [failed, setFailed] = useState(false);
  const frame = alert.event.evidence_frames[index];
  const source =
    frameSource(frame?.image_base64) || safeMediaUrl(frame?.image_url);
  return (
    <div className="episode-frames">
      <div className="episode-image">
        {source && !failed ? (
          <img
            src={source}
            onError={() => setFailed(true)}
            alt={`Кадр события в ${timecode(frame.timestamp_sec)}`}
          />
        ) : alert.mode === "demo" ? (
          <img
            src="/images/demo-cash-desk.jpg"
            alt="Синтетическая иллюстрация кассы, не запись камеры"
          />
        ) : (
          <div className="episode-unavailable">
            <strong>
              {failed ? "Кадр не удалось открыть" : "Кадры не переданы"}
            </strong>
            <p>Описание события доступно рядом.</p>
          </div>
        )}
        <span className="episode-image-label">
          {alert.mode === "demo"
            ? "Демо · иллюстрация"
            : source && !failed
              ? `Кадр · ${timecode(frame.timestamp_sec)}`
              : "Нет изображения"}
        </span>
      </div>
      {alert.event.evidence_frames.length > 1 && (
        <div className="episode-frame-picker" aria-label="Кадры эпизода">
          {alert.event.evidence_frames.map((f, i) => (
            <button
              key={i}
              aria-pressed={index === i}
              onClick={() => {
                setIndex(i);
                setFailed(false);
              }}
            >
              {timecode(f.timestamp_sec)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function EpisodePlayer({
  alert,
  playing,
  onPause,
  onFinish,
}: {
  alert: CameraAlert;
  playing: boolean;
  onPause: () => void;
  onFinish: () => void;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const [duration, setDuration] = useState<number>();
  const [failed, setFailed] = useState(false);
  const [playError, setPlayError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const finished = useRef(false);
  const finishRef = useRef(onFinish);
  const pauseRef = useRef(onPause);
  finishRef.current = onFinish;
  pauseRef.current = onPause;
  const media = useEpisodeMedia(alert);
  const url = media.url;
  const declaredBounds = clipBounds(
    alert.event.timecode_sec,
    alert.recording?.durationSec || 0,
  );
  const actualBounds = useMemo(
    () =>
      duration === undefined
        ? undefined
        : clipBounds(alert.event.timecode_sec, duration),
    [duration, alert.event.timecode_sec],
  );
  const videoMode = Boolean(url && declaredBounds && !failed);
  const length = videoMode
    ? actualBounds
      ? actualBounds.end - actualBounds.start
      : declaredBounds!.end - declaredBounds!.start
    : EPISODE_SECONDS;

  useEffect(() => {
    const video = ref.current;
    if (!video || !actualBounds) return;
    let cancelled = false;
    if (playing) {
      setPlayError("");
      video.play()?.catch(() => {
        if (!cancelled) {
          setPlayError(
            "Не удалось начать воспроизведение. Нажмите «Смотреть», чтобы повторить.",
          );
          pauseRef.current();
        }
      });
    } else video.pause();
    return () => {
      cancelled = true;
      video.pause();
    };
  }, [playing, actualBounds]);

  useEffect(() => {
    if (!playing || videoMode || media.loading) return;
    const timer = window.setInterval(
      () => setElapsed((value) => Math.min(EPISODE_SECONDS, value + 0.25)),
      250,
    );
    return () => window.clearInterval(timer);
  }, [playing, videoMode, media.loading]);

  useEffect(() => {
    if (playing && elapsed >= length && !finished.current) {
      finished.current = true;
      finishRef.current();
    }
  }, [elapsed, length, playing]);

  return (
    <div className="episode-player">
      {media.loading ? (
        <p role="status">Подготовка видео…</p>
      ) : videoMode ? (
        <div className="episode-video-wrap">
          <video
            ref={ref}
            src={url}
            muted
            playsInline
            preload="metadata"
            aria-label="Фрагмент записи события"
            onLoadedMetadata={(e) => {
              const video = e.currentTarget;
              const bounds = clipBounds(
                alert.event.timecode_sec,
                video.duration,
              );
              if (!bounds) {
                setFailed(true);
                setElapsed(0);
                return;
              }
              video.currentTime = bounds.start;
              setDuration(video.duration);
            }}
            onTimeUpdate={(e) => {
              if (!actualBounds) return;
              const video = e.currentTarget;
              setElapsed(
                Math.max(
                  0,
                  Math.min(length, video.currentTime - actualBounds.start),
                ),
              );
              if (video.currentTime >= actualBounds.end) video.pause();
            }}
            onEnded={() => {
              if (playing && !finished.current) {
                finished.current = true;
                finishRef.current();
              }
            }}
            onError={() => {
              setFailed(true);
              setElapsed(0);
            }}
          />
          <span className="episode-image-label">
            {alert.mode === "demo" ? "Демо-видео" : "Фрагмент записи"} ·{" "}
            {timecode(actualBounds?.start ?? declaredBounds!.start)}–
            {timecode(actualBounds?.end ?? declaredBounds!.end)}
          </span>
        </div>
      ) : (
        <EpisodeFrames alert={alert} />
      )}
      <div className="episode-progress">
        <input
          type="range"
          aria-label="Позиция в эпизоде"
          min="0"
          max={length}
          step="0.1"
          value={Math.min(elapsed, length)}
          disabled={videoMode && !actualBounds}
          onChange={(e) => {
            const value = Number(e.target.value);
            finished.current = false;
            setElapsed(value);
            if (ref.current && actualBounds)
              ref.current.currentTime = actualBounds.start + value;
          }}
        />
        <span>
          {timecode(elapsed)} / {timecode(length)}
        </span>
      </div>
      <p className="episode-media-note">
        {media.error ||
          playError ||
          (videoMode
            ? "Короткий фрагмент вокруг события. Полная запись доступна в контексте."
            : failed || alert.recording
              ? "Видео недоступно или таймкод вне записи. Показаны доступные кадры и описание."
              : alert.mode === "demo"
                ? "Демо-подборка иллюстраций: по 10 секунд на эпизод. Это не видео с камеры."
                : "Видео не передано. Обзор показывает кадры и описание по 10 секунд.")}
      </p>
      {media.canRefresh && (
        <button
          className="text-button"
          disabled={media.loading}
          onClick={() => {
            onPause();
            setFailed(false);
            setDuration(undefined);
            setElapsed(0);
            finished.current = false;
            media.refresh();
          }}
        >
          Обновить ссылку на видео
        </button>
      )}
    </div>
  );
}

export function EpisodeContext({ alert }: { alert: CameraAlert }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const media = useEpisodeMedia(alert);
  const url = media.url;
  const bounds = clipBounds(
    alert.event.timecode_sec,
    alert.recording?.durationSec || 0,
    15,
    15,
  );
  const hasVideo = Boolean(url && bounds && !failed);
  return (
    <div className="episode-context">
      <p className="eyebrow">
        {alert.cameraName} · КОНТЕКСТ СОБЫТИЯ
        {alert.mode === "demo" && " · ДЕМО"}
      </p>
      <h3>{alert.event.type}</h3>
      {media.loading ? (
        <p role="status">Подготовка видео…</p>
      ) : hasVideo ? (
        <>
          <video
            ref={ref}
            controls
            playsInline
            preload="metadata"
            src={url}
            aria-label="Полная запись с контекстом"
            onLoadedMetadata={(e) => {
              const actual = clipBounds(
                alert.event.timecode_sec,
                e.currentTarget.duration,
                15,
                15,
              );
              if (actual) e.currentTarget.currentTime = actual.start;
              else setFailed(true);
            }}
            onError={() => setFailed(true)}
          />
          <div className="episode-context-toolbar">
            <p>
              Начинаем за 15 секунд до события, если запись позволяет. Можно
              просмотреть всю запись.
            </p>
            <button
              className="button button-outline"
              onClick={() => {
                if (ref.current)
                  ref.current.currentTime = alert.event.timecode_sec;
              }}
            >
              К событию · {timecode(alert.event.timecode_sec)}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="health-intro">
            {failed || alert.recording
              ? "Не удалось открыть видео. Доступные кадры показаны ниже."
              : "Видеоконтекст не передан. Здесь доступны только иллюстрации или кадры события."}
          </p>
          <EpisodeFrames alert={alert} />
        </>
      )}
      {media.error && <p role="alert">{media.error}</p>}
      {media.canRefresh && (
        <button
          className="text-button"
          disabled={media.loading}
          onClick={() => {
            setFailed(false);
            media.refresh();
          }}
        >
          Обновить ссылку на видео
        </button>
      )}
      <p>{alert.event.description}</p>
      {alert.event.rule && (
        <div className="episode-rule">
          <strong>Основание для проверки</strong>
          <p>
            {alert.event.rule.title}
            {alert.event.rule.section && ` · ${alert.event.rule.section}`}
          </p>
          <p>{alert.event.rule.explanation}</p>
        </div>
      )}
      <p className="notification-session-note">
        Вывод о нарушении принимает специалист после просмотра исходной записи.
      </p>
    </div>
  );
}
