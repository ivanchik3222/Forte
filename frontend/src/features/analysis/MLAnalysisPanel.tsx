import { useEffect, useState } from 'react';
import { apiRequest, mediaUrl } from '../../api/client';
import { useResource } from '../workspace/useResource';
import { MLJob, observationName, parseMLJob } from './ml';
import { timecode } from './types';

export function MLAnalysisPanel({ mediaId, onSeek }: { mediaId: string; onSeek: (sec: number) => void }) {
  const [submitted, setSubmitted] = useState<MLJob | null>(null);
  const [profile, setProfile] = useState('forte_open');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
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
    <div className="section-heading"><div><h2 id="ml-analysis-title">Результат анализа</h2>
      <p>Вывод по записи, доказательства и нормативные основания.</p></div></div>
    <p className="notice">Автоматический результат показывает признаки возможных нарушений. Окончательное решение принимает специалист.</p>
    {(!job || job.status === 'failed') && <div className="settings-save">
      <label>Профиль камеры <select aria-label="Профиль камеры" value={profile} onChange={e => setProfile(e.target.value)}>
        <option value="forte_open">Forte Open · 464×848</option><option value="full_frame">Другая камера · полный кадр</option>
      </select></label>
      <button className="button button-primary" disabled={busy || resource.loading} onClick={() => void run()}>
        {busy ? 'Постановка в очередь…' : 'Запустить анализ'}</button>
    </div>}
    {(error || resource.error || job?.error) && <p role="alert">{error || resource.error || job?.error}</p>}
    {active && <p role="status">{job?.status === 'queued' ? 'Видео в очереди. Анализ начнётся автоматически.' : job?.stage === 'assessing_rules' ? 'Проверяем действия по нормативам и выбираем доказательства…' : job?.stage === 'describing_actions' ? 'Интервалы проверены. Локальная модель описывает действия…' : 'Ищем эпизоды, требующие внимания…'} Статус обновляется автоматически.</p>}
    {result && <>
      {assessed ? <div className={`ml-verdict ml-verdict-${result.verdict}`} role="status">
        <span>Итог проверки</span>
        <h3>{result.verdict === 'violation' ? 'Обнаружены признаки возможных нарушений' : 'Нарушение не обнаружено'}</h3>
        <p>{result.verdict === 'violation' ? `Выделено эпизодов: ${result.violations.length}. Ниже — основания каждого вывода.` : 'В проверенных фрагментах модель не обнаружила признаков нарушения известных правил.'}</p>
      </div> : <p role="status">{result.coverage_status === 'partial' ? 'Запись обработана частично. Есть участки без результата.' : 'Наблюдения готовы. Требуется ручная проверка.'}</p>}
      {result.assessment_coverage === 'partial' && <p role="alert">Проверка правил выполнена частично: есть неразборчивые или необработанные фрагменты. Итог относится к проверенной части записи.</p>}
      {assessed && <div className="ml-findings">{result.violations.map((v,i) => <article className="ml-finding" key={`${v.rule_id}-${v.timecode_sec}-${i}`}>
        <div className="ml-finding-heading"><span>Эпизод {String(i+1).padStart(2,'0')}</span>
          <button className="text-button" onClick={()=>onSeek(v.timecode_sec)}>{timecode(v.timecode_sec)} · Смотреть в видео</button></div>
        <h3>{v.type}</h3><p>{v.visible_fact}</p>
        <div className="ml-evidence-grid">{v.evidence_frames.map((f,j)=><button className="ml-evidence-card" key={j} onClick={()=>onSeek(f.timestamp_sec)}>
          <img src={mediaUrl(f.image_url)} alt={`Доказательство эпизода ${i+1}, ${timecode(f.timestamp_sec)}`} loading="lazy" referrerPolicy="no-referrer" />
          <span>{timecode(f.timestamp_sec)} · {f.explanation}</span>
        </button>)}</div>
        <div className="ml-rule-basis"><strong>{v.classification_status === 'unclassified' ? 'Классификация не завершена' : 'Почему это требует внимания'}</strong><p>{v.explanation}</p>
          {v.rule ? <>
          <a href={v.rule.url} target="_blank" rel="noreferrer">{v.rule.title} · п. {v.rule.section} ↗</a>
          <p>{v.rule.explanation}</p><small>Редакция источника: {v.rule.revision}</small></> :
          <p role="note">Тип и нормативное основание не установлены. Проверьте эпизод вручную; ссылка на правило не подставляется автоматически.</p>}</div>
      </article>)}</div>}
      {gaps.length > 0 && <p className="notice">Нет результата: {gaps.map(w => `${timecode(w.start_sec)}–${timecode(w.end_sec)}`).join(', ')}.</p>}
      {result.candidate_status === 'unsupported_camera' && <p className="notice">Для этого ракурса используется локальная визуальная модель по полному кадру. Детектор исходной камеры 464×848 не применяется.</p>}
      {['failed', 'time_budget_exceeded'].includes(result.caption_status || '') && <p role="alert">Описания действий не готовы. Результат поиска эпизодов сохранён; проверьте запись по таймкодам.</p>}
      {result.source_seen_during_training && <p className="muted">Эта запись участвовала в обучении. Результат на ней не является независимой проверкой точности.</p>}
      <p>{result.processed_frames} {candidate ? 'отметок времени' : 'кадров'} · обработка {result.elapsed_seconds.toFixed(1)} с</p>
      <details className="ml-extra-observations"><summary>Дополнительные наблюдения и кадры ({result.events.length + (result.observations?.length || 0)})</summary>
      <h3>{textEvents ? 'Кадры из записи' : 'Кадры с найденными объектами'}</h3>
      <div className="ml-evidence-grid">{result.evidence_frames.map((e, i) => <button key={i} className="ml-evidence-card" onClick={() => onSeek(e.timestamp_sec)}>
        <img src={mediaUrl(e.image_url)} alt={`${textEvents ? 'Кадр' : 'Объекты'} в ${timecode(e.timestamp_sec)}`} loading="lazy" referrerPolicy="no-referrer" />
        <span>{timecode(e.timestamp_sec)}{textEvents ? ' · Смотреть эпизод' : ` · ${e.boxes.length} объектов`}</span>
      </button>)}</div>
      <h3>{candidate ? 'Эпизоды для проверки' : 'Наблюдаемые интервалы'} ({result.events.length})</h3>
      {!result.events.length && <p>Устойчивые наблюдения не сформированы. Это не означает, что нарушений нет.</p>}
      <div className="ml-event-list">{result.events.slice(0, 100).map((e, i) => <button key={i} className={`button button-outline${textEvents ? ' ml-caption-event' : ''}`} onClick={() => onSeek(e.timecode_sec ?? e.start_sec)}>
        <span>{timecode(e.start_sec)}–{timecode(e.end_sec)} · {observationName(e.kind)}</span>
        {e.description && <span className="ml-caption-description">{e.description}</span>}
      </button>)}</div>
      {result.events.length > 100 && <p>Показаны первые 100 интервалов. Полный результат доступен в JSON.</p>}
      {result.engine === 'reviewed_pipeline' && <>
        <h3>Описания видимых действий ({result.observations?.length || 0})</h3>
        <div className="ml-event-list">{result.observations?.slice(0, 100).map((e, i) => <button key={i} className="button button-outline ml-caption-event" onClick={() => onSeek(e.start_sec)}>
          <span>{timecode(e.start_sec)}–{timecode(e.end_sec)} · {observationName(e.kind)}</span>
          <span className="ml-caption-description">{e.description}</span>
        </button>)}</div>
        {!result.observations?.length && <p>Подтверждаемые кадрами описания не сформированы.</p>}
      </>}
      <p className="muted">{textEvents ? 'Дополнительные наблюдения сами по себе не являются нарушениями.' : 'Близость объектов на изображении не доказывает контакт, передачу или пересчёт денег.'} Для другой камеры качество пока не проверено.</p>
      </details>
      <button className="text-button" onClick={resource.refresh}>Обновить кадры и ссылки</button>
    </>}
  </section>;
}
