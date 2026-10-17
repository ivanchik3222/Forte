import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { demoAccount } from "../api/demoAccount";
import { useAuthStore } from "../store/useAuthStore";
import { useAnalysisStore } from "../store/useAnalysisStore";

const originalFetch = global.fetch;
const demoUser = { id: 7, email: demoAccount.identifier, nickname: null, full_name: "Тестовый пользователь", user_type: "user" };
const response = (payload: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => payload }) as Response;

beforeEach(() => {
  window.scrollTo = jest.fn();
  useAuthStore.setState({ initialized: true, status: "idle", user: null, error: null, accessToken: null });
  useAnalysisStore.setState({ settings: { mode: "api", apiKey: "" }, records: [] });
  global.fetch = jest.fn(async (input) => {
    if (String(input).endsWith("/login")) return response({ user: demoUser, access_token: "demo-access", csrf_token: "demo-csrf" });
    if (String(input).includes("/overview")) return response({ date: "2026-10-17", today_total: 0, today_read: 0, today_unread: 0, unread_total: 0, camera_total: 0, media_total: 0, recent_alerts: [], recent_media: [] });
    return response({ items: [], total: 0, page: 1, per_page: 20 });
  });
});

afterEach(() => {
  global.fetch = originalFetch;
  useAuthStore.setState({ initialized: true, status: "idle", user: null, error: null, accessToken: null });
});

test.each(["/login", "/workspace", "profile-modal"])("quick sign-in from %s authenticates against the API and opens the workspace", async (entry) => {
  window.history.replaceState(null, "", entry === "profile-modal" ? "/workspace" : entry);
  // /login must also be accessible when the user previously selected the static demo.
  if (entry !== "/workspace") useAnalysisStore.setState({ settings: { mode: "demo", apiKey: "" } });
  render(<App />);
  if (entry === "profile-modal") fireEvent.click(screen.getByRole("button", { name: "Войти в аккаунт" }));
  expect(screen.getByLabelText("Email или никнейм")).toHaveValue("");
  expect(screen.getByLabelText("Пароль")).toHaveValue("");
  fireEvent.click(screen.getByRole("button", { name: "Войти в тестовый аккаунт" }));
  await waitFor(() => expect(useAuthStore.getState().user?.email).toBe(demoAccount.identifier));
  await waitFor(() => expect(window.location.pathname).toBe("/workspace"));
  expect(useAnalysisStore.getState().settings.mode).toBe("api");
  expect(global.fetch).toHaveBeenCalledWith("http://localhost:6767/api/auth/login", expect.objectContaining({ method: "POST", credentials: "include", body: JSON.stringify(demoAccount) }));
  expect(screen.queryByRole("button", { name: "Войти в тестовый аккаунт" })).not.toBeInTheDocument();
});

test("pending sign-in prevents duplicate submissions and an API failure keeps the form available", async () => {
  window.history.replaceState(null, "", "/login");
  let complete!: (value: Response) => void;
  global.fetch = jest.fn(() => new Promise<Response>((resolve) => { complete = resolve; }));
  render(<App />);
  fireEvent.change(screen.getByLabelText("Email или никнейм"), { target: { value: "personal@example.com" } });
  const button = screen.getByRole("button", { name: "Войти в тестовый аккаунт" });
  fireEvent.click(button);
  expect(button).toBeDisabled();
  expect(screen.getByRole("button", { name: "Войти" })).toBeDisabled();
  fireEvent.click(button);
  expect(global.fetch).toHaveBeenCalledTimes(1);
  await act(async () => { complete(response({ error: { message: "Тестовый аккаунт недоступен" } }, 401)); });
  expect(await screen.findByRole("alert")).toHaveTextContent("Тестовый аккаунт недоступен");
  expect(screen.getByRole("button", { name: "Войти в тестовый аккаунт" })).toBeEnabled();
  expect(screen.getByLabelText("Email или никнейм")).toHaveValue("personal@example.com");
  expect(useAuthStore.getState().user).toBeNull();
  expect(window.location.pathname).toBe("/login");
});
