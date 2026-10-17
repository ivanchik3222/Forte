import { mediaUrl } from '../../api/client';
import { parseJobResponse } from './api';
import { JobResponse } from './types';

export type FinalAnswer = Extract<JobResponse, { status: 'done' }>;
export interface AdditionalCheck { status: 'not_evaluated' | 'observed' | 'not_observed' | 'unobservable'; reason: string; }

export interface MLBox {
  label: string;
  class_id: number;
  confidence: number;
  xyxy: number[];
}
export interface MLResult {
  verdict: 'requires_review' | 'violation' | 'no_violation';
  violations: unknown[];
  rule_evaluation: 'not_performed' | 'performed';
  classification_complete?: boolean;
  additional_checks?: { identity_document_presentation: AdditionalCheck; customer_hand_oscillation: AdditionalCheck };
  processed_frames: number;
  sampled_fps: number;
  elapsed_seconds: number;
  model_sha256: string;
  frames: { timestamp_sec: number; boxes: MLBox[] }[];
  events: { kind: string; start_sec: number; end_sec: number; mean_detector_confidence: number }[];
  evidence_frames: { timestamp_sec: number; image_url: string; boxes: MLBox[] }[];
}
export interface MLJob {
  job_id: string;
  media_id: string;
  status: 'queued' | 'processing' | 'done' | 'failed';
  camera_profile: 'forte_open' | 'full_frame';
  error: string | null;
  result: MLResult | null;
  final_answer?: FinalAnswer | null;
}
const object = (v: any) => v && typeof v === 'object' && !Array.isArray(v);
const number = (v: any) => typeof v === 'number' && Number.isFinite(v) && v >= 0;
function check(value: unknown): asserts value {
  if (!value) throw new Error('Некорректный ответ локального анализатора.');
}
export function parseMLJob(value: unknown): MLJob | null {
  if (value === null) return null;
  const v = value as MLJob;
  check(object(v) && typeof v.job_id === 'string' && typeof v.media_id === 'string' &&
    ['queued', 'processing', 'done', 'failed'].includes(v.status) &&
    ['forte_open', 'full_frame'].includes(v.camera_profile) &&
    (v.error === null || typeof v.error === 'string'));
  const r = v.result;
  if (v.status === 'done') {
    check(object(r) && r);
    if (v.final_answer != null) {
      const final = parseJobResponse(v.final_answer);
      check(final.status === 'done' && final.job_id === v.job_id &&
        r.classification_complete === true && r.rule_evaluation === 'performed');
    } else check(r.verdict === 'requires_review' && r.rule_evaluation === 'not_performed' &&
      Array.isArray(r.violations) && !r.violations.length);
    check(Array.isArray(r.violations) && number(r.processed_frames) &&
      number(r.sampled_fps) && r.sampled_fps > 0 && number(r.elapsed_seconds) &&
      typeof r.model_sha256 === 'string' && /^[a-f0-9]{64}$/.test(r.model_sha256) &&
      Array.isArray(r.frames) && r.frames.length === r.processed_frames &&
      Array.isArray(r.events) && Array.isArray(r.evidence_frames));
    if (r.additional_checks != null) {
      check(object(r.additional_checks));
      [r.additional_checks.identity_document_presentation,r.additional_checks.customer_hand_oscillation].forEach(c =>
        check(object(c) && ['not_evaluated','observed','not_observed','unobservable'].includes(c.status) && typeof c.reason === 'string'));
    }
    const boxes = (items: MLBox[]) => {
      check(Array.isArray(items));
      items.forEach(b => check(object(b) && Number.isInteger(b.class_id) &&
        ['person', 'hand', 'cash', 'bag', 'storage_cabinet'][b.class_id] === b.label &&
        number(b.confidence) && b.confidence <= 1 && Array.isArray(b.xyxy) && b.xyxy.length === 4 &&
        b.xyxy.every(number) && b.xyxy[0] < b.xyxy[2] && b.xyxy[1] < b.xyxy[3]));
    };
    r.frames.forEach((f, i) => {
      check(object(f) && number(f.timestamp_sec) && (i === 0 || f.timestamp_sec > r.frames[i-1].timestamp_sec));
      boxes(f.boxes);
    });
    r.events.forEach(e => check(object(e) && typeof e.kind === 'string' && number(e.start_sec) &&
      number(e.end_sec) && e.end_sec >= e.start_sec && number(e.mean_detector_confidence) && e.mean_detector_confidence <= 1));
    r.evidence_frames.forEach(e => {
      check(object(e) && number(e.timestamp_sec) && typeof e.image_url === 'string');
      mediaUrl(e.image_url);
      boxes(e.boxes);
    });
  } else check(r === null);
  return v;
}
export const observationName = (kind: string) => ({
  cash_detected: 'Деньги видны в кадре', hand_near_cash: 'Рука рядом с деньгами',
  hand_near_cabinet: 'Рука рядом со шкафом', hand_motion_left: 'Движение руки влево',
  hand_motion_right: 'Движение руки вправо', hand_motion_up: 'Движение руки вверх',
  hand_motion_down: 'Движение руки вниз',
}[kind] || kind);
