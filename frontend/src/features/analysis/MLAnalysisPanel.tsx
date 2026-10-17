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
  return <section className="panel ml-analysis" aria-labelledby="ml-analysis-title">
    <div className="section-heading"><div><h2 id="ml-analysis-title">Наблюдения модели</h2>
      <p>Объекты, движения рук и временные интервалы для ручной проверки.</p></div></div>
    <p className="notice">Модель может пропускать деньги и руки. Отсутствие бокса не подтверждает отсутствие предмета. Автоматическая оценка нарушений отключена.</p>
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
      <p role="status">Наблюдения готовы. Требуется ручная проверка.</p>
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
