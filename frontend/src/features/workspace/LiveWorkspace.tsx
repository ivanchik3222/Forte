import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { apiRequest, mediaUrl } from "../../api/client";
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
import { Modal } from "../../components/Modal";
import { Icon, IconName } from "../../components/Icon";
import { useAuthStore } from "../../store/useAuthStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import {
  fileSize,
  safeSourceUrl,
  timecode,
  validateVideo,
} from "../analysis/types";
import { HistoryTable } from "../analysis/HistoryTable";
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
  new Date(v).toLocaleString("ru-RU", {
    timeZone: "Asia/Almaty",
    dateStyle: "medium",
    timeStyle: "short",
  });

function StateNotice({
  error,
  loading,
  retry,
}: {
  error?: string;
  loading?: boolean;
  retry?: () => void;
}) {
  return (
    <>
      {loading && <p role="status">Загрузка…</p>}
      {error && (
        <div className="notice" role="alert">
          <span>{error}</span>
          {retry && (
            <button className="text-button" onClick={retry}>
              Повторить
            </button>
          )}
        </div>
      )}
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
  return (
    <div className="table-toolbar">
      <span>
        Всего: {total} · Страница {page}
      </span>
      <button
        className="button button-outline"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        Назад
      </button>
      <button
        className="button button-outline"
        disabled={page * perPage >= total}
        onClick={() => onPage(page + 1)}
      >
        Далее
      </button>
    </div>
  );
}

export function LiveWorkspace() {
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
        <Link to="/" className="back-link">
          ← На главную
        </Link>
        <LoginPanel />
        <button
          className="button button-outline"
          onClick={() =>
            useAnalysisStore
              .getState()
              .setSettings({ mode: "demo", apiKey: "" })
          }
        >
          Открыть демонстрацию без входа
        </button>
      </main>
    );
  if (pathname === "/login") return <Navigate to="/workspace" replace />;
  return <AuthenticatedWorkspace key={auth.user.id} />;
}

