import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { Modal } from "./Modal";

function SheetExample() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Открыть</button>
      {open && (
        <Modal
          title="Проверка"
          closeLabel="Готово"
          onClose={() => setOpen(false)}
        >
          <p>Содержание панели</p>
        </Modal>
      )}
    </>
  );
}

afterEach(() => {
  jest.useRealTimers();
});

test("sheet stays mounted while closing, then restores scrolling and trigger focus", () => {
  jest.useFakeTimers();
  render(<SheetExample />);
  const trigger = screen.getByRole("button", { name: "Открыть" });
  trigger.focus();
  fireEvent.click(trigger);
  expect(document.body.style.overflow).toBe("hidden");
  fireEvent.click(screen.getByRole("button", { name: "Готово" }));
  expect(screen.getByRole("dialog")).toHaveClass("modal-closing");
  act(() => {
    jest.advanceTimersByTime(220);
  });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(document.body.style.overflow).toBe("");
  expect(trigger).toHaveFocus();
});

test("Escape and repeated close actions dismiss the sheet only once", () => {
  jest.useFakeTimers();
  const close = jest.fn();
  render(
    <Modal title="Кадр" onClose={close}>
      Кадр
    </Modal>,
  );
  fireEvent(
    screen.getByRole("dialog"),
    new Event("cancel", { bubbles: true, cancelable: true }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Закрыть окно" }));
  act(() => {
    jest.advanceTimersByTime(220);
  });
  expect(close).toHaveBeenCalledTimes(1);
});

test("reduced motion skips the closing delay", () => {
  const original = window.matchMedia;
  window.matchMedia = jest.fn().mockReturnValue({ matches: true });
  const close = jest.fn();
  try {
    render(
      <Modal title="Кадр" onClose={close}>
        Кадр
      </Modal>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Закрыть окно" }));
    expect(close).toHaveBeenCalledTimes(1);
  } finally {
    window.matchMedia = original;
  }
});
