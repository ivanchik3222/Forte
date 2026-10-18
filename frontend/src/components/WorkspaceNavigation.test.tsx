import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { setLocale } from "../i18n";
import { MobileNavigation } from "./WorkspaceNavigation";

beforeEach(() => setLocale("ru"));

test("five mobile controls retain access to secondary sections and account", () => {
  const account = jest.fn();
  render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/workspace"]}>
    <MobileNavigation unread={3} onAccount={account} />
    <Routes><Route path="/workspace" element={null} /><Route path="/settings" element={<h1>Параметры сервиса</h1>} /></Routes>
  </MemoryRouter>);
  const nav = within(screen.getByRole("navigation", { name: "Навигация по кабинету" }));
  expect(nav.getAllByRole("link")).toHaveLength(4);
  expect(nav.getAllByRole("button")).toHaveLength(1);
  expect(nav.getByRole("link", { name: "Оповещения, новых: 3" })).toHaveAttribute("href", "/notifications");
  fireEvent.click(nav.getByRole("button", { name: "Ещё" }));
  const menu = within(screen.getByRole("dialog", { name: "Разделы кабинета" }));
  expect(menu.getByRole("link", { name: "Смена за минуту" })).toHaveAttribute("href", "/shift");
  expect(menu.getByRole("link", { name: "Нормативная база" })).toHaveAttribute("href", "/sources");
  fireEvent.click(menu.getByRole("link", { name: "Настройки" }));
  expect(screen.getByRole("heading", { name: "Параметры сервиса" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(nav.getByRole("button", { name: "Ещё" })).toHaveClass("is-current");
  fireEvent.click(nav.getByRole("button", { name: "Ещё" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Учётная запись" }));
  expect(account).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("a direct report link keeps Records active in the mobile navigation", () => {
  render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/analysis/job-42"]}><MobileNavigation onAccount={() => {}} /></MemoryRouter>);
  expect(screen.getByRole("link", { name: "Записи" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Обзор" })).not.toHaveAttribute("aria-current");
});
