"""Reusable, offline inference shared by the queue worker and batch verification."""
import hashlib
import json
import time
from pathlib import Path

import torch
from PIL import Image, ImageDraw

from predict_objects import frames, COLORS
from train_detector import local_yolo
from interaction_timeline import build_timeline

CLASSES = ['person', 'hand', 'cash', 'bag', 'storage_cabinet']


class Detector:
    def __init__(self, weights, device=None):
        self.weights = Path(weights).resolve()
        if not self.weights.is_file():
            raise FileNotFoundError('Local detector weights are missing; automatic downloads are disabled')
        torch.set_num_threads(4)
        self.device = device or ('0' if torch.cuda.is_available() else 'cpu')
        self.model = local_yolo()(str(self.weights))
        if [self.model.names[i] for i in range(5)] != CLASSES or len(self.model.names) != 5:
            raise ValueError('Unexpected detector classes')
        self.sha256 = hashlib.sha256(self.weights.read_bytes()).hexdigest()

    def analyze(self, source, output, camera_profile='forte_open', timeout=300):
        if camera_profile not in ('forte_open', 'full_frame'):
            raise ValueError('Unknown camera profile')
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        rows = []
        width = height = 0
        roi = None
        for timestamp, rgb in frames(Path(source), 2.):
            if time.perf_counter() - started > timeout:
                raise TimeoutError('Analysis time limit exceeded')
            h, w = rgb.shape[:2]
            if not rows:
                width, height = w, h
                if camera_profile == 'forte_open' and (w, h) != (464, 848):
                    raise ValueError('forte_open requires 464 x 848 video; select full_frame for another camera')
                roi = [0, 300, 464, 610] if camera_profile == 'forte_open' else [0, 0, w, h]
            if (w, h) != (width, height):
                raise ValueError('Frame dimensions changed within video')
            if rows and timestamp <= rows[-1]['timestamp_sec']:
                raise ValueError('Non-increasing video PTS')
            x1, y1, x2, y2 = roi
            prediction = self.model.predict(Image.fromarray(rgb[y1:y2, x1:x2]),
                imgsz=640, device=self.device, conf=.25, iou=.7, verbose=False)[0]
            boxes = []
            for box, score, cls in zip(prediction.boxes.xyxy.cpu(), prediction.boxes.conf.cpu(), prediction.boxes.cls.cpu()):
                left, top, right, bottom = box.tolist()
                class_id = int(cls)
                boxes.append(dict(class_id=class_id, label=CLASSES[class_id], confidence=round(float(score), 5),
                    xyxy=[round(left+x1, 2), round(top+y1, 2), round(right+x1, 2), round(bottom+y1, 2)]))
            rows.append(dict(timestamp_sec=round(timestamp, 6), boxes=boxes))
        if not rows:
            raise ValueError('Video contains no decodable frames')
        report = dict(model_sha256=self.sha256, weights=self.weights.name, device=self.device,
            width=width, height=height, camera_profile=camera_profile, roi_xyxy=roi,
            sampled_fps=2., confidence=.25, nms_iou=.7, processed_frames=len(rows),
            coordinate_system='original image pixels', timestamp_source='video PTS minus stream start', frames=rows)
        timeline = build_timeline(report, width, height)
        report['events'] = timeline['events']
        report['limitations'] = timeline['limitations']
        report['verdict'] = 'requires_review'
        report['violations'] = []
        report['rule_evaluation'] = 'not_performed'
        report['classification_complete'] = False
        report['additional_checks'] = {
            'identity_document_presentation': dict(status='not_evaluated',
                reason='No trained ID/passport/phone presentation model or verified transaction boundaries',
                required_evidence='Customer presents physical or digital document toward cashier; object type and roles must be verified'),
            'customer_hand_oscillation': dict(status='not_evaluated',
                reason='2 FPS boxes cannot establish rapid hand oscillations or ownership of hands',
                required_evidence='Original high-FPS hand trajectories, stable tracking and camera-motion compensation',
                affects_violation_verdict=False),
        }
        # Sample evidence throughout the recording, including observation starts.
        candidates = sorted({0, len(rows)-1} | {
            min(range(len(rows)), key=lambda i: abs(rows[i]['timestamp_sec']-e['start_sec']))
            for e in timeline['events']})
        if len(candidates) > 16:
            candidates = [candidates[round(i*(len(candidates)-1)/15)] for i in range(16)]
        wanted = {rows[i]['timestamp_sec']: rows[i] for i in candidates}
        evidence = []
        for timestamp, rgb in frames(Path(source), 2.):
            if time.perf_counter() - started > timeout:
                raise TimeoutError('Analysis time limit exceeded')
            row = wanted.pop(round(timestamp, 6), None)
            if row is None:
                continue
            picture = Image.fromarray(rgb)
            draw = ImageDraw.Draw(picture)
            draw.rectangle(roi, outline='white', width=1)
            for b in row['boxes']:
                color = COLORS[b['class_id']]
                draw.rectangle(b['xyxy'], outline=color, width=2)
                draw.text((b['xyxy'][0], max(0, b['xyxy'][1]-12)),
                    f"{b['label']} {b['confidence']:.2f}", fill=color)
            name = f'evidence-{len(evidence):03d}.jpg'
            picture.save(output/name, quality=90)
            evidence.append(dict(timestamp_sec=row['timestamp_sec'], image_file=name, boxes=row['boxes']))
            if not wanted:
                break
        if wanted:
            raise ValueError('Evidence frames could not be decoded a second time')
        report['evidence_frames'] = evidence
        report['elapsed_seconds'] = round(time.perf_counter()-started, 3)
        (output/'result.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        return report
