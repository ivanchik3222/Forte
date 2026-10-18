import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { apiRequest } from '../../api/client';
import { MLAnalysisPanel } from './MLAnalysisPanel';
import { parseMLJob } from './ml';
import { asRecord } from '../../api/workspace';
import { StatusBadge } from './HistoryTable';

jest.mock('../../api/client', () => ({
  ...jest.requireActual('../../api/client'), apiRequest: jest.fn(),
}));
const request = apiRequest as jest.Mock;
const complete = {
  job_id: 'job-1', media_id: 'media-1', status: 'done', camera_profile: 'forte_open', error: null,
  result: { verdict: 'requires_review', violations: [], rule_evaluation: 'not_performed',
    processed_frames: 1, sampled_fps: 2, elapsed_seconds: 1.5, model_sha256: 'a'.repeat(64),
    frames: [{ timestamp_sec: 1, boxes: [] }],
    events: [{ kind: 'cash_detected', start_sec: 1, end_sec: 2, mean_detector_confidence: .5 }],
    evidence_frames: [{ timestamp_sec: 1, boxes: [], image_url: '/api/v1/jobs/job-1/evidence/0?token=signed' }],
  },
};
beforeEach(() => request.mockReset());

test('shows observations immediately and opens evidence in a modal before seeking', async () => {
  request.mockResolvedValue(complete);
  const seek = jest.fn();
  render(<MLAnalysisPanel mediaId="media-1" onSeek={seek} />);
  await screen.findByText('Наблюдения готовы. Требуется ручная проверка.');
  expect(screen.getByRole('heading', { name: 'Наблюдаемые интервалы (1)' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: /Увеличить кадр 00:01/ }));
  expect(screen.getByRole('dialog', { name: 'Кадр 00:01' })).toBeVisible();
  expect(seek).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Открыть этот момент в видео' }));
  await waitFor(() => expect(seek).toHaveBeenCalledWith(1));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByText('Без признаков нарушений')).not.toBeInTheDocument();
});

