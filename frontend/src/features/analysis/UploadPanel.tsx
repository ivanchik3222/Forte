import { t, useLocale } from "../../i18n";
import { DragEvent, useRef, useState } from "react";
import { Icon } from "../../components/Icon";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { fileSize, MAX_FILE_SIZE_LABEL, validateVideo } from "./types";

export function UploadPanel({ onOpen }: { onOpen: (id: string) => void }) {
  useLocale();
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
          <h2 id="upload-title">{t("Добавьте запись с камеры")}</h2>
          <p>{t("Загрузите запись работы кассира")}</p>
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
        aria-label={t("Выбрать видеофайл")}
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
            <p>{fileSize(file.size)}{t(" · Готов к проверке")}</p>
            <button
              className="text-button"
              onClick={() => input.current?.click()}
            >{t("Выбрать другой файл ")}<Icon name="refresh" size={14} />
            </button>
          </>
        ) : (
          <>
            <div className="upload-file-icon">
              <Icon name="upload" size={29} />
            </div>
            <strong>{t("Перетащите видео сюда")}</strong>
            <p>{t("или выберите файл на устройстве")}</p>
            <button
              className="button button-outline"
              onClick={() => input.current?.click()}
            >
              <Icon name="plus" size={16} />{t("Выбрать видео")}</button>
            <span className="file-hint">{t("MOV, MP4, WebM · до {0}", [MAX_FILE_SIZE_LABEL])}
            </span>
          </>
        )}
      </div>
      {t(error && (
        <p role="alert" className="inline-error">
          <Icon name="alert" size={17} />
          {t(error)}
        </p>
      ))}
      <div className="upload-bottom">
        <span>
          <Icon name="lock" size={14} />
          {t(mode === "demo"
            ? "Файл остаётся в браузере"
            : "Обработка на сервере команды")}
        </span>
        <button
          className="button button-primary"
          disabled={!file || busy}
          onClick={() => run()}
        >
          {t(mode === "demo" ? "Запустить демо" : "Начать проверку")}
          <Icon name="arrow" size={17} />
        </button>
      </div>
      {mode === "demo" && (
        <p className="demo-upload-note">{t("Демо показывает заранее заданный результат, без анализа содержимого видео.")}</p>
      )}
      {busy && (
        <p className="demo-upload-note">{t("Дождитесь завершения текущей проверки или остановите ожидание на её странице.")}</p>
      )}
      <div className="demo-link-row">
        <span>{t("Хотите сначала посмотреть, как это работает?")}</span>
        <button
          className="text-button"
          onClick={() => run(true)}
          disabled={busy}
        >
          <Icon name="play" size={13} />{t("Открыть демо")}</button>
      </div>
    </section>
  );
}