function AuthenticatedWorkspace() {
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
      <aside className="sidebar" aria-label="Основная навигация">
        <Link className="brand" to="/">
          <img src="/forte-logo.svg" width="112" height="34" alt="Forte" />
          <span className="brand-divider" />
          <span>control</span>
        </Link>
        <div className="workspace-label">
          <Icon name="shield" />
          <div>
            <strong>Кассовый контроль</strong>
            <span>Рабочее пространство</span>
          </div>
        </div>
        <nav>
          {navigation.map((n) => (
            <Link
              className={`nav-item ${active === n.path ? "active" : ""}`}
              aria-current={active === n.path ? "page" : undefined}
              to={n.path}
              key={n.path}
            >
              <Icon name={n.icon} />
              <span>{n.label}</span>
              {n.path === "/notifications" && (
                <span className="nav-count">
                  {overview.data?.unread_total ?? "—"}
                </span>
              )}
              {n.path === "/history" && (
                <span className="nav-count">
                  {overview.data?.media_total ?? "—"}
                </span>
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <strong>Записи на сервере команды</strong>
            <p>Видео сохраняются. ИИ-анализ пока не подключён.</p>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <Link className="mobile-brand" to="/">
            <img src="/forte-logo.svg" width="76" height="23" alt="Forte" />
          </Link>
          <div className="breadcrumbs">
            {navigation.find((n) => n.path === active)?.label || "Видеозапись"}
          </div>
          <div className="topbar-actions">
            <Link className="mode-badge mode-api" to="/settings">
              Рабочий режим
            </Link>
            <button
              className="profile-button"
              onClick={() => setModal("account")}
            >
              <Icon name="user" />
              {user.full_name || user.nickname || user.email}
            </button>
          </div>
        </header>
        <main id="main-content" className="main-content">
          <StateNotice error={overview.error} retry={overview.refresh} />
          {pathname === "/workspace" && (
            <>
              <div className="page-title-row">
                <div>
                  <p className="eyebrow">{today}</p>
                  <h1>Контроль кассовых операций</h1>
                  <p>Сохранённые видео и события для просмотра</p>
                </div>
                <button
                  className="button button-primary"
                  onClick={() => setModal("upload")}
                >
                  <Icon name="plus" />
                  Загрузить видео
                </button>
              </div>
              <div className="notice">
                ИИ-анализ пока не подключён. Проверки камер и события поступают
                от подключённого источника или специалиста.
              </div>
              <StateNotice loading={overview.loading} />
              {overview.data && (
                <>
                  <section className="monitoring-summary">
                    <div className="monitoring-summary-copy">
                      <h2>События за сегодня</h2>
                      <Link to="/notifications">Открыть оповещения</Link>
                    </div>
                    <dl className="monitoring-totals">
                      <div>
                        <dt>Всего событий</dt>
                        <dd>{overview.data.today_total}</dd>
                      </div>
                      <div>
                        <dt>Просмотрено</dt>
                        <dd>{overview.data.today_read}</dd>
                      </div>
                      <div>
                        <dt>Новых</dt>
                        <dd>{overview.data.today_unread}</dd>
                      </div>
                    </dl>
                  </section>
                  {overview.data.monitoring_summary && (
                    <section className="panel">
                      <h2>Доступность наблюдения</h2>
                      <p>
                        Камер с проблемами:{" "}
                        {overview.data.monitoring_summary.problems}. Без свежих
                        проверок: {overview.data.monitoring_summary.unknown}.
                      </p>
                      <p>
                        Перерывы за день:{" "}
                        {overview.data.monitoring_summary.unavailable_minutes.toLocaleString(
                          "ru-RU",
                          { maximumFractionDigits: 1 },
                        )}{" "}
                        камера·мин.
                      </p>
                      <Link className="text-button" to="/monitoring">
                        Проверить интервалы наблюдения
                      </Link>
                      <Link className="button button-outline" to="/shift">
                        Смена за минуту
                      </Link>
                    </section>
                  )}
                  <section className="panel">
                    <h2>Последние события</h2>
                    <AlertList
                      alerts={overview.data.recent_alerts}
                      changed={changed}
                    />
                  </section>
                  <section className="panel history-panel">
                    <h2>Последние записи</h2>
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
                <h1>Страница не найдена</h1>
                <Link to="/workspace">Вернуться к обзору</Link>
              </section>
            )}
        </main>
        <footer className="app-footer">
          Forte Control · Видео сохраняются без ИИ-анализа
        </footer>
      </div>
      <nav className="mobile-bottom-nav" aria-label="Навигация по кабинету">
        {navigation.map((n) => (
          <Link
            className="mobile-tab"
            key={n.path}
            to={n.path}
            aria-current={active === n.path ? "page" : undefined}
          >
            <Icon name={n.icon} />
            <span>{n.label}</span>
          </Link>
        ))}
      </nav>
      {modal === "account" && (
        <Modal title="Учётная запись" onClose={() => setModal(null)}>
          <LoginPanel />
          <StateNotice error={useAuthStore.getState().error || undefined} />
        </Modal>
      )}
      <UploadDialog
        visible={modal === "upload"}
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
  close,
  saved,
}: {
  visible: boolean;
  close: () => void;
  saved: (id: string) => void;
}) {
  const [file, setFile] = useState<File>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
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
        }),
      );
      setFile(undefined);
      saved(record.id);
    } catch (e) {
      setError(
        e instanceof DOMException && e.name === "AbortError"
          ? "Ожидание остановлено. Файл мог сохраниться: повторите отправку с тем же файлом или проверьте историю."
          : `${message(e)} Повтор использует тот же ключ и не создаст дубликат.`,
      );
    } finally {
      setBusy(false);
      controller.current = undefined;
    }
  };
  if (!visible) return null;
  return (
    <Modal title="Загрузить видео" onClose={close}>
      <section className="upload-panel">
        <p>Видео сохранится на сервере. Анализ не выполняется.</p>
        <div
          className="dropzone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            select(e.dataTransfer.files);
          }}
        >
          <Icon name="upload" size={32} />
          <label className="button button-outline">
            Выбрать видео
            <input
              aria-label="Выбрать видеофайл"
              type="file"
              accept=".mov,.mp4,.webm"
              disabled={busy}
              onChange={(e) => select(e.target.files)}
            />
          </label>
          <p>
            {file
              ? `${file.name} · ${fileSize(file.size)}`
              : "Перетащите один MOV, MP4 или WebM до 200 МиБ"}
          </p>
        </div>
        <StateNotice error={error} />
        <div className="settings-save">
          <button
            className="button button-primary"
            disabled={!file || busy}
            onClick={() => void upload()}
          >
            {busy ? "Отправка и проверка файла…" : "Сохранить видео"}
          </button>
          {busy && (
            <button
              className="button button-outline"
              onClick={() => controller.current?.abort()}
            >
              Остановить ожидание
            </button>
          )}
        </div>
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
          <h1>История записей</h1>
          <p>
            Видео сохраняются на сервере и доступны после обновления страницы.
          </p>
        </div>
        <button className="button button-primary" onClick={onNew}>
          Загрузить видео
        </button>
      </div>
      <section className="panel history-panel">
        <div className="table-toolbar">
          <input
            aria-label="Поиск по имени файла"
            className="search-input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Имя файла"
          />
          <select
            aria-label="Статус записи"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="all">Все статусы</option>
            <option value="stored">Без анализа</option>
          </select>
          <select
            aria-label="Сортировка"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setPage(1);
            }}
          >
            <option value="newest">Сначала новые</option>
            <option value="oldest">Сначала старые</option>
          </select>
        </div>
        <StateNotice {...resource} retry={resource.refresh} />
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
  const record = useResource(`/media/${encodeURIComponent(id)}`, parseMedia);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [unplayable, setUnplayable] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const resumeAt = useRef(0);
  const refreshUrl = async () => {
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
    }
  };
  useEffect(() => {
    if (record.data) void refreshUrl();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record.data?.id]);
  const downloadReport = async () => {
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
    }
  };
  return (
    <>
      <Link to="/history" className="back-link">
        ← К записям
      </Link>
      <StateNotice {...record} retry={record.refresh} />
      {record.data && (
        <>
          <div className="page-title-row">
            <div>
              <h1>{record.data.file_name}</h1>
              <p>
                {fileSize(record.data.file_size)} ·{" "}
                {dateTime(record.data.created_at)}
                {record.data.duration_sec
                  ? ` · ${timecode(record.data.duration_sec)}`
                  : ""}
              </p>
            </div>
            <button
              className="button button-outline"
              onClick={() => void downloadReport()}
            >
              Скачать JSON
            </button>
          </div>
          <div className="notice">
            <Icon name="info" />
            Видео сохранено. Анализ пока недоступен. Вывод о наличии нарушений
            не сформирован.
          </div>
          <section className="panel live-video">
            <StateNotice error={error} />
            {url && (
              <video
                ref={video}
                controls
                preload="metadata"
                src={url}
                onLoadedMetadata={() => {
                  if (video.current && resumeAt.current > 0)
                    video.current.currentTime = resumeAt.current;
                }}
                onError={() => setUnplayable(true)}
                style={{
                  width: "100%",
                  maxHeight: "65vh",
                  background: "#171217",
                }}
              />
            )}
            {unplayable && (
              <p role="alert">
                Браузер не смог воспроизвести видео. Обновите ссылку или
                скачайте оригинал; кодек MOV может не поддерживаться.
              </p>
            )}
            <div className="settings-save">
              <button
                className="button button-outline"
                onClick={() => void refreshUrl()}
              >
                Обновить ссылку на видео
              </button>
              {url && (
                <a
                  className="button button-outline"
                  href={`${url}&download=1`}
                  referrerPolicy="no-referrer"
                >
                  Скачать оригинал
                </a>
              )}
            </div>
            <p className="muted">
              Ссылка действует 15 минут. При истечении срока обновите её этой
              кнопкой.
            </p>
          </section>
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
        <ul className="notification-feed" aria-label="События с камер">
          {alerts.map((a) => (
            <li key={a.id}>
              <button
                className={`notification-row ${!a.read_at ? "is-unread" : ""}`}
                onClick={() => void select(a.id)}
              >
                <time className="notification-time">
                  {new Date(a.detected_at).toLocaleTimeString("ru-RU", {
                    timeZone: "Asia/Almaty",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </time>
                <span className="notification-content">
                  <span className="notification-source">
                    {a.camera_name} · {a.location}
                  </span>
                  <strong>{a.event.type}</strong>
                  <span className="notification-meta">
                    {a.read_at ? "Просмотрено" : "Новое"}
                    {a.source === "test" ? " · Тестовое событие" : ""}
                  </span>
                </span>
                <Icon name="arrow" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="notification-empty">
          <h3>Событий пока нет</h3>
          <p>
            Для выбранных условий события не поступали. Доступность наблюдения
            можно проверить в контроле камер.
          </p>
        </div>
      )}
      {selected && (
        <Modal title="Событие с камеры" onClose={() => setSelected(undefined)}>
          <h3>{selected.event.type}</h3>
          <p>
            {selected.camera_name} · {selected.location} ·{" "}
            {dateTime(selected.detected_at)}
          </p>
          {selected.source === "test" && (
            <div className="notice">
              Тестовое событие. Это не результат наблюдения или ИИ-анализа.
            </div>
          )}
          <p>{selected.event.description}</p>
          {selected.event.evidence_frames.length ? (
            selected.event.evidence_frames.map((f, i) => (
              <figure key={i}>
                <img
                  style={{ maxWidth: "100%" }}
                  src={mediaUrl(f.image_url)}
                  alt={`Кадр ${timecode(f.timestamp_sec)}`}
                  referrerPolicy="no-referrer"
                />
                <figcaption>{timecode(f.timestamp_sec)}</figcaption>
              </figure>
            ))
          ) : (
            <p>Кадры не переданы.</p>
          )}
          {selected.event.rule ? (
            <div>
              <h4>{selected.event.rule.title}</h4>
              <p>{selected.event.rule.section}</p>
              <p>{selected.event.rule.explanation}</p>
              {safeSourceUrl(selected.event.rule.url) && (
                <a
                  href={safeSourceUrl(selected.event.rule.url)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Открыть источник
                </a>
              )}
            </div>
          ) : (
            <p>Нормативное основание не передано.</p>
          )}
          <p>
            {selected.read_at
              ? "Просмотр сохранён."
              : "Отметка просмотра не сохранена."}{" "}
            Наличие нарушения определяет специалист.
          </p>
          <StateNotice error={error} />
        </Modal>
      )}
    </>
  );
}

function Notifications({ changed }: { changed: () => void }) {
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
          <h1>Оповещения</h1>
          <p>Просмотр события не подтверждает нарушение.</p>
        </div>
      </div>
      <div className="notice">
        События поступают от подключённого источника или специалиста. Тестовые
        события отмечены отдельно.
      </div>
      <section className="panel">
        <div className="table-toolbar">
          <input
            aria-label="День событий"
            type="date"
            value={day}
            onChange={(e) => {
              setDay(e.target.value);
              setPage(1);
            }}
          />
          <select
            aria-label="Камера"
            value={camera}
            onChange={(e) => {
              setCamera(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Все камеры</option>
            {cameraOptions.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {cameras.data && cameraPage * 100 < cameras.data.total && (
            <button
              className="text-button"
              disabled={cameras.loading}
              onClick={() => setCameraPage((p) => p + 1)}
            >
              Загрузить ещё камеры
            </button>
          )}
          <select
            aria-label="Просмотр событий"
            value={read}
            onChange={(e) => {
              setRead(e.target.value);
              setPage(1);
            }}
          >
            <option value="all">Все</option>
            <option value="new">Новые</option>
            <option value="read">Просмотрены</option>
          </select>
          <button
            className="button button-outline"
            disabled={!resource.data?.items.some((a) => !a.read_at)}
            onClick={() => void bulk()}
          >
            Отметить показанные
          </button>
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
  const [page, setPage] = useState(1);
  const resource = useResource(`/cameras?page=${page}`, (v) =>
    parsePage(v, parseCamera),
  );
  return (
    <section className="panel">
      <h2>Камеры</h2>
      <StateNotice {...resource} retry={resource.refresh} />
      {resource.data && (
        <>
          {resource.data.items.map((c) => (
            <div className="notification-row" key={c.id}>
              <span>
                {c.name} · {c.location}
              </span>
              <span>
                {c.status === "unknown"
                  ? "Не подключена"
                  : c.status === "online"
                    ? "Есть связь"
                    : "Нет связи"}
              </span>
            </div>
          ))}
          {!resource.data.items.length && (
            <p>Камеры ещё не добавлены администратором.</p>
          )}
          <Pager page={page} total={resource.data.total} onPage={setPage} />
        </>
      )}
    </section>
  );
}
function Sources() {
  const [page, setPage] = useState(1);
  const resource = useResource(`/sources?page=${page}`, (v) =>
    parsePage(v, parseSource),
  );
  return (
    <>
      <h1>Нормативная база</h1>
      <div className="notice">
        Справочные ссылки. Актуальность и применимость документа проверяет
        специалист.
      </div>
      <StateNotice {...resource} retry={resource.refresh} />
      {resource.data && (
        <>
          {resource.data.items.map((s) => (
            <article key={s.id} className="panel source-card">
              <Icon name="book" />
              <div>
                <h2>{s.title}</h2>
                <p>
                  {s.publisher} · {s.number} · {s.document_date}
                </p>
                {safeSourceUrl(s.url) && (
                  <a
                    className="button button-outline"
                    href={safeSourceUrl(s.url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Открыть источник
                  </a>
                )}
              </div>
            </article>
          ))}
          {!resource.data.items.length && <p>Источники пока не добавлены.</p>}
          <Pager page={page} total={resource.data.total} onPage={setPage} />
        </>
      )}
    </>
  );
}
function Settings() {
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
      <h1>Настройки подключения</h1>
      <section className="panel settings-panel">
        <h2>Сервис команды</h2>
        <StateNotice {...capabilities} retry={capabilities.refresh} />
        {capabilities.data && (
          <>
            <p>API доступен. Записи хранятся на сервере.</p>
            <p>
              ИИ-анализ:{" "}
              {capabilities.data.analysis ? "доступен" : "не подключён"}.
            </p>
            <p>
              Захват видеопотока:{" "}
              {capabilities.data.camera_stream ? "подключён" : "не подключён"}.
            </p>
          </>
        )}
        <p>Доступ определяется вашей учётной записью.</p>
        <button
          className="button button-outline"
          onClick={() =>
            useAnalysisStore
              .getState()
              .setSettings({ mode: "demo", apiKey: "" })
          }
        >
          Перейти к демонстрации
        </button>
        <p className="muted">
          В демонстрации используются отдельные примеры. Рабочие записи остаются
          на сервере.
        </p>
      </section>
    </>
  );
}
