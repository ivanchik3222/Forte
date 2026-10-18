import { MLJob, MLEvent, observationName } from "./ml";
import { evidenceTime, intervalTime } from "./playback";

export interface ReportFields { department: string; reviewer: string; note: string }
export interface ReportContext { fileName: string; uploadedAt?: string; duration?: number | null }
export interface ReportAssets { logo: string; images: Record<string, string> }
const escape = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, character =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]!));
const paragraph = (value: unknown) => `<p>${escape(value)}</p>`;
const date = (value: string) => new Date(value).toLocaleString("ru-RU", { timeZone: "Asia/Almaty" });

export function reportConclusion(job: MLJob) {
  const result = job.result;
  if (!result) return "Анализ ещё не завершён. Итог не сформирован.";
  if (result.rule_evaluation !== "performed") return "Нормативная оценка не выполнена. Наблюдения требуют проверки специалистом; наличие или отсутствие нарушений не установлено.";
  return result.verdict === "violation"
    ? `Выделено эпизодов с признаками возможных нарушений: ${result.violations.length}. Факты, основания и кадры приведены ниже. Требуется проверка специалистом.`
    : "В проверенных фрагментах модель не обнаружила признаков нарушения известных правил.";
}

export const REPORT_STYLE = `
*{box-sizing:border-box}body{margin:0;background:#efedf0;color:#242126;font:14px/1.65 Arial,sans-serif}
.forte-report{width:min(210mm,100%);padding:18mm;margin:20px auto;background:#fff;overflow-wrap:anywhere}
header{display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:3px solid #a31551;padding-bottom:20px;margin-bottom:28px}
header img{width:130px;height:auto}header span{color:#776472;font-size:11px;text-align:right}h1{font-size:27px;line-height:1.3;margin:12px 0}h2{font-size:18px;margin:28px 0 12px;border-bottom:1px solid #e4dce2;padding-bottom:9px}h3{font-size:15px;margin:18px 0 8px}
p{margin:9px 0;white-space:pre-wrap}.label{color:#a31551;font-size:11px;letter-spacing:1px;text-transform:uppercase}.meta{display:grid;grid-template-columns:1fr 1fr;gap:13px;margin:24px 0}.meta p{margin:0}.meta strong{display:block;color:#7a6d77;font-size:11px;font-weight:400}
.conclusion{padding:18px;border-left:3px solid #a31551;background:#faf4f7}.warning{padding:12px 16px;background:#f4f6fa;border-left:3px solid #5785aa}.finding{padding-bottom:14px}.muted{font-size:12px;color:#726470}table{border-collapse:collapse;width:100%;font-size:12px}th,td{text-align:left;vertical-align:top;padding:10px 8px;border-bottom:1px solid #e6e0e5}th{color:#7b3560;background:#faf4f7}td:first-child{width:115px;font-variant-numeric:tabular-nums}td p{margin:3px 0}
.frames{display:grid;grid-template-columns:1fr 1fr;gap:18px}figure{margin:0;break-inside:avoid}figure img{width:100%;height:310px;object-fit:contain;background:#151215}figcaption{font-size:12px;padding:7px 0}.technical{font-size:11px;color:#73626e}footer{border-top:1px solid #d9cbd4;margin-top:30px;padding-top:16px;font-size:11px;color:#786573}.note{min-height:75px;white-space:pre-wrap}.signature{margin-top:28px;display:flex;justify-content:space-between;gap:15px}
@media screen and (max-width:600px){.forte-report{margin:0;padding:22px}.meta{grid-template-columns:1fr}.frames{grid-template-columns:1fr}h1{font-size:23px}header img{width:100px}td:first-child{width:88px}}
@page{size:A4;margin:14mm}@media print{body{background:#fff;font-size:10pt}.forte-report{width:auto;margin:0;padding:0}h1{font-size:22pt}h2,h3{break-after:avoid}.meta,.conclusion,.warning{break-inside:avoid}thead{display:table-header-group}tr{break-inside:avoid}.frames img{height:85mm}a{color:inherit}footer{font-size:8pt}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
`;

