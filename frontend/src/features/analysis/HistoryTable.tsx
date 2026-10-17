import { formatDate, eventLabel, localeCode, t, useLocale } from "../../i18n";
import { useState } from "react";
import { Icon } from "../../components/Icon";
import { AnalysisRecord, fileSize, timecode } from "./types";

export function StatusBadge({ record }: { record: AnalysisRecord }) {
  useLocale();
  const status =
    record.status === "done"
      ? record.verdict === "violation"
        ? "review"
        : record.verdict === "no_violation" ? "clear" : "observations"
      : record.status;
  const config = {
    stored: { icon: "video", text: "Без анализа" },
    observations: { icon: "video", text: "Наблюдения готовы" },
    review: { icon: "alert", text: "Требует внимания" },
    clear: { icon: "checkCircle", text: "Без признаков нарушений" },
    uploading: { icon: "upload", text: "Загрузка" },
    processing: { icon: "clock", text: "Обрабатывается" },
    failed: { icon: "alert", text: "Ошибка обработки" },
    cancelled: { icon: "close", text: "Ожидание остановлено" },
  } as const;
  return (
    <span className={`status-badge status-${status}`}>
      <Icon name={config[status].icon} size={14} />
      {t(config[status].text)}
    </span>
  );
}

export function HistoryTable({
  records,
  onOpen,
  full = false,
  serverManaged = false,
}: {
  records: AnalysisRecord[];
  onOpen: (id: string) => void;
  full?: boolean;
  serverManaged?: boolean;
}) {
  useLocale();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("newest");
  const filtered = serverManaged
    ? records
    : records
        .filter(
          (record) =>
            record.fileName.toLowerCase().includes(search.toLowerCase()) &&
            (filter === "all" ||
              (filter === "review" && record.verdict === "violation") ||
              (filter === "clear" && record.verdict === "no_violation") ||
              (filter === "processing" &&
                ["uploading", "processing"].includes(record.status)) ||
              (filter === "failed" &&
                ["failed", "cancelled"].includes(record.status))),
        )
        .sort((a, b) =>
          sort === "newest"
            ? b.createdAt.localeCompare(a.createdAt)
            : a.createdAt.localeCompare(b.createdAt),
        );
  return (
    <>
      {full && !serverManaged && (
        <div className="table-toolbar">
          <label className="search-input">
            <Icon name="search" size={18} />
            <input
              aria-label={t("Поиск по имени файла")}
              placeholder={t("Поиск по названию файла")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label className="filter-label">
            <span className="visually-hidden">{t("Статус проверки")}</span>
            <select
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="all">{t("Все статусы")}</option>
              <option value="review">{t("Требует внимания")}</option>
              <option value="clear">{t("Без признаков нарушений")}</option>
              <option value="processing">{t("Обрабатывается")}</option>
              <option value="failed">{t("Ошибки и остановленные")}</option>
            </select>
          </label>
          <label className="filter-label">
            <span className="visually-hidden">{t("Порядок проверок")}</span>
            <select
              value={sort}
              onChange={(event) => setSort(event.target.value)}
            >
              <option value="newest">{t("Сначала новые")}</option>
              <option value="oldest">{t("Сначала старые")}</option>
            </select>
          </label>
        </div>
      )}
      {filtered.length ? (
        <div className="table-scroll">
          <table className="history-table" role="table">
            <thead>
              <tr role="row">
                <th role="columnheader">{t("Видеозапись")}</th>
                <th role="columnheader">{t(serverManaged ? "Дата загрузки" : "Дата проверки")}</th>
                <th role="columnheader">{t(serverManaged ? "Статус" : "Результат")}</th>
                <th role="columnheader">{t("События")}</th>
                <th role="columnheader">
                  <span className="visually-hidden">{t("Действие")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {(full ? filtered : filtered.slice(0, 3)).map((record) => (
                <tr key={record.id} role="row">
                  <td role="cell">
                    <button
                      className="file-cell"
                      aria-label={t("Открыть {0}", [record.fileName])}
                      onClick={() => onOpen(record.id)}
                    >
                      <span className="file-icon">
                        <Icon name="video" size={20} />
                      </span>
                      <span className="file-details">
                        <strong title={record.fileName}>
                          {record.fileName}
                        </strong>
                        <small>
                          {fileSize(record.fileSize)}
                          {t(record.duration
                            ? ` · ${timecode(record.duration)}`
                            : "")}
                          {record.mode === "demo" && (
                            <span className="demo-label">{t("Демо")}</span>
                          )}
                        </small>
                      </span>
                      <Icon
                        name="arrow"
                        size={18}
                        className="mobile-record-arrow"
                      />
                    </button>
                  </td>
                  <td role="cell">
                    <span className="table-date">
                      {formatDate(record.createdAt, {
                        day: "2-digit",
                        month: "short",
                        timeZone: "Asia/Almaty",
                      })}
                    </span>
                    <small>
                      {new Date(record.createdAt).toLocaleTimeString(localeCode(), {
                        hour: "2-digit",
                        minute: "2-digit",
                        timeZone: "Asia/Almaty",
                      })}
                    </small>
                  </td>
                  <td role="cell">
                    <StatusBadge record={record} />
                  </td>
                  <td role="cell">
                    <span
                      className={`event-count ${record.violations.length ? "has-events" : ""} ${record.status !== "done" ? "event-count-pending" : ""}`}
                    >
                      {t(record.status === "done"
                        ? record.violations.length.toString().padStart(2, "0")
                        : "—")}
                      {record.status === "done" && (
                        <span className="mobile-event-caption">
                          {eventLabel(record.violations.length)}
                        </span>
                      )}
                    </span>
                  </td>
                  <td role="cell">
                    <button
                      className="icon-button"
                      aria-label={t("Открыть {0}", [record.fileName])}
                      onClick={() => onOpen(record.id)}
                    >
                      <Icon name="arrow" size={18} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state">
          <Icon name="search" size={30} />
          <h3>{t(serverManaged ? "Записи не найдены" : "Проверки не найдены")}</h3>
          <p>{t("Измените поисковый запрос или выберите другой статус.")}</p>
          {!serverManaged && (
            <button
              className="text-button"
              onClick={() => {
                setSearch("");
                setFilter("all");
              }}
            >{t("Сбросить фильтры")}</button>
          )}
        </div>
      )}
    </>
  );
}
