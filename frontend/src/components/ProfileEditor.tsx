import { FormEvent, useState } from "react";
import { demoAccount } from "../api/demoAccount";
import { apiRequest, User } from "../api/client";
import { useAuthStore } from "../store/useAuthStore";
import { t, useLocale } from "../i18n";
import { Icon } from "./Icon";

export function ProfileEditor({ user }: { user: User }) {
  useLocale();
  const [name, setName] = useState(user.full_name || "");
  const [nickname, setNickname] = useState(user.nickname || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    if (!name.trim()) { setError(t("Укажите имя и фамилию.")); return; }
    setSaving(true); setError(""); setSaved(false);
    try {
      const result = await apiRequest<{ data: { user: User } }>("/api/auth/profile", {
        method: "PUT", body: JSON.stringify({ full_name: name.trim(), ...(nickname.trim() ? { nickname: nickname.trim() } : {}) }),
      });
      const updated = result?.data?.user;
      if (updated?.id !== user.id || typeof updated.full_name !== "string") throw new Error(t("Некорректный ответ сервера."));
      if (useAuthStore.getState().user?.id !== user.id) return;
      useAuthStore.setState({ user: updated });
      setName(updated.full_name); setNickname(updated.nickname || ""); setSaved(true);
    } catch (e) { setError(e instanceof Error ? e.message : t("Не удалось сохранить профиль.")); }
    finally { setSaving(false); }
  }
  if (user.email === demoAccount.identifier) return <div className="profile-readonly">{t("Это общий демонстрационный аккаунт. Редактирование данных доступно в личной учётной записи.")}</div>;
  return <form className="profile-editor" onSubmit={submit} aria-label={t("Редактирование профиля")}>
    <label htmlFor="profile-name">{t("Имя и фамилия")}</label>
    <input id="profile-name" name="name" autoComplete="name" required maxLength={120} value={name}
      onChange={e => { setName(e.target.value); setSaved(false); }} />
    <label htmlFor="profile-nickname">{t("Никнейм")}</label>
    <input id="profile-nickname" name="nickname" autoComplete="username" required={Boolean(user.nickname)}
      pattern="[a-zA-Z0-9_.\-]{3,20}" maxLength={20} value={nickname} aria-describedby="nickname-hint"
      onChange={e => { setNickname(e.target.value); setSaved(false); }} />
    <small id="nickname-hint">{t("3–20 символов: латинские буквы, цифры, точка, дефис или подчёркивание.")}</small>
    {user.email && <p className="profile-email"><Icon name="lock" size={14} /><span>{user.email}</span></p>}
    {error && <p className="profile-feedback is-error" role="alert">{t(error)}</p>}
    {saved && <p className="profile-feedback" role="status"><Icon name="checkCircle" size={17} />{t("Профиль сохранён")}</p>}
    <button className="button button-primary" type="submit" disabled={saving}>
      <Icon name={saving ? "refresh" : "check"} size={17} />{t(saving ? "Сохраняем…" : "Сохранить изменения")}
    </button>
  </form>;
}
