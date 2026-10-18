import { useEffect, useRef, useState } from "react";
import { mediaUrl } from "../../api/client";
import { Icon } from "../../components/Icon";
import { LoadingMark } from "../../components/LoadingState";
import { Modal } from "../../components/Modal";
import { t, useLocale } from "../../i18n";
import { useAuthStore } from "../../store/useAuthStore";
import { MLJob } from "./ml";
import { buildReportDocument, ReportContext, reportConclusion } from "./reportDocument";

async function inlineImage(url: string, signal: AbortSignal, logo = false) {
  const response = await fetch(url, { signal, credentials: "omit", referrerPolicy: "no-referrer" });
  if (!response.ok) throw new Error("Не удалось загрузить кадры отчёта. Обновите кадры и ссылки и повторите.");
  const blob = await response.blob();
  if (blob.size > 12 * 1024 * 1024 || !(logo ? /^image\/svg\+xml$/ : /^image\/(jpeg|png|webp)$/).test(blob.type)) throw new Error("Неподдерживаемый формат изображения отчёта.");
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Не удалось прочитать изображения отчёта."));
    reader.readAsDataURL(blob);
  });
}

export function AnalysisReport({ job, context }: { job: MLJob | null | undefined; context: ReportContext }) {
  useLocale();
  const user = useAuthStore(state => state.user);
  const [department, setDepartment] = useState("");
  const [reviewer, setReviewer] = useState(user?.full_name || user?.nickname || "");
  const [note, setNote] = useState("");
  const [html, setHtml] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [printReady, setPrintReady] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);
  const controller = useRef<AbortController | undefined>(undefined);
  useEffect(() => () => controller.current?.abort(), []);
  const ready = job?.status === "done" && !!job.result;
  const prepare = async () => {
    if (!ready || !job?.result || busy) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(true); setError(""); setPrintReady(false);
    try {
      const logo = await inlineImage("/forte-logo.svg", request.signal, true);
      const urls = Array.from(new Set(job.result.evidence_frames.map(item => item.image_url)));
      const images: Record<string, string> = {};
      // Bounded batches keep long reports from issuing hundreds of concurrent requests.
      for (let offset = 0; offset < urls.length; offset += 4) {
        await Promise.all(urls.slice(offset, offset + 4).map(async url => { images[url] = await inlineImage(mediaUrl(url), request.signal); }));
      }
      if (!request.signal.aborted) setHtml(buildReportDocument(job, context, { department, reviewer, note }, { logo, images }, new Date().toISOString()));
    } catch (e) {
      if (!request.signal.aborted) setError(e instanceof Error ? e.message : "Не удалось сформировать отчёт.");
    } finally { if (!request.signal.aborted) setBusy(false); }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url;
    anchor.download = `Forte-Control-report-${(job?.job_id || "record").replace(/[^a-zA-Z0-9_-]/g, "_")}.html`;
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <section className="analysis-report" id="analysis-report" aria-labelledby="analysis-report-title">
    <div className="report-intro"><span className="report-icon"><Icon name="file" size={27} /></span><div><p className="eyebrow">FORTE CONTROL / {t("ДОКУМЕНТ")}</p><h2 id="analysis-report-title">{t("Отчёт по видеозаписи")}</h2><p>{t("Итог, события, основания и кадры — в одном документе.")}</p></div></div>
    {ready ? <>
      <div className="report-form">
        <label>{t("Подразделение")}<input value={department} onChange={event => setDepartment(event.target.value)} maxLength={160} placeholder={t("Например, отделение № 12")} /></label>
        <label>{t("Проверяющий")}<input value={reviewer} onChange={event => setReviewer(event.target.value)} maxLength={160} placeholder={t("Имя и фамилия")} /></label>
        <label className="report-note-field">{t("Комментарий к отчёту")}<textarea rows={3} value={note} onChange={event => setNote(event.target.value)} maxLength={8000} placeholder={t("При необходимости добавьте контекст проверки")} /></label>
      </div>
      <div className="report-summary"><strong>{t("Текстовый итог")}</strong><p>{t(reportConclusion(job!))}</p></div>
      <div className="report-actions"><button className="button button-primary" disabled={busy} onClick={() => void prepare()}>{busy ? <LoadingMark small /> : <Icon name="file" size={18} />}{t(busy ? "Собираем отчёт и кадры…" : "Открыть готовый отчёт")}</button><p>{t("Документ на русском языке. Поля и комментарий сохранятся в скачанном отчёте.")}</p></div>
      {error && <p role="alert">{t(error)}</p>}
    </> : <p className="report-placeholder">{t("Форма заполнится результатами после завершения анализа. Здесь появятся итог, таймкоды, объяснения и кадры.")}</p>}
    {html && <Modal title={t("Отчёт по видеозаписи")} wide onClose={() => setHtml("")}>
      <div className="report-preview-actions"><button className="button button-primary" disabled={!printReady} onClick={() => { frame.current?.contentWindow?.focus(); frame.current?.contentWindow?.print(); }}><Icon name="file" size={17} />{t("Печать / сохранить PDF")}</button><button className="button button-outline" onClick={download}><Icon name="download" size={17} />{t("Скачать HTML с кадрами")}</button></div>
      <iframe ref={frame} className="report-preview" title={t("Предпросмотр отчёта")} sandbox="allow-same-origin allow-modals" srcDoc={html} onLoad={async () => {
        const document = frame.current?.contentDocument;
        if (document) await Promise.all(Array.from(document.images).map(image => image.decode?.().catch(() => undefined)));
        setPrintReady(true);
      }} />
    </Modal>}
  </section>;
}