/** The narrative is a faithful rendering of the validated result, never a second verdict. */
export function buildReportDocument(job: MLJob, context: ReportContext, fields: ReportFields, assets: ReportAssets, generatedAt: string) {
  const result = job.result;
  if (job.status !== "done" || !result) throw new Error("Отчёт доступен после завершения анализа.");
  const safeImage = (value: string | undefined) => {
    if (!value || !/^data:image\/(?:jpeg|png|webp|svg\+xml);base64,[A-Za-z0-9+/=]+$/.test(value)) throw new Error("Не удалось подготовить изображения отчёта.");
    return value;
  };
  const eventsTable = (events: MLEvent[], heading: string) => `<h2>${heading} (${events.length})</h2>` + (events.length
    ? `<table><thead><tr><th>Интервал</th><th>Наблюдение</th></tr></thead><tbody>${events.map(event => `<tr><td>${intervalTime(event.start_sec, event.end_sec)}</td><td><strong>${escape(observationName(event.kind))}</strong>${event.description ? paragraph(event.description) : ""}${event.timecode_sec !== undefined ? `<p class="muted">Ключевой момент: ${evidenceTime(event.timecode_sec)}</p>` : ""}</td></tr>`).join("")}</tbody></table>`
    : paragraph("Наблюдения этого типа не сформированы. Это не является выводом об отсутствии нарушений."));
  const gaps = result.coverage_windows?.filter(window => window.status !== "done") || [];
  const incomplete = result.coverage_status === "partial" || result.assessment_coverage === "partial";
  const findings = result.violations.map((finding, index) => `<section class="finding"><h3>${index + 1}. ${escape(finding.type)}</h3>
    <p class="label">${intervalTime(finding.start_sec, finding.end_sec)} · Ключевой момент ${evidenceTime(finding.timecode_sec)}</p>
    ${paragraph(finding.description)}<p><strong>Что видно:</strong> ${escape(finding.visible_fact)}</p><p><strong>Обоснование:</strong> ${escape(finding.explanation)}</p>
    ${finding.rule ? `<p><strong>Нормативное основание:</strong> ${escape(finding.rule.title)}, пункт ${escape(finding.rule.section)}. Редакция: ${escape(finding.rule.revision)}.</p>${paragraph(finding.rule.explanation)}<p class="muted">${escape(finding.rule.url)}</p>` : paragraph("Тип и нормативное основание не установлены. Эпизод требует ручной проверки.")}
    <p><strong>Кадры-доказательства:</strong></p><ul>${finding.evidence_frames.map(frame => `<li>${evidenceTime(frame.timestamp_sec)} — ${escape(frame.explanation)}</li>`).join("")}</ul></section>`).join("");
  const frames = result.evidence_frames.map((frame, index) => `<figure><img src="${safeImage(assets.images[frame.image_url])}" alt="Кадр ${index + 1}" /><figcaption><strong>Кадр ${index + 1} · ${evidenceTime(frame.timestamp_sec)}</strong>${frame.boxes.length ? `<br>Объектов: ${frame.boxes.length}. ${escape(frame.boxes.map(box => `${({ person: "человек", hand: "рука", cash: "деньги", bag: "сумка", storage_cabinet: "шкаф" } as Record<string, string>)[box.label] || box.label} — ${(box.confidence * 100).toFixed(1)}%`).join("; "))}` : ""}</figcaption></figure>`).join("");
  const html = `<article class="forte-report"><header><img src="${safeImage(assets.logo)}" alt="Forte" /><span>CONTROL / ВИДЕОАНАЛИТИКА<br>Проект отчёта · проверка специалистом</span></header>
    <p class="label">Отчёт № ${escape(job.job_id)}</p><h1>Проверка кассовых операций по видеозаписи</h1>
    <div class="meta"><p><strong>Видеозапись</strong>${escape(context.fileName)}</p><p><strong>Сформирован · время Астаны</strong>${date(generatedAt)}</p><p><strong>Подразделение</strong>${escape(fields.department || "Не указано")}</p><p><strong>Проверяющий</strong>${escape(fields.reviewer || "Не указан")}</p><p><strong>Длительность записи</strong>${context.duration == null ? "Не определена" : evidenceTime(context.duration)}</p><p><strong>Загружена · время Астаны</strong>${context.uploadedAt ? date(context.uploadedAt) : "Не указано"}</p></div>
    <h2>01 / Итог анализа</h2><div class="conclusion">${paragraph(reportConclusion(job))}</div>
    ${incomplete ? '<p class="warning">Запись или нормативная оценка обработана частично. Итог относится только к проверенным фрагментам; отсутствие результата на других участках не означает отсутствие нарушений.</p>' : ""}
    ${gaps.length ? `<p>Участки без результата: ${gaps.map(window => `${intervalTime(window.start_sec, window.end_sec)} (${window.status === "invalid_model_output" ? "не удалось интерпретировать" : "не обработан"})`).join("; ")}.</p>` : ""}
    ${["partial", "failed", "time_budget_exceeded"].includes(result.caption_status || "") ? '<p class="warning">Описания действий сформированы не полностью или недоступны. Сохранённые интервалы требуют просмотра исходной записи.</p>' : ""}
    <h2>02 / События, требующие проверки (${result.violations.length})</h2>${findings || paragraph(result.rule_evaluation === "performed" ? "Модель не выделила эпизодов с признаками нарушения известных правил в проверенных фрагментах." : "Нормативная оценка не выполнена; список нарушений не сформирован.")}
    ${eventsTable(result.events, "03 / Наблюдаемые интервалы")}${result.observations ? eventsTable(result.observations, "04 / Описания видимых действий") : ""}
    <h2>Кадры из записи (${result.evidence_frames.length})</h2><div class="frames">${frames || paragraph("Кадры не переданы анализатором.")}</div>
    <p class="muted">Рамки и проценты относятся к обнаруженным объектам, а не к вероятности нарушения. Наблюдение само по себе не устанавливает виновность или намерение человека.</p>
    <h2>Комментарий проверяющего</h2><p class="note">${escape(fields.note || "Не заполнен.")}</p><div class="signature"><span>Проверил: ${escape(fields.reviewer || "________________")}</span><span>Подпись: ________________</span></div>
    <h2>Данные для сверки результата</h2><div class="technical"><p>ID записи: ${escape(job.media_id)}<br>ID анализа: ${escape(job.job_id)}<br>Обработано отметок: ${result.processed_frames}; время обработки: ${result.elapsed_seconds.toFixed(1)} с.<br>Нормативная оценка: ${result.rule_evaluation === "performed" ? "выполнена" : "не выполнена"}${result.assessment_version ? `; версия ${escape(result.assessment_version)}` : ""}.<br>SHA-256 модели: ${escape(result.model_sha256)}</p>${result.source_seen_during_training ? paragraph("Запись участвовала в обучении. Этот результат не является независимой проверкой точности.") : ""}</div>
    <footer>Forte Control · Отчёт системы анализа, подготовленный для проверки специалистом. Не является утверждённым бланком банка. Обязательный машинный результат для жюри передаётся отдельно через API в формате JSON.</footer></article>`;
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>Forte Control — отчёт ${escape(job.job_id)}</title><style>${REPORT_STYLE}</style></head><body>${html}</body></html>`;
}
