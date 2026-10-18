import { LanguageSwitcher, LanguageSettings } from "../../components/LanguageSwitcher";
import { formatDate, localeCode, t, useLocale } from "../../i18n";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  apiRequest,
  mediaUrl,
  UploadProgress as TransferProgress,
} from "../../api/client";
import {
  Alert,
  Camera,
  asRecord,
  load,
  parseAlert,
  parseCamera,
  parseMedia,
  parseOverview,
  parsePage,
  parseSource,
} from "../../api/workspace";
import { LoginPanel } from "../../components/LoginPanel";
import { LoadingMark, LoadingState } from "../../components/LoadingState";
import { RegulatoryGuide } from "../../components/RegulatoryGuide";
import { Modal } from "../../components/Modal";
import { MobileNavigation, SidebarAccount, WorkspacePage } from "../../components/WorkspaceNavigation";
import { Icon, IconName } from "../../components/Icon";
import { useAuthStore } from "../../store/useAuthStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import {
  fileSize,
  MAX_FILE_SIZE_LABEL,
  safeSourceUrl,
  timecode,
  validateVideo,
} from "../analysis/types";
import { HistoryTable } from "../analysis/HistoryTable";
import { useEvidencePlayback } from "../analysis/useEvidencePlayback";
import { intervalTime } from "../analysis/playback";
import { MLAnalysisPanel } from "../analysis/MLAnalysisPanel";
import { UploadProgress, uploadPercent } from "../analysis/UploadProgress";
import { useCurrentDay } from "../notifications/types";
import { useResource } from "./useResource";
import { MonitoringPage } from "../../pages/MonitoringPage";
import { ShiftPage } from "../../pages/ShiftPage";

const navigation: { path: string; label: string; icon: IconName }[] = [
  { path: "/workspace", label: "Обзор", icon: "grid" },
  { path: "/notifications", label: "Оповещения", icon: "bell" },
  { path: "/shift", label: "Смена за минуту", icon: "play" },
  { path: "/monitoring", label: "Контроль камер", icon: "eye" },
  { path: "/history", label: "История записей", icon: "history" },
  { path: "/sources", label: "Нормативная база", icon: "book" },
  { path: "/settings", label: "Настройки", icon: "settings" },
];
const message = (e: unknown) =>
  e instanceof TypeError
    ? "Нет связи с сервером."
    : e instanceof Error
      ? e.message
      : "Ошибка запроса.";
const dateTime = (v: string) =>
  formatDate(v, {
    timeZone: "Asia/Almaty",
    dateStyle: "medium",
    timeStyle: "short",
  });

function StateNotice({
  error,
  loading,
  retry,
  data,
  loadingLabel = "Загружаем данные…",
  loadingLayout = "panel",
}: {
  error?: string;
  loading?: boolean;
  retry?: () => void;
  data?: unknown;
  loadingLabel?: string;
  loadingLayout?: "panel" | "inline" | "records";
}) {
  useLocale();
  return (
    <>
      {loading && !error && <LoadingState label={data === undefined ? loadingLabel : "Обновляем данные…"} variant={data === undefined ? loadingLayout : "inline"} />}
      {t(error && (
        <div className="notice" role="alert">
          <span>{t(error)}</span>
          {retry && (
            <button className="text-button" onClick={retry}>{t("Повторить")}</button>
          )}
        </div>
      ))}
    </>
  );
}
function Pager({
  page,
  total,
  perPage = 20,
  onPage,
}: {
  page: number;
  total: number;
  perPage?: number;
  onPage: (page: number) => void;
}) {
  useLocale();
  return (
    <div className="table-toolbar">
      <span>{t("Всего: ")}{total}{t(" · Страница ")}{page}
      </span>
      <button
        className="button button-outline"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >{t("Назад")}</button>
      <button
        className="button button-outline"
        disabled={page * perPage >= total}
        onClick={() => onPage(page + 1)}
      >{t("Далее")}</button>
    </div>
  );
}

