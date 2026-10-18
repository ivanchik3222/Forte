import { buildReportDocument, reportConclusion } from "./reportDocument";
import { MLJob } from "./ml";

const image = "data:image/jpeg;base64,YWJj";
export const reportJob: MLJob = { job_id: "test-job", media_id: "test-media", status: "done", camera_profile: "forte_open", error: null,
  result: { engine: "reviewed_pipeline", candidate_status: "candidates_found", caption_status: "partial", source_seen_during_training: false,
    verdict: "requires_review", violations: [], rule_evaluation: "not_performed", processed_frames: 1, sampled_fps: 2, elapsed_seconds: 10,
    model_sha256: "a".repeat(64), frames: [{ timestamp_sec: 7.1, boxes: [] }], coverage_status: "partial",
    coverage_windows: [{ start_sec: 10, end_sec: 20, status: "not_processed" }],
    events: Array.from({ length: 105 }, (_, index) => ({ kind: "bank_event_candidate", start_sec: index, end_sec: index + .5, mean_detector_confidence: null, description: `Эпизод ${index + 1}` })),
    observations: [{ kind: "object_handover", start_sec: 7.1, end_sec: 7.8, description: "Qwen: человек передаёт предмет.", mean_detector_confidence: null }],
    evidence_frames: [{ timestamp_sec: 7.1, image_url: "/api/v1/jobs/test-job/evidence/0?token=private", boxes: [] }],
  } };
const create = (job = reportJob, note = "Комментарий проверяющего") => buildReportDocument(job, { fileName: "camera.mov", duration: 120 },
  { department: "Отделение № 12", reviewer: "Проверяющий", note }, { logo: image, images: { [reportJob.result!.evidence_frames[0].image_url]: image } }, "2026-10-18T10:00:00Z");

test("report includes every interval, Qwen descriptions, evidence and explicit assessment gaps", () => {
  const html = create();
  expect(html).toContain("Эпизод 105"); expect(html).toContain("Qwen: человек передаёт предмет.");
  expect(html).toContain("00:07.1–00:07.8"); expect(html).toContain("00:10–00:20");
  expect(html).toContain("Нормативная оценка не выполнена");
  expect(html).not.toContain("Нарушений нет"); expect(html).toContain("обработана частично");
  expect(html).toContain(image); expect(html).not.toContain("token=private");
  expect(html).toContain("Комментарий проверяющего");
});

test("report preserves rule-backed findings and never infers a negative verdict from an empty list", () => {
  expect(reportConclusion(reportJob)).toContain("не установлено");
  const job: MLJob = { ...reportJob, result: { ...reportJob.result!, verdict: "violation", rule_evaluation: "performed", assessment_coverage: "done",
    violations: [{ type: "Признак нарушения", start_sec: 7, end_sec: 8, timecode_sec: 7.1, description: "Описание события", visible_fact: "Наблюдаемый факт", explanation: "Почему требуется внимание", requires_human_review: true, rule_id: "known-rule",
      rule: { title: "Правила № 231", section: "20", explanation: "Требование к хранению", url: "https://adilet.zan.kz/rus/docs/V1900019680", revision: "16.03.2026" },
      evidence: [{ evidence_index: 0, timestamp_sec: 7.1, explanation: "Кадр с фактом" }], evidence_frames: [{ ...reportJob.result!.evidence_frames[0], explanation: "Кадр с фактом" }],
    }] } };
  const html = create(job);
  for (const expected of ["Наблюдаемый факт", "Почему требуется внимание", "пункт 20", "Кадр с фактом", "Описание события"]) expect(html).toContain(expected);
  expect(reportConclusion(job)).toContain("признаками возможных нарушений: 1");
});

test("export escapes user and model text, embeds only image data and requires a finished result", () => {
  const attack = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
  const html = create(reportJob, attack);
  const parsed = new DOMParser().parseFromString(html, "text/html");
  expect(parsed.querySelectorAll("script,[onerror]")).toHaveLength(0);
  expect(parsed.querySelector(".note")?.textContent).toBe(attack);
  expect(() => buildReportDocument(reportJob, { fileName: "video.mov" }, { department: "", reviewer: "", note: "" }, { logo: "javascript:alert(1)", images: {} }, "2026-10-18")).toThrow();
  expect(() => create({ ...reportJob, status: "processing", result: null })).toThrow();
});
