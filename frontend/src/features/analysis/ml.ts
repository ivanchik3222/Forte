import { mediaUrl } from '../../api/client';

export interface MLBox {
  label: string;
  class_id: number;
  confidence: number;
  xyxy: number[];
}
export interface MLResult {
  engine?: 'objects' | 'dense_vlm' | 'reviewed_temporal' | 'reviewed_pipeline';
  candidate_status?: 'candidates_found' | 'no_candidates_found' | 'unsupported_camera';
  caption_status?: 'done' | 'partial' | 'failed' | 'time_budget_exceeded';
  source_seen_during_training?: boolean;
  coverage_status?: 'done' | 'partial';
  coverage_windows?: { start_sec: number; end_sec: number; status: 'done' | 'not_processed' | 'invalid_model_output' }[];
  verdict: 'requires_review' | 'violation' | 'no_violation';
  violations: MLViolation[];
  rule_evaluation: 'not_performed' | 'performed';
  assessment_coverage?: 'done' | 'partial';
  assessment_version?: string;
  processed_frames: number;
  sampled_fps: number;
  elapsed_seconds: number;
  model_sha256: string;
  frames: { timestamp_sec: number; boxes: MLBox[] }[];
  events: MLEvent[];
  observations?: MLEvent[];
  evidence_frames: { timestamp_sec: number; image_url: string; boxes: MLBox[] }[];
}
export interface MLViolation {
  type: string; start_sec: number; end_sec: number; timecode_sec: number; description: string;
  visible_fact: string; explanation: string; rule_id: string | null; requires_human_review: true;
  classification_status?: 'grounded' | 'unclassified';
  rule: { title: string; section: string; url: string; explanation: string; revision: string } | null;
  evidence: { evidence_index: number; timestamp_sec: number; explanation: string }[];
  evidence_frames: { timestamp_sec: number; image_url: string; explanation: string; boxes: MLBox[] }[];
}
export interface MLEvent {
  kind: string; start_sec: number; end_sec: number; mean_detector_confidence: number | null;
  description?: string; timecode_sec?: number; score?: number; evidence_indices?: number[];
  type?: null; rule_id?: null; requires_human_review?: boolean;
}
export interface MLJob {
  job_id: string;
  media_id: string;
  status: 'queued' | 'processing' | 'done' | 'failed';
  stage?: 'finding_events' | 'describing_actions' | 'assessing_rules' | null;
  camera_profile: 'forte_open' | 'full_frame';
  error: string | null;
  result: MLResult | null;
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
    check(r.engine === undefined || ['objects', 'dense_vlm', 'reviewed_temporal', 'reviewed_pipeline'].includes(r.engine));
    const candidate = r.engine === 'reviewed_temporal' || r.engine === 'reviewed_pipeline';
    if (candidate) {
      check(['candidates_found', 'no_candidates_found', 'unsupported_camera'].includes(r.candidate_status || '') &&
        typeof r.source_seen_during_training === 'boolean');
    }
    if (r.engine === 'reviewed_pipeline') {
      check(['done', 'partial', 'failed', 'time_budget_exceeded'].includes(r.caption_status || '') && Array.isArray(r.observations));
    }
    if (r.engine === 'dense_vlm' || r.engine === 'reviewed_pipeline') {
      check(['done', 'partial'].includes(r.coverage_status || '') && Array.isArray(r.coverage_windows));
      r.coverage_windows?.forEach(w => check(object(w) && number(w.start_sec) && number(w.end_sec) &&
        w.end_sec >= w.start_sec && ['done', 'not_processed', 'invalid_model_output'].includes(w.status)));
    }
    check(Array.isArray(r.violations));
    if (r.rule_evaluation === 'performed') {
      check(['violation','no_violation'].includes(r.verdict) &&
        (r.verdict === 'violation') === (r.violations.length > 0) &&
        ['done','partial'].includes(r.assessment_coverage || ''));
    } else check(r.verdict === 'requires_review' && r.rule_evaluation === 'not_performed' && !r.violations.length);
    check(number(r.processed_frames) &&
      number(r.sampled_fps) && r.sampled_fps > 0 && number(r.elapsed_seconds) &&
      typeof r.model_sha256 === 'string' && /^[a-f0-9]{64}$/.test(r.model_sha256) &&
      Array.isArray(r.frames) && r.frames.length === r.processed_frames &&
      Array.isArray(r.events) && Array.isArray(r.evidence_frames));
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
    const validateEvent = (e: MLEvent, descriptive: boolean) => {
      check(object(e) && typeof e.kind === 'string' && number(e.start_sec) &&
      number(e.end_sec) && e.end_sec >= e.start_sec && (descriptive ? e.mean_detector_confidence === null && typeof e.description === 'string' &&
        e.description.trim().length > 0 && e.description.length <= 1200 :
        number(e.mean_detector_confidence) && e.mean_detector_confidence !== null && e.mean_detector_confidence <= 1));
      if (e.evidence_indices !== undefined) check(Array.isArray(e.evidence_indices) && e.evidence_indices.every(i =>
        Number.isInteger(i) && i >= 0 && i < r.evidence_frames.length));
    };
    r.events.forEach(e => {
      validateEvent(e, candidate || r.engine === 'dense_vlm');
      if (candidate) check(e.kind === 'bank_event_candidate' && number(e.score) && e.score! <= 1 &&
        number(e.timecode_sec) && e.timecode_sec! >= e.start_sec && e.timecode_sec! <= e.end_sec &&
        e.type === null && e.rule_id === null && e.requires_human_review === true);
    });
    if (candidate) check((r.candidate_status === 'candidates_found') === (r.events.length > 0));
    r.observations?.forEach(e => validateEvent(e, true));
    r.evidence_frames.forEach(e => {
      check(object(e) && number(e.timestamp_sec) && typeof e.image_url === 'string');
      mediaUrl(e.image_url);
      boxes(e.boxes);
    });
    r.violations.forEach(e => {
      check(object(e) && [e.type,e.description,e.visible_fact,e.explanation].every(s=>typeof s==='string' && s.trim().length>0) &&
        number(e.start_sec) && number(e.end_sec) && number(e.timecode_sec) &&
        e.start_sec <= e.timecode_sec && e.timecode_sec <= e.end_sec && e.requires_human_review === true);
      if (e.classification_status === 'unclassified') check(e.rule===null && e.rule_id===null && candidate);
      else {
        check(typeof e.rule_id==='string' && object(e.rule) && e.rule &&
          [e.rule.title,e.rule.section,e.rule.url,e.rule.explanation,e.rule.revision].every(s=>typeof s==='string' && s.length>0));
        const source = new URL(e.rule.url);
        check(source.protocol === 'https:' && ['adilet.zan.kz','law.gov.kz','zan.gov.kz','nationalbank.kz'].includes(source.hostname));
      }
      check(Array.isArray(e.evidence) && e.evidence.length >= 1 && e.evidence.length <= 3 &&
        Array.isArray(e.evidence_frames) && e.evidence_frames.length === e.evidence.length &&
        new Set(e.evidence.map(f=>f.evidence_index)).size === e.evidence.length);
      e.evidence.forEach((f,i) => {
        const frame=r.evidence_frames[f.evidence_index], own=e.evidence_frames[i];
        check(Number.isInteger(f.evidence_index) && frame && own && number(f.timestamp_sec) &&
          f.timestamp_sec >= e.start_sec && f.timestamp_sec <= e.end_sec && frame.timestamp_sec === f.timestamp_sec &&
          own.timestamp_sec === f.timestamp_sec && own.image_url === frame.image_url &&
          typeof f.explanation==='string' && f.explanation.trim().length>0 && own.explanation===f.explanation);
      });
      check(e.evidence.some(f=>f.timestamp_sec === e.timecode_sec));
    });
  } else check(r === null);
  return v;
}
export const observationName = (kind: string) => ({
  bank_event_candidate: 'Эпизод для проверки',
  cash_detected: 'Деньги видны в кадре', hand_near_cash: 'Рука рядом с деньгами',
  hand_near_cabinet: 'Рука рядом со шкафом', hand_motion_left: 'Движение руки влево',
  hand_motion_right: 'Движение руки вправо', hand_motion_up: 'Движение руки вверх',
  hand_motion_down: 'Движение руки вниз',
  cash_handling: 'Действия с наличными', cash_on_work_surface: 'Наличные на рабочей поверхности',
  object_handover: 'Передача предмета', object_moved_toward_clothing: 'Перемещение предмета к одежде',
  object_moved_into_bag: 'Перемещение предмета в сумку', cabinet_door_opening: 'Открывание дверцы',
  cabinet_door_closing: 'Закрывание дверцы', person_leaves_work_area: 'Уход из видимой рабочей зоны',
  document_presented: 'Предъявление документа', other_visible_action: 'Наблюдаемое действие',
  visibility_insufficient: 'Недостаточный обзор', object_opening: 'Открывание предмета',
  object_closing: 'Закрывание предмета', object_placed_inside: 'Предмет помещён внутрь',
  object_removed: 'Извлечение предмета', object_placed_on_surface: 'Предмет на поверхности',
  object_shown: 'Показ предмета', object_held: 'Удержание предмета', object_lifted_and_replaced: 'Подъём и возвращение предмета',
}[kind] || kind);
