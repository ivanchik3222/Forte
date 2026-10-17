export interface User {
  id: number;
  email: string | null;
  nickname: string | null;
  full_name: string | null;
  user_type: string;
}

interface AuthResponse {
  user: User;
  access_token: string;
  refresh_token: string;
}

const apiBaseUrl = (
  process.env.REACT_APP_API_URL || 'http://localhost:6767'
).replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  accessToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body) headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);

  const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers });
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const error = payload as { error?: string; message?: string } | null;
    throw new ApiError(error?.error || error?.message || 'Не удалось выполнить запрос.', response.status);
  }

  return payload as T;
}

export const authApi = {
  login: (identifier: string, password: string) =>
    apiRequest<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, password }),
    }),
};
