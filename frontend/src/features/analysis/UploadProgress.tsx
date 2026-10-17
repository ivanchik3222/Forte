import { UploadProgress as TransferProgress } from "../../api/client";
import { fileSize } from "./types";

export function uploadPercent(progress: TransferProgress): number | undefined {
  if (progress.transferred) return 100;
  if (!progress.total) return progress.loaded === 0 ? 0 : undefined;
  return Math.min(100, Math.floor((progress.loaded / progress.total) * 100));
}

export function UploadProgress({
  file,
  progress,
}: {
  file: File;
  progress: TransferProgress;
}) {
  const percent = uploadPercent(progress);
  const saving = progress.transferred;
  const label = saving ? "Сохраняем запись" : "Загружаем видео";
  const loaded = saving ? file.size : Math.min(file.size, progress.loaded);
  return (
    <div className={`transfer-card ${saving ? "is-saving" : ""}`}>
      <div className="transfer-file">
        <span className="transfer-format" aria-hidden="true">
          {file.name.split(".").pop()?.toUpperCase()}
        </span>
        <div>
          <strong title={file.name}>{file.name}</strong>
          <span>{fileSize(file.size)} · Ваша запись</span>
        </div>
        <span className="transfer-live" aria-hidden="true" />
      </div>
      <div className="transfer-body">
        <div
          className={`transfer-dial ${percent === undefined ? "is-indeterminate" : ""}`}
          role="progressbar"
          aria-label="Передача видео"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-valuetext={
            saving
              ? "Файл передан. Ожидаем сохранения на сервере."
              : percent === undefined
                ? `Передано ${fileSize(loaded)}`
                : `${percent}% · ${fileSize(loaded)} из ${fileSize(file.size)}`
          }
        >
          <svg viewBox="0 0 160 160" aria-hidden="true">
            <circle className="transfer-ring-track" cx="80" cy="80" r="69" />
            <circle
              className="transfer-ring-fill"
              cx="80"
              cy="80"
              r="69"
              pathLength="100"
              strokeDasharray={`${percent ?? 22} 100`}
            />
          </svg>
          <span className="transfer-orbit" aria-hidden="true" />
          <div className="transfer-number" aria-hidden="true">
            <strong>
              {percent ?? "…"}
              {percent !== undefined && <small>%</small>}
            </strong>
            <span>{saving ? "передано" : "загружено"}</span>
          </div>
        </div>
        <div className="transfer-copy">
          <span className="transfer-eyebrow">
            {saving ? "Последний шаг" : "Видео в пути"}
          </span>
          <div role="status" aria-live="polite">
            <h3>{label}</h3>
          </div>
          <p>
            {saving
              ? "Видео уже передано. Сервер проверяет файл и добавляет его в историю."
              : "Передаём запись в рабочее пространство. Пожалуйста, оставьте вкладку открытой."}
          </p>
          <div className="transfer-volume">
            <strong>{fileSize(loaded)}</strong>
            <span>из {fileSize(file.size)}</span>
          </div>
        </div>
      </div>
      <ol className="transfer-stages" aria-label="Этапы загрузки">
        <li
          className={saving ? "is-complete" : "is-current"}
          aria-current={!saving ? "step" : undefined}
        >
          <span aria-hidden="true">{saving ? "✓" : "01"}</span> Передача видео
        </li>
        <li
          className={saving ? "is-current" : ""}
          aria-current={saving ? "step" : undefined}
        >
          <span aria-hidden="true">02</span> Сохранение
        </li>
      </ol>
    </div>
  );
}