test('enqueues using authenticated media API and selected camera profile', async () => {
  let submitted = false;
  request.mockImplementation(async (path, options) => {
    if (options?.method === 'POST') { submitted = true; return { ...complete, status: 'queued', result: null }; }
    return submitted ? complete : null;
  });
  render(<MLAnalysisPanel mediaId="media-1" onSeek={jest.fn()} />);
  const button = await screen.findByRole('button', { name: 'Запустить анализ' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Профиль камеры'), { target: { value: 'full_frame' } });
  fireEvent.click(button);
  await screen.findByText('Наблюдения готовы. Требуется ручная проверка.');
  expect(request).toHaveBeenCalledWith('/api/v1/media/media-1/analyze', expect.objectContaining({
    method: 'POST', body: JSON.stringify({ camera_profile: 'full_frame' }),
  }));
});

test('rejects a fabricated automatic legal verdict and unsafe evidence URL', () => {
  expect(() => parseMLJob({ ...complete, result: { ...complete.result, verdict: 'no_violation' } })).toThrow();
  expect(() => parseMLJob({ ...complete, result: { ...complete.result,
    evidence_frames: [{ timestamp_sec: 1, boxes: [], image_url: 'https://untrusted.invalid/frame.jpg' }] } })).toThrow();
  expect(() => parseMLJob({ ...complete, result: { ...complete.result,
    frames: [{ timestamp_sec: -1, boxes: [] }] } })).toThrow();
});

test('completed server analysis with no legal verdict is labelled observations', () => {
  const record = asRecord({ id: '1', file_name: 'x.mov', file_size: 10, created_at: '2026-10-17T10:00:00Z',
    duration_sec: 1, status: 'stored', analysis_status: 'done', verdict: null, violations: [] });
  render(<StatusBadge record={record} />);
  expect(screen.getByText('Наблюдения готовы')).toBeInTheDocument();
  expect(screen.queryByText('Без признаков нарушений')).not.toBeInTheDocument();
});

test('rejects observations returned for a different recording', async () => {
  request.mockResolvedValue({ ...complete, media_id: 'other-media' });
  render(<MLAnalysisPanel mediaId="media-1" onSeek={jest.fn()} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Сервер вернул анализ другой записи.');
  expect(screen.queryByText('Наблюдения готовы. Требуется ручная проверка.')).not.toBeInTheDocument();
});

test('shows factual captions and explicit gaps without fabricated detector confidence', async () => {
  request.mockResolvedValue({ ...complete, result: { ...complete.result, engine: 'dense_vlm',
    coverage_status: 'partial', coverage_windows: [
      { start_sec: 0, end_sec: 12, status: 'done' }, { start_sec: 12, end_sec: 24, status: 'not_processed' },
    ], events: [{ kind: 'object_handover', start_sec: 1, end_sec: 2, mean_detector_confidence: null,
      description: 'Человек передаёт предмет через стол.' }],
  } });
  const seek = jest.fn();
  render(<MLAnalysisPanel mediaId="media-1" onSeek={seek} />);
  const caption = await screen.findByRole('button', { name: /Человек передаёт предмет через стол/ });
  fireEvent.click(caption);
  expect(seek).toHaveBeenCalledWith(1, { start: 1, end: 2, label: 'Передача предмета' });
  expect(screen.getByText('Нет результата: 00:12–00:24.')).toBeInTheDocument();
  expect(screen.getByText('Запись обработана частично. Есть участки без результата.')).toBeInTheDocument();
  expect(screen.queryByText(/0 объектов/)).not.toBeInTheDocument();
});

test('does not accept a confidence-free event from the object detector', () => {
  expect(() => parseMLJob({ ...complete, result: { ...complete.result,
    events: [{ ...complete.result.events[0], mean_detector_confidence: null }],
  } })).toThrow();
});

const combined = () => ({ ...complete, result: { ...complete.result, engine: 'reviewed_pipeline',
  candidate_status: 'candidates_found', caption_status: 'done', source_seen_during_training: false,
  coverage_status: 'done', coverage_windows: [{ start_sec: 0, end_sec: 10, status: 'done' }],
  events: [{ kind: 'bank_event_candidate', start_sec: 1, end_sec: 3, timecode_sec: 2,
    mean_detector_confidence: null, score: .73, type: null, rule_id: null, requires_human_review: true,
    description: 'Модель выделила интервал для проверки.', evidence_indices: [0] }],
  observations: [{ kind: 'cabinet_door_opening', start_sec: 1, end_sec: 2, mean_detector_confidence: null,
    description: 'Человек открывает дверцу шкафа.', evidence_indices: [0] }],
} });

test('shows candidate episodes separately from Qwen descriptions and plays the whole interval', async () => {
  request.mockResolvedValue(combined());
  const seek = jest.fn();
  render(<MLAnalysisPanel mediaId="media-1" onSeek={seek} />);
  await screen.findByText('Эпизоды для проверки (1)');
  expect(screen.getByText('Описания видимых действий (1)')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Модель выделила интервал/ }));
  expect(seek).toHaveBeenCalledWith(1, { start: 1, end: 3, label: 'Эпизод для проверки' });
  expect(screen.queryByText(/73%/)).not.toBeInTheDocument();
  expect(screen.queryByText(/0 объектов/)).not.toBeInTheDocument();
});

test('preserves candidate results when captions fail and rejects invalid model references', async () => {
  const payload = combined();
  expect(() => parseMLJob({ ...payload, result: { ...payload.result,
    events: [{ ...payload.result.events[0], evidence_indices: [50] }],
  } })).toThrow();
  expect(() => parseMLJob({ ...payload, result: { ...payload.result,
    events: [{ ...payload.result.events[0], rule_id: 'fabricated_violation' }],
  } })).toThrow();
  request.mockResolvedValue({ ...payload, result: { ...payload.result, observations: [], caption_status: 'failed',
    coverage_status: 'partial', coverage_windows: [] } });
  render(<MLAnalysisPanel mediaId="media-1" onSeek={jest.fn()} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Результат поиска эпизодов сохранён');
  expect(screen.getByText('Эпизоды для проверки (1)')).toBeInTheDocument();
});

test('automatically polls an uploaded queued video through the caption stage', async () => {
  jest.useFakeTimers();
  const payload = combined();
  request.mockResolvedValueOnce({ ...payload, status: 'queued', result: null })
    .mockResolvedValueOnce({ ...payload, status: 'processing', stage: 'describing_actions', result: null })
    .mockResolvedValue(payload);
  render(<MLAnalysisPanel mediaId="media-1" onSeek={jest.fn()} />);
  await screen.findByText(/Видео в очереди. Анализ начнётся автоматически/);
  expect(screen.queryByRole('button', { name: 'Запустить анализ' })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByText(/Локальная модель описывает действия/)).toBeInTheDocument(), { timeout: 4000 });
  await waitFor(() => expect(screen.getByText('Эпизоды для проверки (1)')).toBeInTheDocument(), { timeout: 4000 });
  jest.useRealTimers();
});

const assessed = () => {
  const payload=combined();
  const frame=payload.result.evidence_frames[0];
  return {...payload,result:{...payload.result,verdict:'violation',rule_evaluation:'performed',assessment_coverage:'done',
    violations:[{type:'Уход до завершения обслуживания',start_sec:1,end_sec:3,timecode_sec:1,
      description:'Кассир уходит, клиент остаётся.',visible_fact:'Кассир уходит, клиент остаётся.',
      explanation:'Обслуживание ещё продолжается.',rule_id:'cashier_leaves_customer',requires_human_review:true,
      rule:{title:'Правила НБРК № 231',section:'22',url:'https://adilet.zan.kz/rus/docs/V1900019680',explanation:'До окончания обслуживания кассир остаётся на месте.',revision:'16.03.2026'},
      evidence:[{evidence_index:0,timestamp_sec:1,explanation:'Клиент ждёт у окна.'}],
      evidence_frames:[{...frame,explanation:'Клиент ждёт у окна.'}]}]}};
};

test('binary verdict groups each finding with its own evidence and normative link',async()=>{
  request.mockResolvedValue(assessed());
  const seek=jest.fn();render(<MLAnalysisPanel mediaId="media-1" onSeek={seek}/>);
  await screen.findByText('Обнаружены признаки возможных нарушений');
  expect(screen.getByText('Уход до завершения обслуживания')).toBeInTheDocument();
  expect(screen.getByRole('link',{name:/Правила НБРК № 231/})).toHaveAttribute('href','https://adilet.zan.kz/rus/docs/V1900019680');
  fireEvent.click(screen.getByRole('button',{name:/Клиент ждёт у окна/}));
  expect(screen.getByRole('dialog', { name: 'Кадр 00:01' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Открыть этот момент в видео' }));
  await waitFor(() => expect(seek).toHaveBeenCalledWith(1));
});

test('rejects a finding with unrelated evidence or inconsistent binary verdict',()=>{
  const payload=assessed();expect(parseMLJob(payload)?.result?.verdict).toBe('violation');
  expect(()=>parseMLJob({...payload,result:{...payload.result,verdict:'no_violation'}})).toThrow();
  const finding=payload.result.violations[0];
  expect(()=>parseMLJob({...payload,result:{...payload.result,violations:[{...finding,timecode_sec:2}]}})).toThrow();
  expect(()=>parseMLJob({...payload,result:{...payload.result,violations:[{...finding,
    evidence_frames:[{...finding.evidence_frames[0],timestamp_sec:55}]}]}})).toThrow();
});

test('shows a negative verdict with partial coverage explicitly',async()=>{
  const payload=assessed();request.mockResolvedValue({...payload,result:{...payload.result,
    verdict:'no_violation',violations:[],assessment_coverage:'partial'}});
  render(<MLAnalysisPanel mediaId="media-1" onSeek={jest.fn()}/>);
  await screen.findByText('Нарушение не обнаружено');
  expect(screen.getByRole('alert')).toHaveTextContent('Итог относится к проверенной части записи');
});

test('unclassified positive signal remains visible without an invented rule',async()=>{
  const payload=assessed();
  const finding={...payload.result.violations[0],classification_status:'unclassified',rule:null,rule_id:null};
  request.mockResolvedValue({...payload,result:{...payload.result,violations:[finding]}});
  render(<MLAnalysisPanel mediaId="media-1" onSeek={jest.fn()}/>);
  await screen.findByText('Обнаружены признаки возможных нарушений');
  expect(screen.getByRole('note')).toHaveTextContent('Тип и нормативное основание не установлены');
  expect(screen.queryByRole('link',{name:/Правила НБРК/})).not.toBeInTheDocument();
});
