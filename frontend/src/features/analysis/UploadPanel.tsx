import { DragEvent, useRef, useState } from "react";
import { Icon } from "../../components/Icon";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { fileSize, validateVideo } from "./types";

export function UploadPanel({ onOpen }: { onOpen: (id: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const mode = useAnalysisStore((state) => state.settings.mode);
  const start = useAnalysisStore((state) => state.start);
  const busy = useAnalysisStore((state) =>
    state.records.some((item) =>
      ["uploading", "processing"].includes(item.status),
    ),
  );
  const select = (files: FileList | null) => {
    if (!files?.length) return;
    if (files.length > 1) {
      setError("Для одной проверки выберите один видеофайл.");
      return;
    }
    const validation = validateVideo(files[0]);
    if (validation) {
      setError(validation);
      return;
    }
    setFile(files[0]);
    setError("");
  };
  const drop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    select(event.dataTransfer.files);
  };
  const run = (demo = false) => {
    try {
      onOpen(start(demo ? undefined : file || undefined));
      setError("");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Не удалось начать проверку.",
      );
    }
  };
  return (
    <section className="panel upload-panel" aria-labelledby="upload-title">
      <div className="section-heading">
        <div>
          <h2 id="upload-title">Добавьте запись с камеры</h2>
          <p>Загрузите запись работы кассира</p>
        </div>
        <span className="subtle-icon">
          <Icon name="video" size={21} />
        </span>
      </div>
      <input
        ref={input}
        type="file"
        id="video-file"
        className="visually-hidden"
        accept=".mov,.mp4,.webm,video/quicktime,video/mp4,video/webm"
        onChange={(event) => {
          select(event.target.files);
          event.target.value = "";
        }}
        aria-label="Выбрать видеофайл"
      />
      <div
        className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node))
            setDragging(false);
        }}
        onDrop={drop}
      >
        {file ? (
          <>
            <div className="upload-file-icon">
              <Icon name="video" size={29} />
            </div>
            <strong className="selected-filename">{file.name}</strong>
            <p>{fileSize(file.size)} · Готов к проверке</p>
            <button
              className="text-button"
              onClick={() => input.current?.click()}
            >
              Выбрать другой файл <Icon name="refresh" size={14} />
            </button>
          </>
        ) : (
          <>
            <div className="upload-file-icon">
              <Icon name="upload" size={29} />
            </div>
            <strong>Перетащите видео сюда</strong>
            <p>или выберите файл на устройстве</p>
            <button
              className="button button-outline"
              onClick={() => input.current?.click()}
            >
              <Icon name="plus" size={16} />
              Выбрать видео
            </button>
            <span className="file-hint">MOV, MP4, WebM · до 200 МБ</span>
          </>
        )}
      </div>
      {error && (
        <p role="alert" className="inline-error">
          <Icon name="alert" size={17} />
          {error}
        </p>
      )}
      <div className="upload-bottom">
        <span>
          <Icon name="lock" size={14} />
          {mode === "demo"
            ? "Файл остаётся в браузере"
            : "Обработка на сервере команды"}
        </span>
        <button
          className="button button-primary"
          disabled={!file || busy}
          onClick={() => run()}
        >
          {mode === "demo" ? "Запустить демо" : "Начать проверку"}
          <Icon name="arrow" size={17} />
        </button>
      </div>
      {mode === "demo" && (
        <p className="demo-upload-note">
          Демо показывает заранее заданный результат, без анализа содержимого
          видео.
        </p>
      )}
      {busy && (
        <p className="demo-upload-note">
          Дождитесь завершения текущей проверки или остановите ожидание на её
          странице.
        </p>
      )}
      <div className="demo-link-row">
        <span>Хотите сначала посмотреть, как это работает?</span>
        <button
          className="text-button"
          onClick={() => run(true)}
          disabled={busy}
        >
          <Icon name="play" size={13} />
          Открыть демо
        </button>
      </div>
    </section>
  );
}
