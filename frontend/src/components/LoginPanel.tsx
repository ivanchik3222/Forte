import { LoadingMark } from "./LoadingState";
import { ProfileEditor } from "./ProfileEditor";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { t, useLocale } from "../i18n";
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { demoAccount } from "../api/demoAccount";
import { useAuthStore } from "../store/useAuthStore";
import { useAnalysisStore } from "../store/useAnalysisStore";

export function LoginPanel() {
  useLocale();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [otp, setOtp] = useState("");
  const demoEnabled = process.env.REACT_APP_DEMO_MODE !== "false";
  const [password, setPassword] = useState("");
  const [testLogin, setTestLogin] = useState(false);
  const status = useAuthStore((state) => state.status);
  const user = useAuthStore((state) => state.user);
  const error = useAuthStore((state) => state.error);
  const login = useAuthStore((state) => state.login);
  const logout = useAuthStore((state) => state.logout);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (status === "loading") return;
    void login(identifier.trim(), password, otp || undefined);
  };

  const handleTestLogin = async () => {
    if (status === "loading") return;
    setTestLogin(true);
    await login(demoAccount.identifier, demoAccount.password);
    setTestLogin(false);
    const session = useAuthStore.getState();
    if (session.status === "authenticated" && session.user?.email === demoAccount.identifier) {
      useAnalysisStore.getState().setSettings({ mode: "api", apiKey: "" });
      navigate("/workspace");
    }
  };

  return (
    <div className="account-layout">
      <div className="account-welcome">
        <span className="landing-eyebrow">{t("ВАШЕ РАБОЧЕЕ ПРОСТРАНСТВО")}</span>
        <h3>{t("Внимание к деталям.")}<br />{t("Уверенность в решениях.")}</h3>
        <p>{t("Записи, события и обоснования — всё для внимательного контроля в одном месте.")}</p>
        <img src="/images/review-480.webp" alt="" width="480" height="480" />
      </div>
      <section className="account-form" aria-labelledby="login-title">
        <div className="mb-8 flex items-center justify-between gap-4">
          <span className="inline-flex items-center gap-2 rounded-full bg-forte-50 px-3 py-1.5 text-xs font-semibold text-forte-700">
            <span className="h-2 w-2 rounded-full bg-forte-500" />{t("Учётная запись команды")}</span>
          <LanguageSwitcher />
        </div>

        {status === "authenticated" && user ? (
          <div>
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-forte-100 text-xl font-bold text-forte-700">
              {t((user.full_name || user.nickname || user.email || "U")
                .charAt(0)
                .toUpperCase())}
            </div>
            <h2 id="login-title" className="text-2xl font-bold tracking-tight">{t("Добро пожаловать!")}</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-500">{t("Вы вошли как")}{" "}
              <strong className="font-semibold text-ink">
                {user.full_name || user.nickname || user.email}
              </strong>{t(". Учётная запись подключена.")}</p>
            <ProfileEditor key={user.id} user={user} />
            <button
              type="button"
              onClick={() => void logout()}
              className="mt-8 w-full rounded-xl border border-zinc-200 px-4 py-3 text-sm font-semibold text-ink transition hover:border-forte-500 hover:text-forte-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forte-500"
            >{t("Выйти")}</button>
            {t(error && <p role="alert">{t(error)}</p>)}
          </div>
        ) : (
          <>
            <h2 id="login-title" className="text-2xl font-bold tracking-tight">{t("Вход в рабочее пространство")}</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-500">{t("Войдите в учётную запись команды.")}</p>
            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              <div>
                <label
                  htmlFor="identifier"
                  className="mb-2 block text-sm font-semibold"
                >{t("Email или никнейм")}</label>
                <input
                  id="identifier"
                  name="identifier"
                  type="text"
                  autoComplete="username"
                  required
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                  placeholder="you@example.com"
                  className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm outline-none transition placeholder:text-zinc-400 focus:border-forte-500 focus:bg-white focus:ring-3 focus:ring-forte-100"
                />
              </div>
              <div>
                <label
                  htmlFor="password"
                  className="mb-2 block text-sm font-semibold"
                >{t("Пароль")}</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={t("Введите пароль")}
                  className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm outline-none transition placeholder:text-zinc-400 focus:border-forte-500 focus:bg-white focus:ring-3 focus:ring-forte-100"
                />
              </div>
              <div>
                <label htmlFor="otp" className="mb-2 block text-sm font-semibold">{t("Код MFA (если подключён)")}</label>
                <input id="otp" name="otp" inputMode="numeric" autoComplete="one-time-code"
                  pattern="[0-9]{6}" maxLength={6} value={otp} onChange={(event) => setOtp(event.target.value)}
                  className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm" />
              </div>
              {t(error && (
                <p
                  role="alert"
                  className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700"
                >
                  {t(error)}
                </p>
              ))}
              <button
                type="submit"
                disabled={status === "loading"}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-forte-500 px-4 py-3.5 text-sm font-semibold text-white shadow-lg shadow-forte-500/20 transition hover:bg-forte-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forte-500 disabled:cursor-wait disabled:opacity-60"
              >
                {status === "loading" && !testLogin && <LoadingMark small />}
                {t(status === "loading" && !testLogin ? "Проверяем данные…" : "Войти")}
              </button>
              {demoEnabled && <>
              <button
                type="button"
                disabled={status === "loading"}
                onClick={() => void handleTestLogin()}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-forte-200 bg-forte-50 px-4 py-3.5 text-sm font-semibold text-forte-700 transition hover:border-forte-500 hover:bg-forte-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forte-500 disabled:cursor-wait disabled:opacity-60"
              >
                {status === "loading" && testLogin && <LoadingMark small />}
                {t(status === "loading" && testLogin ? "Входим в тестовый аккаунт…" : "Войти в тестовый аккаунт")}
              </button>
              <p className="text-center text-xs leading-5 text-zinc-500">{t("Общий тестовый аккаунт: загруженные записи и изменения видны всем, кто в него вошёл.")}</p>
              </>}
            </form>
            {demoEnabled && <p className="mt-5 text-center text-xs leading-5 text-zinc-400">{t("Демонстрационный интерфейс. Не вводите данные реального банковского аккаунта.")}</p>}
          </>
        )}
      </section>
    </div>
  );
}
