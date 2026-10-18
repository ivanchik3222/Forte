import { LoadingMark, LoadingState } from "../../components/LoadingState";
import { t, useLocale } from "../../i18n";
import { useEffect, useState } from 'react';
import { apiRequest } from '../../api/client';
import { useResource } from '../workspace/useResource';
import { MLJob, observationName, parseMLJob } from './ml';
import { timecode } from './types';
import { Icon } from '../../components/Icon';
import { EvidenceGallery } from './EvidenceGallery';
import { AnalysisReport } from './AnalysisReport';
import { ReportContext } from './reportDocument';
import { intervalTime, SeekToEvidence } from './playback';
import '../../styles/analysis-review.css';

export function MLAnalysisPanel({ mediaId, onSeek, context }: { mediaId: string; onSeek: SeekToEvidence; context?: ReportContext }) {
  const locale = useLocale();
  const [submitted, setSubmitted] = useState<MLJob | null>(null);
  const [profile, setProfile] = useState('forte_open');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [eventLimit, setEventLimit] = useState(100);
  const [observationLimit, setObservationLimit] = useState(100);
  const parse = (value: unknown) => {
    const next = parseMLJob(value);
    if (next && next.media_id !== mediaId) throw new Error('Сервер вернул анализ другой записи.');
    return next;
  };
  const resource = useResource(`/media/${encodeURIComponent(mediaId)}/analysis`, parse);
  const job = resource.data ?? submitted;
  const active = job?.status === 'queued' || job?.status === 'processing';
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(resource.refresh, 3000);
    return () => clearInterval(timer);
  }, [active, resource.refresh]);
  const run = async () => {
    setBusy(true); setError('');
    try {
      const next = parse(await apiRequest(`/api/v1/media/${encodeURIComponent(mediaId)}/analyze`, {
        method: 'POST', body: JSON.stringify({ camera_profile: profile }),
      }));
      setSubmitted(next); resource.refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось запустить анализ.'); }
    finally { setBusy(false); }
  };
  const result = job?.result;
  const descriptive = result?.engine === 'dense_vlm';
  const candidate = result?.engine === 'reviewed_temporal' || result?.engine === 'reviewed_pipeline';
  const textEvents = descriptive || candidate;
  const gaps = result?.coverage_windows?.filter(w => w.status !== 'done') || [];
  const assessed = result?.rule_evaluation === 'performed';
  return <section className="panel ml-analysis" aria-labelledby="ml-analysis-title">
    <div className="section-heading"><div><h2 id="ml-analysis-title">{t("Результат анализа")}</h2>
      <p>{t("Вывод по записи, доказательства и нормативные основания.")}</p></div></div>
    {result && <nav className="analysis-section-nav" aria-label={t("Разделы результата")}>
      <a href="#analysis-intervals"><Icon name="play" size={17} />{t("Интервалы")}</a>
      <a href="#analysis-frames"><Icon name="image" size={17} />{t("Кадры")}</a>
      <a href="#analysis-report"><Icon name="file" size={17} />{t("Отчёт")}</a>
    </nav>}
    {locale !== "ru" && <p className="muted" lang={locale}>{t("Описание модели показано на языке источника.")}</p>}
    {resource.loading && !active && <LoadingState label="Загружаем результат анализа…" variant={job ? "inline" : "panel"} />}
    {(!job || job.status === 'failed') && <div className="settings-save">
      <label>{t("Профиль камеры ")}<select aria-label={t("Профиль камеры")} value={profile} onChange={e => setProfile(e.target.value)}>
        <option value="forte_open">Forte Open · 464×848</option><option value="full_frame">{t("Другая камера · полный кадр")}</option>
      </select></label>
      <button className="button button-primary" disabled={busy || resource.loading} onClick={() => void run()}>
        {busy && <LoadingMark small />}{t(busy ? 'Постановка в очередь…' : 'Запустить анализ')}</button>
    </div>}
    {t((error || resource.error || job?.error) && <p role="alert">{t(error || resource.error || job?.error)}</p>)}
    {active && <LoadingState label={t(job?.status === 'queued' ? 'Видео в очереди. Анализ начнётся автоматически.' : job?.stage === 'assessing_rules' ? 'Проверяем действия по нормативам и выбираем доказательства…' : job?.stage === 'describing_actions' ? 'Интервалы проверены. Локальная модель описывает действия…' : 'Ищем эпизоды, требующие внимания…') + t(" Статус обновляется автоматически.")} />}
    {result && <>
      {assessed ? <div className={`ml-verdict ml-verdict-${result.verdict}`} role="status">
        <span>{t("Итог проверки")}</span>
        <h3>{t(result.verdict === 'violation' ? 'Обнаружены признаки возможных нарушений' : 'Нарушение не обнаружено')}</h3>
        <p>{t(result.verdict === 'violation' ? t("Выделено эпизодов: {0}. Ниже — основания каждого вывода.", [result.violations.length]) : 'В проверенных фрагментах модель не обнаружила признаков нарушения известных правил.')}</p>
      </div> : <p className="analysis-verdict-pending" role="status">{t(result.coverage_status === 'partial' ? 'Запись обработана частично. Есть участки без результата.' : 'Наблюдения готовы. Требуется ручная проверка.')}</p>}
      {result.assessment_coverage === 'partial' && <p role="alert">{t("Проверка правил выполнена частично: есть неразборчивые или необработанные фрагменты. Итог относится к проверенной части записи.")}</p>}
      {assessed && <div className="ml-findings">{result.violations.map((v,i) => <article className="ml-finding" key={`${v.rule_id}-${v.timecode_sec}-${i}`}>
        <div className="ml-finding-heading"><span>{t("Эпизод ")}{String(i+1).padStart(2,'0')}</span>
          <button className="button button-outline" onClick={()=>onSeek(v.start_sec, { start: v.start_sec, end: v.end_sec, label: v.type })}><Icon name="play" size={16} />{intervalTime(v.start_sec, v.end_sec)}{t(" · Смотреть в видео")}</button></div>
        <h3>{v.type}</h3><p>{v.visible_fact}</p>
        <EvidenceGallery frames={v.evidence_frames.map(frame => ({ ...frame, caption: frame.explanation }))} onSeek={onSeek} />
        <div className="ml-rule-basis"><strong>{t(v.classification_status === 'unclassified' ? 'Классификация не завершена' : 'Почему это требует внимания')}</strong><p>{v.explanation}</p>
          {v.rule ? <>
          <a href={v.rule.url} target="_blank" rel="noreferrer">{v.rule.title}{t(" · п. ")}{t(v.rule.section)} ↗</a>
          <p>{v.rule.explanation}</p><small>{t("Редакция источника: ")}{t(v.rule.revision)}</small></> :
          <p role="note">{t("Тип и нормативное основание не установлены. Проверьте эпизод вручную; ссылка на правило не подставляется автоматически.")}</p>}</div>
      </article>)}</div>}
      {gaps.length > 0 && <p className="notice">{t("Нет результата: ")}{t(gaps.map(w => `${timecode(w.start_sec)}–${timecode(w.end_sec)}`).join(', '))}.</p>}
      {result.candidate_status === 'unsupported_camera' && <p className="notice">{t("Для этого ракурса используется локальная визуальная модель по полному кадру. Детектор исходной камеры 464×848 не применяется.")}</p>}
      {['failed', 'time_budget_exceeded'].includes(result.caption_status || '') && <p role="alert">{t("Описания действий не готовы. Результат поиска эпизодов сохранён; проверьте запись по таймкодам.")}</p>}
      {result.source_seen_during_training && <p className="muted">{t("Эта запись участвовала в обучении. Результат на ней не является независимой проверкой точности.")}</p>}
      <section className="analysis-observations" id="analysis-intervals" aria-labelledby="analysis-intervals-title">
        <div className="analysis-block-heading"><div><p className="eyebrow">{t("01 / СОБЫТИЯ")}</p><h3 id="analysis-intervals-title">{t(candidate ? 'Эпизоды для проверки' : 'Наблюдаемые интервалы')} ({result.events.length})</h3><p>{t("Нажмите на интервал, чтобы посмотреть этот фрагмент видео.")}</p></div><Icon name="play" size={25} /></div>
        {!result.events.length && <p>{t("Устойчивые наблюдения не сформированы. Это не означает, что нарушений нет.")}</p>}
        <div className="ml-event-list">{result.events.slice(0, eventLimit).map((event, index) => <button key={index} className="analysis-interval" onClick={() => onSeek(event.start_sec, { start: event.start_sec, end: event.end_sec, label: t(observationName(event.kind)) })}>
          <span className="interval-play"><Icon name="play" size={17} /></span><span className="interval-copy"><strong>{intervalTime(event.start_sec, event.end_sec)}</strong><span>{t(observationName(event.kind))}</span>{event.description && <p>{event.description}</p>}</span><Icon name="arrow" size={17} />
        </button>)}</div>
        {result.events.length > eventLimit && <button className="button button-outline" onClick={() => setEventLimit(value => value + 100)}>{t("Показать ещё интервалы")}</button>}
        {result.engine === 'reviewed_pipeline' && <>
          <h3 className="analysis-captions-title">{t("Описания видимых действий (")}{result.observations?.length || 0})</h3>
          <div className="ml-event-list">{result.observations?.slice(0, observationLimit).map((event, index) => <button key={index} className="analysis-interval" onClick={() => onSeek(event.start_sec, { start: event.start_sec, end: event.end_sec, label: t(observationName(event.kind)) })}>
            <span className="interval-play"><Icon name="play" size={17} /></span><span className="interval-copy"><strong>{intervalTime(event.start_sec, event.end_sec)}</strong><span>{t(observationName(event.kind))}</span><p>{event.description}</p></span><Icon name="arrow" size={17} />
          </button>)}</div>
          {(result.observations?.length || 0) > observationLimit && <button className="button button-outline" onClick={() => setObservationLimit(value => value + 100)}>{t("Показать ещё описания")}</button>}
          {!result.observations?.length && <p>{t("Подтверждаемые кадрами описания не сформированы.")}</p>}
        </>}
      </section>
      <section id="analysis-frames" aria-labelledby="analysis-frames-title" className="analysis-frames">
        <div className="analysis-block-heading"><div><p className="eyebrow">{t("02 / КАДРЫ")}</p><h3 id="analysis-frames-title">{t(textEvents ? 'Кадры из записи' : 'Кадры с найденными объектами')}</h3><p>{t("Откройте кадр, чтобы рассмотреть детали в большом размере.")}</p></div><Icon name="image" size={25} /></div>
        <EvidenceGallery frames={result.evidence_frames.map(frame => ({ ...frame, caption: textEvents ? t("Кадр из записи") : t("Объектов: {0}", [frame.boxes.length]) }))} onSeek={onSeek} />
        {!result.evidence_frames.length && <p>{t("Кадры не переданы анализатором.")}</p>}
      </section>
      <p className="analysis-review-note"><Icon name="info" size={18} />{t(textEvents ? 'Наблюдения требуют проверки по исходному видео.' : 'Близость объектов на изображении не доказывает контакт, передачу или пересчёт денег.')}</p>
      <div className="analysis-processing-meta"><span>{t("Обработано отметок: {0}", [result.processed_frames])}</span><span>{t("Время анализа: {0} с", [result.elapsed_seconds.toFixed(1)])}</span></div>
      <button className="text-button" disabled={resource.loading} onClick={resource.refresh}>{t("Обновить кадры и ссылки")}</button>
    </>}
    <AnalysisReport job={job} context={context || { fileName: mediaId }} />
  </section>;
}
