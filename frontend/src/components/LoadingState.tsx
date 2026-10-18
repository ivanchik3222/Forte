import { t, useLocale } from "../i18n";
import { Icon } from "./Icon";
import "../styles/loading.css";

/** Decorative only: the owning status or button supplies the accessible label. */
export function LoadingMark({ small = false }: { small?: boolean }) {
  return <span className={`loading-mark${small ? " loading-mark-small" : ""}`} aria-hidden="true">
    <svg className="loading-ring" viewBox="0 0 48 48"><circle cx="24" cy="24" r="21" /></svg>
    {!small && <Icon name="scan" size={19} />}
  </span>;
}

export function LoadingState({
  label = "Загружаем данные…",
  variant = "panel",
}: {
  label?: string;
  variant?: "panel" | "inline" | "records";
}) {
  useLocale();
  return <div className={`loading-state loading-state-${variant}`}>
    <div className="loading-status" role="status" aria-live="polite" aria-atomic="true">
      <LoadingMark small={variant === "inline"} /><span>{t(label)}</span>
    </div>
    {variant === "records" && <div className="loading-records" aria-hidden="true">
      {[0, 1, 2].map(index => <div className="loading-record" key={index}>
        <span className="loading-thumbnail" /><span className="loading-record-copy"><i /><i /></span><span className="loading-record-badge" />
      </div>)}
    </div>}
  </div>;
}
