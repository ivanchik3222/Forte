import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';
import { useAuthStore } from './store/useAuthStore';

const originalFetch = global.fetch;

afterEach(() => {
  useAuthStore.getState().logout();
  global.fetch = originalFetch;
});

test('вход отправляет данные backend и показывает пользователя', async () => {
  const fetchMock = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      user: { id: 1, email: 'demo@example.com', nickname: null, full_name: 'Тестовый пользователь', user_type: 'user' },
      access_token: 'test-access',
      refresh_token: 'test-refresh',
    }),
  } as Response);
  global.fetch = fetchMock;

  render(<App />);
  fireEvent.change(screen.getByLabelText('Email или никнейм'), { target: { value: 'demo@example.com' } });
  fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'secret123' } });
  fireEvent.click(screen.getByRole('button', { name: 'Войти' }));

  await waitFor(() => expect(screen.getByText('Тестовый пользователь')).toBeInTheDocument());
  expect(fetchMock).toHaveBeenCalledWith('http://localhost:6767/api/auth/login', expect.objectContaining({
    method: 'POST',
    body: JSON.stringify({ identifier: 'demo@example.com', password: 'secret123' }),
  }));
});
