import { create } from "zustand";
import { authApi, observeSession, User, ApiError } from "../api/client";
interface AuthState {
  status: "idle" | "loading" | "authenticated";
  initialized: boolean;
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  error: string | null;
  login: (identifier: string, password: string) => Promise<void>;
  restore: () => Promise<void>;
  logout: () => Promise<void>;
}
const message = (e: unknown) =>
  e instanceof TypeError
    ? "Нет связи с сервером."
    : e instanceof Error
      ? e.message
      : "Ошибка запроса.";
let restoring: Promise<void> | undefined;
export const useAuthStore = create<AuthState>((set, get) => ({
  status: "idle",
  initialized: false,
  user: null,
  accessToken: null,
  refreshToken: null,
  error: null,
  login: async (identifier, password) => {
    set({ status: "loading", error: null });
    try {
      const pending = authApi.login(identifier, password);
      // login clears the previous session synchronously; keep the form busy afterwards.
      set({ status: "loading" });
      const session = await pending;
      set({
        status: "authenticated",
        user: session.user,
        accessToken: session.access_token,
        initialized: true,
      });
    } catch (e) {
      set({ status: "idle", initialized: true, error: message(e) });
    }
  },
  restore: () => {
    if (get().initialized) return Promise.resolve();
    if (!restoring)
      restoring = (async () => {
        set({ status: "loading" });
        try {
          await authApi.restore();
        } catch (e) {
          set({
            status: "idle",
            error:
              e instanceof ApiError && e.status === 401 ? null : message(e),
          });
        } finally {
          set({ initialized: true });
        }
      })().finally(() => {
        restoring = undefined;
      });
    return restoring;
  },
  logout: async () => {
    try {
      await authApi.logout();
    } catch (e) {
      set({ error: message(e) });
    }
  },
}));
observeSession((session) =>
  useAuthStore.setState(
    session
      ? {
          status: "authenticated",
          user: session.user,
          accessToken: session.access_token,
          error: null,
          initialized: true,
        }
      : { status: "idle", user: null, accessToken: null, refreshToken: null },
  ),
);
