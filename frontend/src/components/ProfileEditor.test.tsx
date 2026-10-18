import { act, fireEvent, render, screen } from "@testing-library/react";
import { apiRequest, User } from "../api/client";
import { demoAccount } from "../api/demoAccount";
import { setLocale } from "../i18n";
import { useAuthStore } from "../store/useAuthStore";
import { ProfileEditor } from "./ProfileEditor";
import { SidebarAccount } from "./WorkspaceNavigation";

jest.mock("../api/client", () => ({
  ...jest.requireActual("../api/client"),
  apiRequest: jest.fn(),
}));

const user: User = { id: 41, email: "reviewer@example.com", nickname: "reviewer", full_name: "Тестовый пользователь", user_type: "user" };
const request = apiRequest as jest.Mock;
beforeEach(() => {
  setLocale("ru");
  request.mockReset();
  useAuthStore.setState({ user, status: "authenticated", initialized: true });
});

test("profile changes persist through the existing API and update the sidebar", async () => {
  const updated = { ...user, full_name: "Алия Тестовая", nickname: "aliya.test" };
  request.mockResolvedValue({ data: { user: updated } });
  render(<><ProfileEditor user={user} /><SidebarAccount onOpen={() => {}} /></>);
  fireEvent.change(screen.getByLabelText("Имя и фамилия"), { target: { value: "  Алия Тестовая  " } });
  fireEvent.change(screen.getByLabelText("Никнейм"), { target: { value: "aliya.test" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить изменения" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Профиль сохранён");
  expect(request).toHaveBeenCalledWith("/api/auth/profile", {
    method: "PUT", body: JSON.stringify({ full_name: "Алия Тестовая", nickname: "aliya.test" }),
  });
  expect(screen.getByRole("button", { name: "Учётная запись" })).toHaveTextContent("Алия Тестовая");
  expect(screen.getByLabelText("Имя и фамилия")).toHaveValue("Алия Тестовая");
});

test("a failed save retains the original account and the edited form for retry", async () => {
  request.mockRejectedValue(new Error("Этот nickname уже занят"));
  render(<ProfileEditor user={user} />);
  fireEvent.change(screen.getByLabelText("Никнейм"), { target: { value: "taken" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить изменения" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Этот nickname уже занят");
  expect(useAuthStore.getState().user).toEqual(user);
  expect(screen.getByLabelText("Никнейм")).toHaveValue("taken");
  expect(screen.getByRole("button", { name: "Сохранить изменения" })).toBeEnabled();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("a late profile response cannot restore an account after logout", async () => {
  let finish!: (value: unknown) => void;
  request.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<ProfileEditor user={user} />);
  fireEvent.click(screen.getByRole("button", { name: "Сохранить изменения" }));
  act(() => { useAuthStore.setState({ user: null, status: "idle" }); });
  await act(async () => { finish({ data: { user: { ...user, full_name: "Изменено" } } }); });
  expect(useAuthStore.getState().user).toBeNull();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("the shared demo account explains why personal details are read-only", () => {
  render(<ProfileEditor user={{ ...user, email: demoAccount.identifier }} />);
  expect(screen.getByText(/общий демонстрационный аккаунт/)).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(request).not.toHaveBeenCalled();
});
