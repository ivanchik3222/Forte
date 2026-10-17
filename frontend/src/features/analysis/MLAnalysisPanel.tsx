import { useEffect, useState } from 'react';
import { apiRequest, mediaUrl } from '../../api/client';
import { useResource } from '../workspace/useResource';
import { MLJob, observationName, parseMLJob } from './ml';
import { timecode, safeSourceUrl } from './types';

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
  const final = job?.final_answer;
  const checkStatus = (status?: string) => ({
    observed: 'Наблюдалось', not_observed: 'Не наблюдалось в проверенном интервале',
    unobservable: 'Невозможно оценить', not_evaluated: 'Проверка ещё не выполнена',
  }[status || 'not_evaluated'] || 'Невозможно оценить');
  return <section className="panel ml-analysis" aria-labelledby="ml-analysis-title">
    <div className="section-heading"><div><h2 id="ml-analysis-title">Наблюдения модели</h2>
      <p>Объекты, движения рук и временные интервалы для ручной проверки.</p></div></div>
    <p className="notice">Отсутствие бокса не подтверждает отсутствие предмета. Итог о возможных нарушениях требует классификации событий и проверки правил.</p>
    {(!job || job.status === 'failed') && <div className="settings-save">
      <label>Профиль камеры <select aria-label="Профиль камеры" value={profile} onChange={e => setProfile(e.target.value)}>
        <option value="forte_open">Forte Open · 464×848</option><option value="full_frame">Другая камера · полный кадр</option>
      </select></label>
      <button className="button button-primary" disabled={busy || resource.loading} onClick={() => void run()}>
        {busy ? 'Постановка в очередь…' : 'Найти объекты и движения'}</button>
    </div>}
    {(error || resource.error || job?.error) && <p role="alert">{error || resource.error || job?.error}</p>}
    {active && <p role="status">{job?.status === 'queued' ? 'Видео в очереди. Обработку выполняет локальный worker.' : 'Модель обрабатывает видео…'} Статус обновляется автоматически.</p>}
    {result && <>
      {final ? <section aria-label="Итог проверки">
        <h3>{final.verdict === 'violation' ? 'Обнаружены признаки возможных нарушений' : 'Нарушение не обнаружено'}</h3>
        {final.violations.map((v,i) => <article key={i}>
          <h4>{v.type}</h4><button className="text-button" onClick={() => onSeek(v.timecode_sec)}>{timecode(v.timecode_sec)}</button>
          <p>{v.description}</p>
          {v.evidence_frames.map((f,j) => <img key={j} src={`data:image/jpeg;base64,${f.image_base64}`} alt={`Кадр-доказательство ${timecode(f.timestamp_sec)}`} style={{maxHeight:260,maxWidth:'100%'}} />)}
          {v.rule && <p>{v.rule.title} · {v.rule.section}. {v.rule.explanation}{safeSourceUrl(v.rule.url) && <a href={safeSourceUrl(v.rule.url)} target="_blank" rel="noreferrer"> Нормативный источник</a>}</p>}
        </article>)}
      </section> : <>
        <p role="status">Наблюдения готовы. Требуется ручная проверка.</p>
        <p>Итог по ТЗ пока не сформирован: классификация событий ещё не выполнена.</p>
      </>}
      <div className="notice"><div>
        <p><strong>Показ удостоверения кассиру:</strong> {checkStatus(result.additional_checks?.identity_document_presentation.status)}.</p>
        <p><strong>Колебания рук клиента:</strong> {checkStatus(result.additional_checks?.customer_hand_oscillation.status)}.</p>
        <p>Цифровое удостоверение учитывается отдельно. Движения рук сами по себе не подтверждают нарушение.</p>
      </div></div>
      <p>{result.processed_frames} кадров · {result.sampled_fps} кадра/с · обработка {result.elapsed_seconds.toFixed(1)} с</p>
      <h3>Кадры с найденными объектами</h3>
      <div className="ml-evidence-grid">{result.evidence_frames.map((e, i) => <button key={i} className="ml-evidence-card" onClick={() => onSeek(e.timestamp_sec)}>
        <img src={mediaUrl(e.image_url)} alt={`Объекты в ${timecode(e.timestamp_sec)}`} loading="lazy" referrerPolicy="no-referrer" />
        <span>{timecode(e.timestamp_sec)} · {e.boxes.length} объектов</span>
      </button>)}</div>
      <h3>Наблюдаемые интервалы ({result.events.length})</h3>
      {!result.events.length && <p>Устойчивые наблюдения не сформированы. Это не означает, что нарушений нет.</p>}
      <div className="ml-event-list">{result.events.slice(0, 100).map((e, i) => <button key={i} className="button button-outline" onClick={() => onSeek(e.start_sec)}>
        {timecode(e.start_sec)}–{timecode(e.end_sec)} · {observationName(e.kind)}
      </button>)}</div>
      {result.events.length > 100 && <p>Показаны первые 100 интервалов. Полный результат доступен в JSON.</p>}
      <p className="muted">Близость объектов на изображении не доказывает контакт, передачу или пересчёт денег. Для другой камеры качество пока не проверено.</p>
      <button className="text-button" onClick={resource.refresh}>Обновить кадры и ссылки</button>
    </>}
  </section>;
}
