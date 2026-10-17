"""Audit the v1 data and sweep inference settings on VAL only, without retraining."""
import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

import torch

from evaluate_detector import fixed_counts
from train_detector import ROOT, local_yolo


def scores(counts):
    tp, fp, fn = (counts[k] for k in ('tp', 'fp', 'fn'))
    return dict(**counts, precision=tp / (tp + fp) if tp + fp else 0.,
                recall=tp / (tp + fn) if tp + fn else 0.,
                f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.)


def audit_data(records, classes, manual):
    audit = {}
    for split in ('train', 'val', 'test'):
        rows = [r for r in records if r['split'] == split]
        by_source = {}
        for source in sorted({r['source'] for r in rows}):
            group = [r for r in rows if r['source'] == source]
            by_source[source] = dict(images=len(group), boxes=dict(Counter(
                b['label'] for r in group for b in r['boxes'])))
        native = [r for r in rows if r['source'] == 'forte']
        sizes = {}
        for cls in classes:
            boxes = [b['xyxy'] for r in native for b in r['boxes'] if b['label'] == cls]
            if boxes:
                widths = [b[2] - b[0] for b in boxes]
                heights = [b[3] - b[1] for b in boxes]
                sizes[cls] = dict(boxes=len(boxes), median_width=statistics.median(widths),
                                  median_height=statistics.median(heights),
                                  min_height=min(heights), max_height=max(heights))
        clipped_cabinets = []
        for r in native:
            roi = r['roi_xyxy']
            for box in manual[r['name']].get('storage_cabinet', []):
                area = (box[2] - box[0]) * (box[3] - box[1])
                visible = max(0, min(box[2], roi[2]) - max(box[0], roi[0])) * max(
                    0, min(box[3], roi[3]) - max(box[1], roi[1]))
                if visible < area:
                    clipped_cabinets.append(dict(name=r['name'], annotated_xyxy=box,
                                                 retained_annotated_area=visible / area))
        audit[split] = dict(by_source=by_source, native_box_sizes=sizes,
                            images_with_masked_regions=sum(bool(r.get('ignore_regions_masked')) for r in rows),
                            cabinets_clipped_beyond_stored_annotation=clipped_cabinets)
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT / 'datasets/cash_objects_v1')
    parser.add_argument('--weights', type=Path, default=ROOT / 'models/cash_detector/best.pt')
    parser.add_argument('--out', type=Path, default=ROOT / 'runs/detector_diagnosis_v1')
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f'Choose a new --out: {args.out}')
    records = json.loads((args.data / 'manifest.json').read_text(encoding='utf-8'))
    manual = json.loads((ROOT / 'annotations/corrected/manual_boxes.json').read_text(encoding='utf-8'))
    # This deliberately cannot be switched to test: settings are chosen on val only.
    validation = [r for r in records if r['split'] == 'val']
    torch.set_num_threads(4)
    device = '0' if torch.cuda.is_available() else 'cpu'
    model = local_yolo()(str(args.weights))
    classes = [model.names[i] for i in sorted(model.names)]
    rows = []
    for imgsz in (640, 960):
        for nms_iou in (.3, .5, .7):
            predictions = []
            for r in validation:
                result = model.predict(str(args.data / 'images/val' / (r['name'] + '.jpg')),
                                       imgsz=imgsz, device=device, conf=.01, iou=nms_iou,
                                       max_det=300, rect=True, augment=False, verbose=False)[0]
                predictions.append([
                    dict(label=classes[int(c)], confidence=float(s), xyxy=b.tolist())
                    for b, s, c in zip(result.boxes.xyxy.cpu(), result.boxes.conf.cpu(), result.boxes.cls.cpu())])
            for confidence in (.05, .1, .15, .25, .35, .5):
                totals = {c: dict(tp=0, fp=0, fn=0) for c in classes}
                for r, pred in zip(validation, predictions):
                    counts = fixed_counts(r['boxes'], [p for p in pred if p['confidence'] >= confidence], classes)
                    for cls in classes:
                        for key in totals[cls]:
                            totals[cls][key] += counts[cls][key]
                per_class = {c: scores(v) for c, v in totals.items()}
                total = scores({k: sum(v[k] for v in totals.values()) for k in ('tp', 'fp', 'fn')})
                rows.append(dict(imgsz=imgsz, nms_iou=nms_iou, confidence=confidence,
                                 overall=total, per_class=per_class,
                                 macro_f1=statistics.mean(v['f1'] for v in per_class.values())))
            print(f'VAL sweep: imgsz={imgsz}, NMS IoU={nms_iou}', flush=True)
    baseline = next(r for r in rows if (r['imgsz'], r['nms_iou'], r['confidence']) == (640, .7, .25))
    saved = json.loads((ROOT / 'runs/cash_yolo11n_augmented_val/metrics.json').read_text(encoding='utf-8'))
    weight_hash = hashlib.sha256(args.weights.read_bytes()).hexdigest()
    baseline_reproduced = None
    if weight_hash == saved['weights_sha256']:
        baseline_reproduced = all(baseline['overall'][k] == saved['fixed_threshold'][k] for k in ('tp', 'fp', 'fn'))
        if not baseline_reproduced:
            raise AssertionError('The saved VAL fixed-threshold counts did not reproduce')
    curves = {}
    for run in ('cash_yolo11n_augmented', 'cash_yolo11n_control'):
        with (ROOT / 'runs' / run / 'results.csv').open(encoding='utf-8', newline='') as handle:
            curve = [{k.strip(): float(v) for k, v in r.items()} for r in csv.DictReader(handle)]
        curves[run] = dict(first=curve[0], last=curve[-1],
                           best_val=max(curve, key=lambda r: r['metrics/mAP50-95(B)']))
    summary = dict(weights_sha256=weight_hash, dataset_manifest_sha256=hashlib.sha256(
        (args.data / 'manifest.json').read_bytes()).hexdigest(),
        device=device, validation_images=len(validation), matching_iou=.5,
        baseline_reproduced=baseline_reproduced, data_audit=audit_data(records, classes, manual),
        training_curves=curves, baseline=baseline,
        best_micro_f1=max(rows, key=lambda r: r['overall']['f1']),
        best_macro_f1=max(rows, key=lambda r: r['macro_f1']), sweep=rows,
        limitations=['VAL tuning diagnostics, not an independent quality estimate',
                     'No new predictions on test; v1 test remains a historical audit',
                     'Fixed-threshold F1 here is not mAP',
                     'Only 10 validation images; thresholds may overfit',
                     'Retained cabinet area uses stored annotation, which can already be partial'])
    args.out.mkdir(parents=True)
    (args.out / 'diagnosis.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    with (args.out / 'val_sweep.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['imgsz', 'nms_iou', 'confidence',
                                                   'tp', 'fp', 'fn', 'precision', 'recall', 'f1', 'macro_f1'])
        writer.writeheader()
        for r in rows:
            writer.writerow({**{k: r[k] for k in ('imgsz', 'nms_iou', 'confidence', 'macro_f1')}, **r['overall']})
    print(json.dumps({k: summary[k] for k in ('baseline_reproduced', 'baseline', 'best_micro_f1', 'best_macro_f1')}, indent=2))


if __name__ == '__main__':
    main()
