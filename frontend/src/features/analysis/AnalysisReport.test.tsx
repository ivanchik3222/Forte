import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AnalysisReport } from "./AnalysisReport";
import { MLJob } from "./ml";

const job: MLJob = { job_id: "report-test", media_id: "media-test", status: "done", camera_profile: "forte_open", error: null,
  result: { verdict: "requires_review", violations: [], rule_evaluation: "not_performed", processed_frames: 1, sampled_fps: 2,
    elapsed_seconds: 1, model_sha256: "a".repeat(64), frames: [{ timestamp_sec: 1, boxes: [] }], events: [],
    evidence_frames: [{ timestamp_sec: 1, image_url: "/api/v1/jobs/report-test/evidence/0?token=signed", boxes: [] }] } };
const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });

test("report embeds frames and reviewer text; failed downloads cannot create an incomplete report", async () => {
  let fail = true;
  global.fetch = jest.fn(async input => {
    const logo = String(input).endsWith(".svg");
    return { ok: logo || !fail, blob: async () => new Blob([logo ? '<svg xmlns="http://www.w3.org/2000/svg" />' : "jpeg"], { type: logo ? "image/svg+xml" : "image/jpeg" }) } as Response;
  });
  render(<AnalysisReport job={job} context={{ fileName: "test.mov" }} />);
  fireEvent.change(screen.getByLabelText("Подразделение"), { target: { value: "Отделение 12" } });
  fireEvent.change(screen.getByLabelText("Комментарий к отчёту"), { target: { value: "Нужен повторный просмотр." } });
  fireEvent.click(screen.getByRole("button", { name: "Открыть готовый отчёт" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось загрузить кадры");
  expect(screen.queryByTitle("Предпросмотр отчёта")).not.toBeInTheDocument();
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "Открыть готовый отчёт" }));
  const preview = await screen.findByTitle("Предпросмотр отчёта");
  expect(preview.getAttribute("srcdoc")).toContain("Отделение 12");
  expect(preview.getAttribute("srcdoc")).toContain("Нужен повторный просмотр.");
  expect(preview.getAttribute("srcdoc")).toContain("data:image/jpeg;base64,");
  expect(preview.getAttribute("srcdoc")).not.toContain("token=signed");
  expect(preview).toHaveAttribute("sandbox", "allow-same-origin allow-modals");
  fireEvent.load(preview);
  await waitFor(() => expect(screen.getByRole("button", { name: "Печать / сохранить PDF" })).toBeEnabled());
});

test("unfinished analysis displays the report placeholder without fabricated content", () => {
  render(<AnalysisReport job={{ ...job, status: "processing", result: null }} context={{ fileName: "test.mov" }} />);
  expect(screen.getByText(/Форма заполнится результатами/)).toBeVisible();
  expect(screen.queryByRole("button", { name: "Открыть готовый отчёт" })).not.toBeInTheDocument();
});
