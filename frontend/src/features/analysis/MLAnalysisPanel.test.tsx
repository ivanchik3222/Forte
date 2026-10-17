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

test('loads persistent observations and seeks original video from evidence', async () => {
  request.mockResolvedValue(complete);
  const seek = jest.fn();
  render(<MLAnalysisPanel mediaId="media-1" onSeek={seek} />);
  await screen.findByText('Наблюдения готовы. Требуется ручная проверка.');
  fireEvent.click(screen.getByRole('button', { name: /00:01 · 0 объектов/ }));
  expect(seek).toHaveBeenCalledWith(1);
  expect(screen.queryByText('Без признаков нарушений')).not.toBeInTheDocument();
});

test('enqueues using authenticated media API and selected camera profile', async () => {
  let submitted = false;
  request.mockImplementation(async (path, options) => {
    if (options?.method === 'POST') { submitted = true; return { ...complete, status: 'queued', result: null }; }
    return submitted ? complete : null;
  });
  render(<MLAnalysisPanel mediaId="media-1" onSeek={jest.fn()} />);
  const button = await screen.findByRole('button', { name: 'Найти объекты и движения' });
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
