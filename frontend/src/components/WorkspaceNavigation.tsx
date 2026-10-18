import { CSSProperties, ReactNode, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { t, useLocale } from "../i18n";
import { useAuthStore } from "../store/useAuthStore";
import { Icon, IconName } from "./Icon";
import { Modal } from "./Modal";

const tabs: { path: string; label: string; icon: IconName }[] = [
  { path: "/workspace", label: "Обзор", icon: "grid" },
  { path: "/notifications", label: "События", icon: "bell" },
  { path: "/history", label: "Записи", icon: "history" },
  { path: "/monitoring", label: "Камеры", icon: "eye" },
];
const more: { path: string; label: string; icon: IconName }[] = [
  { path: "/shift", label: "Смена за минуту", icon: "play" },
  { path: "/sources", label: "Нормативная база", icon: "book" },
  { path: "/settings", label: "Настройки", icon: "settings" },
];

export function SidebarAccount({ onOpen }: { onOpen: () => void }) {
  useLocale();
  const user = useAuthStore(s => s.user);
  const name = user?.full_name || user?.nickname || user?.email || t("Проверяющий");
  const initials = name.trim().split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase();
  return <button className="sidebar-account" onClick={onOpen} aria-label={t("Учётная запись")}>
    <span className="avatar">{user ? initials : <Icon name="user" />}</span>
    <span className="sidebar-account-copy"><strong>{name}</strong><small>{t(user ? "Профиль и данные" : "Войти в аккаунт")}</small></span>
    <Icon name="chevron" size={16} />
  </button>;
}

export function WorkspacePage({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <div className="workspace-page" key={pathname}>{children}</div>;
}

export function MobileNavigation({ unread = 0, onAccount }: { unread?: number; onAccount: () => void }) {
  useLocale();
  const { pathname } = useLocation();
  const [expanded, setExpanded] = useState(false);
  const current = pathname.startsWith("/analysis/") ? "/history" : pathname;
  const index = tabs.findIndex(tab => tab.path === current);
  const activeIndex = index === -1 ? 4 : index;
  return <>
    <nav className="mobile-bottom-nav" aria-label={t("Навигация по кабинету")} style={{ "--active-tab": activeIndex } as CSSProperties}>
      <span className="mobile-active-indicator" aria-hidden="true" />
      {tabs.map(tab => <Link key={tab.path} to={tab.path} className="mobile-tab"
        aria-current={current === tab.path ? "page" : undefined}
        aria-label={tab.path === "/notifications" ? t("Оповещения, новых: {0}", [unread]) : undefined}>
        <span className="mobile-tab-icon"><Icon name={tab.icon} size={22} />
          {tab.path === "/notifications" && unread > 0 && <span className="mobile-notification-count" aria-hidden="true">{unread > 99 ? "99+" : unread}</span>}
        </span><span className="mobile-tab-label">{t(tab.label)}</span>
      </Link>)}
      <button className={`mobile-tab ${activeIndex === 4 ? "is-current" : ""}`} aria-expanded={expanded} aria-haspopup="dialog" onClick={() => setExpanded(true)}>
        <span className="mobile-tab-icon"><Icon name="menu" size={22} /></span><span className="mobile-tab-label">{t("Ещё")}</span>
      </button>
    </nav>
    {expanded && <Modal title={t("Разделы кабинета")} onClose={() => setExpanded(false)}>
      <div className="workspace-more-menu">
        {more.map(item => <Link to={item.path} key={item.path} aria-current={current === item.path ? "page" : undefined} onClick={() => setExpanded(false)}>
          <span className="more-menu-icon"><Icon name={item.icon} /></span><strong>{t(item.label)}</strong><Icon name="chevron" size={17} />
        </Link>)}
        <button onClick={() => { setExpanded(false); onAccount(); }}>
          <span className="more-menu-icon"><Icon name="user" /></span><strong>{t("Учётная запись")}</strong><Icon name="chevron" size={17} />
        </button>
      </div>
    </Modal>}
  </>;
}
