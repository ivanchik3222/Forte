import { create } from 'zustand';
import { authApi, User } from '../api/client';

type AuthStatus = 'idle' | 'loading' | 'authenticated';

interface AuthState {
  status: AuthStatus;
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  error: string | null;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  status: 'idle',
  user: null,
  accessToken: null,
  refreshToken: null,
  error: null,
  login: async (identifier, password) => {
    set({ status: 'loading', error: null });
    try {
      const result = await authApi.login(identifier, password);
      set({
        status: 'authenticated',
        user: result.user,
        accessToken: result.access_token,
        refreshToken: result.refresh_token,
      });
    } catch (error) {
      set({
        status: 'idle',
        user: null,
        accessToken: null,
        refreshToken: null,
        error: error instanceof TypeError
          ? 'Нет связи с сервером. Проверьте, запущен ли backend.'
          : error instanceof Error ? error.message : 'Не удалось войти.',
      });
    }
  },
  logout: () => set({
    status: 'idle',
    user: null,
    accessToken: null,
    refreshToken: null,
    error: null,
  }),
}));
