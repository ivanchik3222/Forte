import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ApiAccessPage } from './ApiAccessPage';

const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });

test('issues and revokes a key without a user session', async () => {
  const request = jest.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ api_key: 'forte_test_secret', expires_at: '2026-11-17T00:00:00Z' }) })
    .mockResolvedValueOnce({ ok: true });
  global.fetch = request;
  render(<MemoryRouter><ApiAccessPage /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: 'Создать API-ключ' }));
  expect(await screen.findByDisplayValue('forte_test_secret')).toBeInTheDocument();
  expect(request.mock.calls[0][1]).toEqual({ method: 'POST', credentials: 'omit' });
  fireEvent.click(screen.getByRole('button', { name: 'Отозвать ключ' }));
  expect(await screen.findByText('Ключ отозван. Доступ к его задачам закрыт.')).toBeInTheDocument();
  expect(request.mock.calls[1][1].headers).toEqual({ 'X-API-Key': 'forte_test_secret' });
  expect(screen.queryByDisplayValue('forte_test_secret')).not.toBeInTheDocument();
});

test('shows issuance limit errors without generating a local key', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: false, json: async () => ({ error: { message: 'Лимит выдачи ключей' } }) });
  render(<MemoryRouter><ApiAccessPage /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: 'Создать API-ключ' }));
  expect(await screen.findByText('Лимит выдачи ключей')).toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