export function LiveWorkspace() {
  useLocale();
  const auth = useAuthStore();
  const { pathname } = useLocation();
  useEffect(() => {
    void useAuthStore.getState().restore();
  }, []);
  if (!auth.initialized)
    return (
      <main className="main-content">
        <StateNotice loading />
      </main>
    );
  if (!auth.user)
    return (
      <main className="main-content">
        <Link to="/" className="back-link">{t("← На главную")}</Link>
        <LoginPanel />
        <button
          className="button button-outline"
          onClick={() =>
            useAnalysisStore
              .getState()
              .setSettings({ mode: "demo", apiKey: "" })
          }
        >{t("Открыть демонстрацию без входа")}</button>
      </main>
    );
  if (pathname === "/login") return <Navigate to="/workspace" replace />;
  return <AuthenticatedWorkspace key={auth.user.id} />;
}

function AuthenticatedWorkspace() {
  useLocale();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const today = useCurrentDay();
  const overview = useResource(`/overview?date=${today}`, parseOverview, true);
  const [modal, setModal] = useState<"upload" | "account" | null>(null);
  const [revision, setRevision] = useState(0);
  const changed = () => {
    setRevision((x) => x + 1);
    overview.refresh();
  };
  const active = pathname.startsWith("/analysis/") ? "/history" : pathname;
  const open = (id: string) => navigate(`/analysis/${id}`);
  return (
    <div className="app-shell live-workspace">
      <a className="skip-link" href="#main-content">{t("Перейти к содержимому")}</a>
      <aside className="sidebar" aria-label={t("Основная навигация")}>
        <Link className="brand" to="/">
          <img src="/forte-logo.svg" width="112" height="34" alt="Forte" />
          <span className="brand-divider" />
          <span>control</span>
        </Link>
        <div className="workspace-label">
          <Icon name="shield" />
          <div>
            <strong>{t("Кассовый контроль")}</strong>
            <span>{t("Рабочее пространство")}</span>
          </div>
        </div>
        <nav>
          {navigation.filter(n => n.path !== "/settings").map((n) => (
            <Link
              className={`nav-item ${active === n.path ? "active" : ""}`}
              aria-current={active === n.path ? "page" : undefined}
              to={n.path}
              key={n.path}
            >
              <Icon name={n.icon} />
              <span>{t(n.label)}</span>
              {n.path === "/notifications" && (
                <span className="nav-count">
                  {t(overview.data?.unread_total ?? "—")}
                </span>
              )}
              {n.path === "/history" && (
                <span className="nav-count">
                  {t(overview.data?.media_total ?? "—")}
                </span>
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <span className="local-card-icon"><Icon name="shield" /></span>
            <strong>{t("Записи на сервере команды")}</strong>
            <p>{t("Видео сохраняются и автоматически отправляются на локальный анализ.")}</p>
          </div>
          <Link to="/settings" className={`nav-item ${active === "/settings" ? "active" : ""}`} aria-current={active === "/settings" ? "page" : undefined}>
            <Icon name="settings" size={19} /><span>{t("Настройки")}</span>
          </Link>
          <SidebarAccount onOpen={() => setModal("account")} />
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <Link className="mobile-brand" to="/">
            <img src="/forte-logo.svg" width="76" height="23" alt="Forte" />
          </Link>
          <div className="breadcrumbs">
            {t(navigation.find((n) => n.path === active)?.label || "Видеозапись")}
          </div>
          <div className="topbar-actions">
            <LanguageSwitcher />
            <Link className="mode-badge mode-api" to="/settings">{t("Рабочий режим")}</Link>
            <button
              className="profile-button workspace-profile-top"
              aria-label={t("Открыть профиль")}
              onClick={() => setModal("account")}
            >
              <span className="avatar"><Icon name="user" size={18} /></span>
              <span>{user.full_name || user.nickname || user.email}</span>
            </button>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
          <WorkspacePage>
          <StateNotice error={overview.error} retry={overview.refresh} />
          {pathname === "/workspace" && (
            <>
              <div className="page-title-row overview-intro">
                <div>
                  <p className="eyebrow">{t(today)}</p>
                  <h1>{t("Контроль кассовых операций")}</h1>
                  <p>{t("Сохранённые видео и события для просмотра")}</p>
                </div>
                <button
                  className="button button-primary"
                  onClick={() => setModal("upload")}
                >
                  <Icon name="plus" />{t("Загрузить видео")}</button>
              </div>
              <StateNotice loading={overview.loading} />
              {overview.data && (
                <>
                  <section className="monitoring-summary">
                    <div className="monitoring-summary-copy">
                      <h2>{t("События за сегодня")}</h2>
                      <Link className="monitoring-link" to="/notifications">{t("Открыть оповещения")}<Icon name="arrow" size={18} /></Link>
                    </div>
                    <dl className="monitoring-totals">
                      <div>
                        <dt>{t("Всего событий")}</dt>
                        <dd>{overview.data.today_total}</dd>
                      </div>
                      <div>
                        <dt>{t("Просмотрено")}</dt>
                        <dd>{overview.data.today_read}</dd>
                      </div>
                      <div>
                        <dt>{t("Новых")}</dt>
                        <dd>{overview.data.today_unread}</dd>
                      </div>
                    </dl>
                  </section>
                  {overview.data.monitoring_summary && (
                    <section className="panel observation-card" aria-labelledby="observation-title">
                      <div className="observation-heading">
                        <span className="observation-icon"><Icon name="eye" size={23} /></span>
                        <div><h2 id="observation-title">{t("Доступность наблюдения")}</h2></div>
                      </div>
                      <dl className="observation-metrics">
                        <div><dt>{t("Камер с проблемами")}</dt><dd>{overview.data.monitoring_summary.problems}</dd></div>
                        <div><dt>{t("Без свежих проверок")}</dt><dd>{overview.data.monitoring_summary.unknown}</dd></div>
                        <div><dt>{t("Перерывы за день")}</dt><dd>{overview.data.monitoring_summary.unavailable_minutes.toLocaleString(localeCode(), { maximumFractionDigits: 1 })}<small>{t("камера·мин.")}</small></dd></div>
                      </dl>
                      <div className="observation-actions">
                        <Link className="button button-outline" to="/monitoring">{t("Проверить камеры")}<Icon name="arrow" size={17} /></Link>
                        <Link className="button button-outline" to="/shift"><Icon name="play" size={16} />{t("Смена за минуту")}</Link>
                      </div>
                    </section>
                  )}
                  <section className="panel">
                    <h2>{t("Последние события")}</h2>
                    <AlertList
                      alerts={overview.data.recent_alerts}
                      changed={changed}
                    />
                  </section>
                  <section className="panel history-panel">
                    <h2>{t("Последние записи")}</h2>
                    <HistoryTable
                      records={overview.data.recent_media.map(asRecord)}
                      onOpen={open}
                      serverManaged
                    />
                  </section>
                </>
              )}
              <CameraList />
            </>
          )}
          {pathname === "/history" && (
            <History
              key={revision}
              open={open}
              onNew={() => setModal("upload")}
            />
          )}
          {pathname.startsWith("/analysis/") && (
            <MediaDetail
              key={pathname}
              id={pathname.slice("/analysis/".length)}
            />
          )}
          {pathname === "/notifications" && <Notifications changed={changed} />}
          {pathname === "/monitoring" && <MonitoringPage live />}
          {pathname === "/shift" && <ShiftPage live onChanged={changed} />}
          {pathname === "/sources" && <Sources />}
          {pathname === "/settings" && <Settings />}
          {!navigation.some((n) => n.path === pathname) &&
            !pathname.startsWith("/analysis/") && (
              <section className="panel empty-state">
                <h1>{t("Страница не найдена")}</h1>
                <Link to="/workspace">{t("Вернуться к обзору")}</Link>
              </section>
            )}
          </WorkspacePage>
        </main>
        <footer className="app-footer">{t("Forte Control · Локальный анализ видео")}</footer>
      </div>
      <MobileNavigation unread={overview.data?.unread_total || 0} onAccount={() => setModal("account")} />
      {modal === "account" && (
        <Modal title={t("Учётная запись")} onClose={() => setModal(null)}>
          <LoginPanel />
          <StateNotice error={useAuthStore.getState().error || undefined} />
        </Modal>
      )}
      <UploadDialog
        visible={modal === "upload"}
        reopen={() => setModal("upload")}
        close={() => setModal(null)}
        saved={(id) => {
          setModal(null);
          changed();
          open(id);
        }}
      />
    </div>
  );
}

function UploadDialog({
  visible,
  reopen,
  close,
  saved,
}: {
  visible: boolean;
  reopen: () => void;
  close: () => void;
  saved: (id: string) => void;
}) {
  useLocale();
  const [file, setFile] = useState<File>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<TransferProgress>({
    loaded: 0,
    transferred: false,
  });
  const [dragging, setDragging] = useState(false);
  const key = useRef("");
  const controller = useRef<AbortController | undefined>(undefined);
  useEffect(() => () => controller.current?.abort(), []);
  const select = (files: FileList | null) => {
    if (busy || !files?.length) return;
    const validation =
      files.length !== 1 ? "Выберите один файл." : validateVideo(files[0]);
    if (validation) {
      setError(validation);
      return;
    }
    setFile(files[0]);
    key.current = crypto.randomUUID
      ? crypto.randomUUID()
      : Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
          b.toString(16).padStart(2, "0"),
        ).join("");
    setError("");
  };
  const upload = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError("");
    setProgress({ loaded: 0, transferred: false });
    controller.current = new AbortController();
    const body = new FormData();
    body.append("file", file);
    try {
      const record = parseMedia(
        await apiRequest("/api/v1/media", {
          method: "POST",
          body,
          signal: controller.current.signal,
          headers: { "Idempotency-Key": key.current },
          onUploadProgress: setProgress,
        }),
      );
      setFile(undefined);
      saved(record.id);
    } catch (e) {
      setError(
        e instanceof DOMException && e.name === "AbortError"
          ? "Ожидание остановлено. Файл мог сохраниться: повторите отправку с тем же файлом или проверьте историю."
          : t("{0} Можно повторить отправку — сохранённая запись не продублируется.", [message(e)]),
      );
    } finally {
      setBusy(false);
      controller.current = undefined;
    }
  };
  if (!visible)
    return file && (busy || error) ? (
      <button className="transfer-mini" onClick={reopen}>
        <span className="transfer-mini-value">
          {t(error
            ? "!"
            : `${uploadPercent(progress) ?? "…"}${uploadPercent(progress) !== undefined ? "%" : ""}`)}
        </span>
        <span>
          <strong>
            {t(error
              ? "Не удалось загрузить видео"
              : progress.transferred
                ? "Сохраняем запись"
                : "Загружаем видео")}
          </strong>
          <small>{file.name}</small>
        </span>
        <Icon name="arrow" size={18} />
      </button>
    ) : null;
  return (
    <Modal title={t("Загрузить видео")} onClose={close}>
      <section className="upload-panel live-upload-panel">
        {!busy && (
          <p>{t("После загрузки автоматически начнётся анализ. Эпизоды, описания действий и кадры появятся на странице записи.")}</p>
        )}
        {busy && file ? (
          <UploadProgress file={file} progress={progress} />
        ) : (
          <div
            className={`dropzone ${dragging ? "dragging" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              select(e.dataTransfer.files);
            }}
          >
            <Icon name="upload" size={32} />
            <label className="button button-outline">{t("Выбрать видео")}<input
                aria-label={t("Выбрать видеофайл")}
                type="file"
                className="visually-hidden"
                accept=".mov,.mp4,.webm"
                disabled={busy}
                onChange={(e) => {
                  select(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
            <p className="selected-filename">
              {t(file
                ? `${file.name} · ${fileSize(file.size)}`
                : t("Перетащите один MOV, MP4 или WebM до {0}", [MAX_FILE_SIZE_LABEL]))}
            </p>
          </div>
        )}
        <StateNotice error={error} />
        <div className="settings-save">
          {!busy && (
            <button
              className="button button-primary"
              disabled={!file || busy}
              onClick={() => void upload()}
            >{t("Сохранить видео")}</button>
          )}
          {busy && (
            <button
              className="button button-outline"
              onClick={() => controller.current?.abort()}
            >
              {t(progress.transferred
                ? "Остановить ожидание"
                : "Отменить загрузку")}
            </button>
          )}
        </div>
        {busy && (
          <p className="transfer-hint">{t("Окно можно свернуть — загрузка продолжится. Оставьте вкладку открытой до завершения.")}</p>
        )}
      </section>
    </Modal>
  );
}

function History({
  open,
  onNew,
}: {
  open: (id: string) => void;
  onNew: () => void;
}) {
  useLocale();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("newest");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);
  const resource = useResource(
    `/media?${new URLSearchParams({ search: query, sort, status, page: String(page) })}`,
    (v) => parsePage(v, parseMedia),
  );
  return (
    <>
      <div className="page-title-row">
        <div>
          <h1>{t("История записей")}</h1>
          <p>{t("Видео сохраняются на сервере и доступны после обновления страницы.")}</p>
        </div>
        <button className="button button-primary" onClick={onNew}>{t("Загрузить видео")}</button>
      </div>
      <section className="panel history-panel">
        <div className="table-toolbar">
          <input
            aria-label={t("Поиск по имени файла")}
            className="search-input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("Имя файла")}
          />
          <select
            aria-label={t("Статус записи")}
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="all">{t("Все статусы")}</option>
            <option value="stored">{t("Сохранённые записи")}</option>
          </select>
          <select
            aria-label={t("Сортировка")}
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setPage(1);
            }}
          >
            <option value="newest">{t("Сначала новые")}</option>
            <option value="oldest">{t("Сначала старые")}</option>
          </select>
        </div>
        <StateNotice {...resource} retry={resource.refresh} loadingLabel="Загружаем записи…" loadingLayout="records" />
        {resource.data && (
          <>
            <HistoryTable
              records={resource.data.items.map(asRecord)}
              onOpen={open}
              full
              serverManaged
            />
            <Pager page={page} total={resource.data.total} onPage={setPage} />
          </>
        )}
      </section>
    </>
  );
}

function MediaDetail({ id }: { id: string }) {
  useLocale();
  const record = useResource(`/media/${encodeURIComponent(id)}`, parseMedia);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [unplayable, setUnplayable] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const playback = useEvidencePlayback();
  const { video, resumeAt } = playback;
  const refreshUrl = async () => {
    if (preparing) return;
    setPreparing(true);
    try {
      resumeAt.current = video.current?.currentTime || 0;
      const result = await apiRequest<{ url: string; expires_in: number }>(
        `/api/v1/media/${encodeURIComponent(id)}/playback-url`,
        { method: "POST" },
      );
      setUrl(mediaUrl(result.url));
      setError("");
      setUnplayable(false);
    } catch (e) {
      setError(message(e));
    } finally {
      setPreparing(false);
    }
  };
  useEffect(() => {
    if (record.data) void refreshUrl();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record.data?.id]);
  const downloadReport = async () => {
    if (downloading) return;
    setDownloading(true);
    try {
      const report = await apiRequest(
        `/api/v1/media/${encodeURIComponent(id)}/report`,
      );
      const blob = URL.createObjectURL(
        new Blob([JSON.stringify(report, null, 2)], {
          type: "application/json",
        }),
      );
      const a = document.createElement("a");
      a.href = blob;
      a.download = `forte-report-${id}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(blob), 1000);
    } catch (e) {
      setError(message(e));
    } finally {
      setDownloading(false);
    }
  };
  return (
    <>
      <Link to="/history" className="back-link">{t("← К записям")}</Link>
      <StateNotice {...record} retry={record.refresh} />
      {record.data && (
        <>
          <div className="page-title-row">
            <div>
              <h1>{t(record.data.file_name)}</h1>
              <p>
                {fileSize(record.data.file_size)} ·{" "}
                {t(dateTime(record.data.created_at))}
                {t(record.data.duration_sec
                  ? ` · ${timecode(record.data.duration_sec)}`
                  : "")}
              </p>
            </div>
            <button
              className="button button-outline"
              disabled={downloading}
              onClick={() => void downloadReport()}
            >{downloading && <LoadingMark small />}{t(downloading ? "Готовим JSON…" : "Скачать JSON")}</button>
          </div>
          <section className="panel live-video" ref={playback.panel} tabIndex={-1} aria-label={t("Исходная видеозапись")}>
            <div className="video-panel-heading"><div><p className="eyebrow">{t("ИСХОДНАЯ ЗАПИСЬ")}</p><h2>{t("Просмотр видео")}</h2></div><Icon name="video" size={25} /></div>
            {playback.range && <div className="video-selected-range" role="status"><span><Icon name="play" size={17} /><strong>{intervalTime(playback.range.start, playback.range.end)}</strong> {playback.range.label}</span><button className="text-button" onClick={() => playback.seek(playback.range!.start, playback.range!)}>{t("Повторить фрагмент")}</button><button className="text-button" onClick={playback.clearRange}>{t("Смотреть всё видео")}</button></div>}
            <StateNotice error={error} />
            {preparing && <LoadingState label="Подготовка видео…" variant={url ? "inline" : "panel"} />}
            {t(url && (
              <video
                ref={video}
                controls
                playsInline
                preload="metadata"
                src={url}
                onLoadedMetadata={playback.onLoadedMetadata}
                onTimeUpdate={playback.onTimeUpdate}
                onSeeking={playback.onSeeking}
                onPlay={playback.onPlay}
                onError={() => setUnplayable(true)}
                style={{
                  width: "100%",
                  maxHeight: "65vh",
                  background: "#171217",
                }}
              />
            ))}
            {playback.playBlocked && <p role="status">{t("Нажмите ▶ в плеере, чтобы воспроизвести выбранный фрагмент.")}</p>}
            {unplayable && (
              <p role="alert">{t("Браузер не смог воспроизвести видео. Обновите ссылку или скачайте оригинал; кодек MOV может не поддерживаться.")}</p>
            )}
            <div className="settings-save">
              <button
                className="button button-outline"
                disabled={preparing}
                onClick={() => void refreshUrl()}
              >{preparing && <LoadingMark small />}{t("Обновить ссылку на видео")}</button>
              {t(url && (
                <a
                  className="button button-outline"
                  href={`${url}&download=1`}
                  referrerPolicy="no-referrer"
                >{t("Скачать оригинал")}</a>
              ))}
            </div>
          </section>
          <MLAnalysisPanel
            key={id}
            mediaId={id}
            context={{ fileName: record.data.file_name, uploadedAt: record.data.created_at, duration: record.data.duration_sec }}
            onSeek={playback.seek}
          />
        </>
      )}
    </>
  );
}

function AlertList({
  alerts,
  changed,
}: {
  alerts: Alert[];
  changed: () => void;
}) {
  useLocale();
  const [selected, setSelected] = useState<Alert>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const select = async (id: string) => {
    setLoading(true);
    setError("");
    setSelected(undefined);
    try {
      const alert = await load(`/notifications/${id}`, parseAlert);
      setSelected(alert);
      const result = await apiRequest<{
        items: { id: string; read_at: string }[];
      }>("/api/v1/notifications/read", {
        method: "POST",
        body: JSON.stringify({ ids: [id] }),
      });
      setSelected({ ...alert, read_at: result.items[0].read_at });
      changed();
    } catch (e) {
      setError(message(e));
    } finally {
      setLoading(false);
    }
  };
  return (
    <>
      <StateNotice loading={loading} error={error} />
      {alerts.length ? (
        <ul className="notification-feed" aria-label={t("События с камер")}>
          {alerts.map((a) => (
            <li key={a.id}>
              <button
                className={`notification-row ${!a.read_at ? "is-unread" : ""}`}
                onClick={() => void select(a.id)}
              >
                <time className="notification-time">
                  {new Date(a.detected_at).toLocaleTimeString(localeCode(), {
                    timeZone: "Asia/Almaty",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </time>
                <span className="notification-content">
                  <span className="notification-source">
                    {t(a.camera_name)} · {t(a.location)}
                  </span>
                  <strong>{t(a.event.type)}</strong>
                  <span className="notification-meta">
                    {t(a.read_at ? "Просмотрено" : "Новое")}
                    {t(a.source === "test" ? " · Тестовое событие" : "")}
                  </span>
                </span>
                <Icon name="arrow" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="notification-empty">
          <h3>{t("Событий пока нет")}</h3>
          <p>{t("Для выбранных условий события не поступали. Доступность наблюдения можно проверить в контроле камер.")}</p>
        </div>
      )}
      {selected && (
        <Modal title={t("Событие с камеры")} onClose={() => setSelected(undefined)}>
          <h3>{t(selected.event.type)}</h3>
          <p>
            {t(selected.camera_name)} · {t(selected.location)} ·{" "}
            {t(dateTime(selected.detected_at))}
          </p>
          {selected.source === "test" && (
            <div className="notice">{t("Тестовое событие. Это не результат наблюдения или ИИ-анализа.")}</div>
          )}
          <p>{t(selected.event.description)}</p>
          {selected.event.evidence_frames.length ? (
            selected.event.evidence_frames.map((f, i) => (
              <figure key={i}>
                <img
                  style={{ maxWidth: "100%" }}
                  src={mediaUrl(f.image_url)}
                  alt={t("Кадр {0}", [timecode(f.timestamp_sec)])}
                  referrerPolicy="no-referrer"
                />
                <figcaption>{timecode(f.timestamp_sec)}</figcaption>
              </figure>
            ))
          ) : (
            <p>{t("Кадры не переданы.")}</p>
          )}
          {selected.event.rule ? (
            <div>
              <h4>{t(selected.event.rule.title)}</h4>
              <p>{t(selected.event.rule.section)}</p>
              <p>{t(selected.event.rule.explanation)}</p>
              {t(safeSourceUrl(selected.event.rule.url) && (
                <a
                  href={safeSourceUrl(selected.event.rule.url)}
                  target="_blank"
                  rel="noreferrer"
                >{t("Открыть источник")}</a>
              ))}
            </div>
          ) : (
            <p>{t("Нормативное основание не передано.")}</p>
          )}
          <p>
            {t(selected.read_at
              ? "Просмотр сохранён."
              : "Отметка просмотра не сохранена.")}{" "}{t("Наличие нарушения определяет специалист.")}</p>
          <StateNotice error={error} />
        </Modal>
      )}
    </>
  );
}

function Notifications({ changed }: { changed: () => void }) {
  useLocale();
  const today = useCurrentDay();
  const [selectedDay, setDay] = useState("");
  const day = selectedDay || today;
  const [camera, setCamera] = useState("");
  const [read, setRead] = useState("all");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [cameraPage, setCameraPage] = useState(1);
  const [cameraOptions, setCameraOptions] = useState<Camera[]>([]);
  const cameras = useResource(`/cameras?per_page=100&page=${cameraPage}`, (v) =>
    parsePage(v, parseCamera),
  );
  useEffect(() => {
    if (cameras.data)
      setCameraOptions((previous) =>
        Array.from(
          new Map(
            [...previous, ...cameras.data!.items].map((item) => [
              item.id,
              item,
            ]),
          ).values(),
        ),
      );
  }, [cameras.data]);
  useEffect(() => setPage(1), [day]);
  const resource = useResource(
    `/notifications?${new URLSearchParams({ date: day, camera_id: camera, read, page: String(page) })}`,
    (v) => parsePage(v, parseAlert),
    true,
  );
  const updated = () => {
    resource.refresh();
    changed();
  };
  const bulk = async () => {
    try {
      await apiRequest("/api/v1/notifications/read", {
        method: "POST",
        body: JSON.stringify({
          ids:
            resource.data?.items.filter((a) => !a.read_at).map((a) => a.id) ||
            [],
        }),
      });
      setError("");
      updated();
    } catch (e) {
      setError(message(e));
    }
  };
  return (
    <>
      <div className="page-title-row">
        <div>
          <h1>{t("Оповещения")}</h1>
          <p>{t("Просмотр события не подтверждает нарушение.")}</p>
        </div>
      </div>
      <div className="notice">{t("События поступают от подключённого источника или специалиста. Тестовые события отмечены отдельно.")}</div>
      <section className="panel">
        <div className="table-toolbar">
          <input
            aria-label={t("День событий")}
            type="date"
            value={day}
            onChange={(e) => {
              setDay(e.target.value);
              setPage(1);
            }}
          />
          <select
            aria-label={t("Камера")}
            value={camera}
            onChange={(e) => {
              setCamera(e.target.value);
              setPage(1);
            }}
          >
            <option value="">{t("Все камеры")}</option>
            {cameraOptions.map((c) => (
              <option key={c.id} value={c.id}>
                {t(c.name)}
              </option>
            ))}
          </select>
          {cameras.data && cameraPage * 100 < cameras.data.total && (
            <button
              className="text-button"
              disabled={cameras.loading}
              onClick={() => setCameraPage((p) => p + 1)}
            >{t("Загрузить ещё камеры")}</button>
          )}
          <select
            aria-label={t("Просмотр событий")}
            value={read}
            onChange={(e) => {
              setRead(e.target.value);
              setPage(1);
            }}
          >
            <option value="all">{t("Все")}</option>
            <option value="new">{t("Новые")}</option>
            <option value="read">{t("Просмотрены")}</option>
          </select>
          <button
            className="button button-outline"
            disabled={!resource.data?.items.some((a) => !a.read_at)}
            onClick={() => void bulk()}
          >{t("Отметить показанные")}</button>
        </div>
        <StateNotice error={error || cameras.error} />
        <StateNotice {...resource} retry={resource.refresh} />
        {resource.data && (
          <>
            <AlertList alerts={resource.data.items} changed={updated} />
            <Pager page={page} total={resource.data.total} onPage={setPage} />
          </>
        )}
      </section>
    </>
  );
}

function CameraList() {
  useLocale();
  const [page, setPage] = useState(1);
  const resource = useResource(`/cameras?page=${page}`, (v) =>
    parsePage(v, parseCamera),
  );
  return (
    <section className="panel">
      <h2>{t("Камеры")}</h2>
      <StateNotice {...resource} retry={resource.refresh} />
      {resource.data && (
        <>
          {resource.data.items.map((c) => (
            <div className="notification-row" key={c.id}>
              <span>
                {t(c.name)} · {t(c.location)}
              </span>
              <span>
                {t(c.status === "unknown"
                  ? "Не подключена"
                  : c.status === "online"
                    ? "Есть связь"
                    : "Нет связи")}
              </span>
            </div>
          ))}
          {!resource.data.items.length && (
            <p>{t("Камеры ещё не добавлены администратором.")}</p>
          )}
          <Pager page={page} total={resource.data.total} onPage={setPage} />
        </>
      )}
    </section>
  );
}
function Sources() {
  useLocale();
  const [page, setPage] = useState(1);
  const resource = useResource(`/sources?page=${page}`, (v) =>
    parsePage(v, parseSource),
  );
  return (
    <RegulatoryGuide>
      <section className="regulatory-server-sources panel">
        <h2>{t("Источники, добавленные в кабинет")}</h2>
        <p>{t("Справочник сервера может содержать дополнительные документы. Их наличие в списке не включает новые правила в модель.")}</p>
        <StateNotice {...resource} retry={resource.refresh} />
        {resource.data && (
          <>
            {resource.data.items.map((s) => (
              <article key={s.id} className="panel source-card">
                <Icon name="book" />
                <div>
                  <h2>{t(s.title)}</h2>
                  <p>
                    {t(s.publisher)} · {t(s.number)} · {t(s.document_date)}
                  </p>
                  {t(safeSourceUrl(s.url) && (
                    <a
                      className="button button-outline"
                      href={safeSourceUrl(s.url)}
                      target="_blank"
                      rel="noreferrer"
                    >{t("Открыть источник")}</a>
                  ))}
                </div>
              </article>
            ))}
            {!resource.data.items.length && <p>{t("Источники пока не добавлены.")}</p>}
            <Pager page={page} total={resource.data.total} onPage={setPage} />
          </>
        )}
      </section>
    </RegulatoryGuide>
  );
}
function Settings() {
  useLocale();
  const capabilities = useResource("/capabilities", (v) => {
    const value = v as {
      uploads?: unknown;
      analysis?: unknown;
      camera_stream?: unknown;
    };
    if (
      !value ||
      typeof value.uploads !== "boolean" ||
      typeof value.analysis !== "boolean" ||
      typeof value.camera_stream !== "boolean"
    )
      throw new Error("Некорректный ответ сервера.");
    return value;
  });
  return (
    <>
      <h1>{t("Настройки подключения")}</h1>
      <LanguageSettings />
      <section className="panel settings-panel">
        <h2>{t("Сервис команды")}</h2>
        <StateNotice {...capabilities} retry={capabilities.refresh} />
        {capabilities.data && (
          <>
            <p>{t("API доступен. Записи хранятся на сервере.")}</p>
            <p>{t("Поиск объектов и движений:")}{" "}
              {t(capabilities.data.analysis ? "доступен" : "не подключён")}.
            </p>
            <p>{t("Захват видеопотока:")}{" "}
              {t(capabilities.data.camera_stream ? "подключён" : "не подключён")}.
            </p>
          </>
        )}
        <p>{t("Доступ определяется вашей учётной записью.")}</p>
        <button
          className="button button-outline"
          onClick={() =>
            useAnalysisStore
              .getState()
              .setSettings({ mode: "demo", apiKey: "" })
          }
        >{t("Перейти к демонстрации")}</button>
        <p className="muted">{t("В демонстрации используются отдельные примеры. Рабочие записи остаются на сервере.")}</p>
      </section>
    </>
  );
}
