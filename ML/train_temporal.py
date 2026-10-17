"""Train/evaluate a frozen R3D18 + point-supervised head locally (including Apple MPS)."""
import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import sklearn
import torch
import torchvision
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold

from pipeline import manifest, save_json
from training_split import development_records
from temporal_model import (CONFIG, ROOT, WEIGHTS_SHA256, candidate_events, export_head, extract,
                            fit_head, load_encoder, scene_group)


def predict(head, record, cache, config):
    times, features = cache[record['sha256']]
    scores = head.predict_proba(features)[:, 1]
    peak = int(scores.argmax())
    return dict(video_ids=record['video_ids'], source_sha256=record['sha256'], label=record['label'],
                annotated_times_sec=record['timestamps_sec'], score=float(scores[peak]),
                predicted_time_sec=float(times[peak]), scene_group=scene_group(record),
                appearance_group=record['appearance_group'],
                events=candidate_events(times, scores, config['threshold']),
                times_sec=times.tolist(), scores=scores.tolist())


def metrics(predictions, threshold=.5):
    y = np.asarray([p['label'] for p in predictions])
    scores = np.asarray([p['score'] for p in predictions])
    predicted = scores >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(y, predicted, average='binary', zero_division=0)
    positives = [p for p in predictions if p['label']]
    errors = [min(abs(p['predicted_time_sec'] - t) for t in p['annotated_times_sec']) for p in positives]
    localized = sum(p['score'] >= threshold and e <= 2. for p, e in zip(positives, errors))
    return dict(n_videos=len(y), threshold=threshold, precision=float(precision), recall=float(recall),
                f1=float(f1), accuracy=float(np.mean(y == predicted)),
                confusion_matrix_labels_0_1=confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
                roc_auc=float(roc_auc_score(y, scores)) if len(set(y)) == 2 else None,
                average_precision=float(average_precision_score(y, scores)) if y.sum() else None,
                localization_mae_positive_videos_sec=float(np.mean(errors)) if errors else None,
                localization_within_2s=float(np.mean(np.asarray(errors) <= 2.)) if errors else None,
                positive_videos_detected_and_localized_within_2s=localized,
                n_positive_videos=len(positives))


def run(args):
    started = time.monotonic()
    records = development_records(manifest(args.data))
    if len(records) < 10:
        raise ValueError('At least ten unique videos required for this evaluation protocol')
    config = dict(CONFIG)
    config_key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    cache_dir = ROOT / 'cache' / f'temporal_{config_key}'
    cache_dir.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    save_json(args.output / 'protocol.json', dict(config=config, seed=42, config_hash=config_key,
        evaluation=['5-fold unique-video OOF', 'leave-one-scene-group-out', 'pink-to-white holdout'],
        selection='One fixed configuration; no threshold search on held-out predictions',
        source_hashes=[r['sha256'] for r in records]))
    cache, encoder, device, durations = {}, None, None, {}
    for i, record in enumerate(records):
        path = cache_dir / (record['sha256'] + '.npz')
        if not path.is_file():
            if encoder is None:
                encoder, device = load_encoder(args.device)
                print(f'encoder ready: {device}', flush=True)
            began = time.monotonic()
            times, features, duration = extract(record['path'], encoder, device, config, args.batch_size)
            np.savez_compressed(path, times=times, features=features, duration=duration)
            print(f'features {i+1}/{len(records)} ids={record["video_ids"]} '
                  f'windows={len(times)} elapsed={time.monotonic()-began:.1f}s', flush=True)
        with np.load(path, allow_pickle=False) as data:
            times, features = data['times'], data['features']
            durations[record['sha256']] = float(data['duration'])
        if any(t > durations[record['sha256']] + .1 for t in record['timestamps_sec']):
            raise ValueError(f'Annotation exceeds video duration: {record["video_ids"]}')
        if features.shape != (len(times), 512) or not np.isfinite(features).all() or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
            raise ValueError('Invalid cached temporal features')
        cache[record['sha256']] = (times, features)
    del encoder
    if device == 'mps':
        torch.mps.empty_cache()
    labels = [r['label'] for r in records]
    oof = []
    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    for fold, (tr, va) in enumerate(splitter.split(records, labels)):
        head = fit_head([records[i] for i in tr], cache, config)
        oof.extend([dict(predict(head, records[i], cache, config), fold=fold) for i in va])
        print(f'unique-video fold {fold+1}/5 complete', flush=True)
    grouped = []
    groups = [scene_group(r) for r in records]
    for tr, va in LeaveOneGroupOut().split(records, labels, groups):
        head = fit_head([records[i] for i in tr], cache, config)
        grouped.extend(predict(head, records[i], cache, config) for i in va)
        print(f'held-out scene {groups[va[0]]} complete', flush=True)
    tr = [r for r in records if r['appearance_group'] == 'pink']
    va = [r for r in records if r['appearance_group'] == 'white']
    head = fit_head(tr, cache, config)
    cross = [predict(head, r, cache, config) for r in va]
    report = dict(config=config, unique_videos=len(records), original_videos=sum(len(r['video_ids']) for r in records),
        positive_videos=sum(labels), negative_videos=len(labels)-sum(labels),
        duration_sec=sum(durations.values()), total_windows=sum(len(v[0]) for v in cache.values()),
        oof_same_scene=metrics(oof), leave_one_scene_group_out=metrics(grouped),
        appearance_holdout_pink_to_white=metrics(cross),
        scene_metrics={group: metrics([p for p in grouped if p['scene_group'] == group]) for group in sorted(set(groups))},
        elapsed_sec=time.monotonic()-started,
        environment=dict(python=platform.python_version(), platform=platform.platform(),
                         torch=torch.__version__, torchvision=torchvision.__version__, sklearn=sklearn.__version__,
                         device=device or args.device, backbone_sha256=WEIGHTS_SHA256),
        limitations=['Experimental binary candidates, no action types, legal conclusions or theft intent',
                     'One camera only; all historical data have been inspected during earlier development',
                     'Frozen video backbone; only linear classification head is trained on bank labels',
                     'Point annotations are incomplete; unmarked positive footage is not negative',
                     'Threshold 0.5 is fixed, uncalibrated; maximum scores bias long videos',
                     'Four-second symmetric context is offline, not real-time causal prediction',
                     '112px encoder input can miss small banknotes and documents',
                     'Final artifact fits all videos; quality is evaluated only with out-of-fold/holdout predictions'])
    save_json(args.output / 'metrics.json', report)
    for name, rows in [('oof_predictions', oof), ('scene_predictions', grouped), ('appearance_predictions', cross)]:
        save_json(args.output / (name + '.json'), rows)
    final = fit_head(records, cache, config)
    metadata = dict(format_version=1, config=config, backbone_sha256=WEIGHTS_SHA256,
                    training_source_hashes=[r['sha256'] for r in records],
                    automatic_violation_detection=False, requires_review=True,
                    evaluation=report, purpose='Research candidate ranking, not a production verdict')
    export_head(final, args.output / 'temporal_head.npz', metadata)
    print(json.dumps({k: report[k] for k in ('oof_same_scene', 'leave_one_scene_group_out',
          'appearance_holdout_pink_to_white', 'elapsed_sec')}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'runs/mac_temporal')
    parser.add_argument('--device', choices=['auto', 'mps', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--batch-size', type=int, default=2)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error('--batch-size must be positive')
    run(args)
