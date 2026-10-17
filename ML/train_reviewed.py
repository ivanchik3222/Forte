"""Fresh training using partial human observations; locked test videos stay unopened.

Four matched runs isolate the effects of manual supervision and augmentation.
Whole-scene cross-validation is DEVELOPMENT only, never the two reserved videos.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.model_selection import LeaveOneGroupOut

from pipeline import ROOT, manifest, save_json
from reviewed_model import (ACTION_KINDS, PROTOCOL, VIEWS, action_samples, export_model,
                            fit_reviewed, join_views)
from temporal_model import CONFIG, WEIGHTS_SHA256, scene_group
from train_temporal import metrics, predict
from train_transfer import load_cache
from training_split import assert_training_sources, development_records, read_split

LIMITATIONS = [
    'Research candidates only; not a legal verdict or a calibrated violation probability',
    'Action scores are conditional ranks among annotated actions, not probabilities of their occurrence',
    'Partial annotations: unknown actions can be missing even inside annotated windows',
    'Generic actions and visibility flags are not negative/background examples',
    'Only 38 development videos from one camera; no independent new-camera validation',
    'Two reserved videos excluded from every new fit/validation; historical models previously used them',
    'Backbone frozen at Kinetics400 weights; only a 64-unit shared adapter and heads are trained',
    'Four-second symmetric context; not a causal early-warning or intent model',
    'Small cash/documents at 112px per view can be unrecognizable',
    'Some action classes have only two source videos; a missing suggestion does not prove absence',
    'Development metrics are used for selection and are not an independent final quality estimate']


def evaluate_actions(model, records, cache, observations, support, fold):
    x, target, _, sources, centers, _ = action_samples(records, cache, observations)
    if not len(x):
        return []
    scores = model.action_scores(x)
    train_counts = np.asarray([len(support[k]) for k in ACTION_KINDS])
    prior_top = int(np.argmax(np.where(model.active, train_counts, -1))) if model.active.any() else -1
    rows = []
    for label, score, source, center in zip(target, scores, sources, centers):
        ranked = [int(i) for i in np.argsort(-score, kind='stable') if model.active[i]]
        known = np.flatnonzero(label).tolist()
        rows.append(dict(source_sha256=str(source), time_sec=float(center), fold=fold,
            annotated_kinds=[ACTION_KINDS[i] for i in known],
            top_kinds=[ACTION_KINDS[i] for i in ranked[:3]],
            top1_matches_known=bool(ranked and ranked[0] in known),
            top3_matches_known=bool(set(ranked[:3]) & set(known)),
            has_supported_label=bool(model.active[known].any()),
            frequency_baseline_matches_known=prior_top in known))
    return rows


def action_metrics(rows):
    if not rows:
        return dict(annotated_windows=0, sources=0)
    sources = sorted({r['source_sha256'] for r in rows})
    per_source = [np.mean([r['top1_matches_known'] for r in rows if r['source_sha256'] == source]) for source in sources]
    per_source_baseline = [np.mean([r['frequency_baseline_matches_known'] for r in rows if r['source_sha256'] == source]) for source in sources]
    return dict(annotated_windows=len(rows), sources=len(sources),
        top1_known_label_hit_rate=float(np.mean([r['top1_matches_known'] for r in rows])),
        source_balanced_top1_hit_rate=float(np.mean(per_source)),
        source_balanced_frequency_baseline=float(np.mean(per_source_baseline)),
        top3_known_label_hit_rate=float(np.mean([r['top3_matches_known'] for r in rows])),
        windows_without_supported_train_label=sum(not r['has_supported_label'] for r in rows),
        per_known_kind={kind:dict(windows=len(kr), sources=len({r['source_sha256'] for r in kr}),
            top1_retrieval_rate=float(np.mean([bool(r['top_kinds']) and r['top_kinds'][0] == kind for r in kr])),
            top3_retrieval_rate=float(np.mean([kind in r['top_kinds'] for r in kr])))
            for kind in ACTION_KINDS if (kr := [r for r in rows if kind in r['annotated_kinds']])},
        interpretation='Conditional known-action retrieval on annotated windows only. Not full-video detection precision/recall.')


def balanced_accuracy(report):
    (tn, fp), (fn, tp) = report['confusion_matrix_labels_0_1']
    return .5 * (tn / (tn + fp) + tp / (tp + fn))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--annotations', type=Path, default=ROOT / 'annotations/reviewed/annotations.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs/mac_reviewed_v1')
    args = parser.parse_args()
    started = time.monotonic(); torch.set_num_threads(4)
    split = read_split()
    bank = development_records(manifest(args.data), required=True)
    assert_training_sources([r['sha256'] for r in bank], split)
    document = json.loads(args.annotations.read_text())
    observations = [r for r in document['observations'] if r['source_sha256'] in {v['sha256'] for v in bank}]
    if any(r['review_status'] != 'human_reviewed' for r in observations):
        raise ValueError('Machine proposals cannot enter human-supervised training')
    original = join_views(*(load_cache(bank, view) for view in VIEWS))
    augmented = join_views(*(load_cache(bank, dict(view, augmentation='mild_video_v1')) for view in VIEWS))
    args.output.mkdir(parents=True, exist_ok=True)
    # Written before fitting. Future reruns never silently reuse all-bank adapters.
    save_json(args.output / 'protocol.json', dict(PROTOCOL, view_configs=VIEWS, split=split,
        annotation_export_sha256=document['export_sha256'], initialization='fresh seeded heads; Kinetics400 frozen backbone',
        code_sha256={name:hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                     ('reviewed_model.py', 'train_reviewed.py', 'temporal_model.py', 'training_split.py')},
        external_adapters_reused=False, historical_bank_adapters_reused=False,
        action_variants_selection='source-balanced top1 known-label hit rate on development scene folds',
        limitations=LIMITATIONS))
    variants = [('bank_only', False, None), ('bank_only_augmented', False, augmented),
                ('human_auxiliary', True, None), ('human_auxiliary_augmented', True, augmented)]
    groups = [scene_group(r) for r in bank]
    labels = [r['label'] for r in bank]
    folds = list(LeaveOneGroupOut().split(bank, labels, groups))
    results, artifacts = {}, {}
    for name, auxiliary, aug in variants:
        predictions, action_rows = [], []
        for tr, va in folds:
            train = [bank[i] for i in tr]; val = [bank[i] for i in va]
            model, support = fit_reviewed(train, original, observations, split, auxiliary=auxiliary, augmented_cache=aug)
            predictions.extend(predict(model, record, original, CONFIG) for record in val)
            if auxiliary:
                action_rows.extend(evaluate_actions(model, val, original, observations, support, groups[va[0]]))
            print(f'{name}: excluded scene {groups[va[0]]}; train={len(train)}, val={len(val)}', flush=True)
        event_report = metrics(predictions)
        event_report['balanced_accuracy'] = balanced_accuracy(event_report)
        results[name] = dict(events_development_scene_cv=event_report, actions_development_scene_cv=action_metrics(action_rows))
        save_json(args.output / f'{name}_scene_predictions.json', predictions)
        save_json(args.output / f'{name}_action_predictions.json', action_rows)
        model, support = fit_reviewed(bank, original, observations, split, auxiliary=auxiliary, augmented_cache=aug)
        metadata = dict(format_version=1, model_family='reviewed_dual_view_r3d18', backbone_sha256=WEIGHTS_SHA256,
            view_configs=VIEWS, action_kinds=ACTION_KINDS, protocol=PROTOCOL, variant=name, split=split,
            training_source_hashes=sorted(r['sha256'] for r in bank),
            annotation_export_sha256=document['export_sha256'],
            training_action_support={k:len(v) for k,v in support.items()},
            training_augmentation='mild_video_v1' if aug is not None else None,
            auxiliary_action_supervision=auxiliary,
            automatic_violation_detection=False, requires_review=True,
            evaluation=dict(development=results[name], reserved_test='not_evaluated', limitations=LIMITATIONS))
        path = args.output / f'{name}.npz'
        export_model(model, path, metadata)
        artifacts[name] = dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        print(name, json.dumps(results[name], ensure_ascii=False), flush=True)
    candidate = max(results, key=lambda k:(results[k]['events_development_scene_cv']['balanced_accuracy'],
        results[k]['events_development_scene_cv']['positive_videos_detected_and_localized_within_2s']))
    action = max([k for k, auxiliary, _ in variants if auxiliary],
        key=lambda k:results[k]['actions_development_scene_cv'].get('source_balanced_top1_hit_rate', -1))
    report = dict(status='research_only_requires_review', development_videos=len(bank),
        positive_videos=sum(labels), negative_videos=len(labels)-sum(labels),
        confirmed_development_observations=len(observations),
        specific_action_observations=sum(r['kind'] in ACTION_KINDS for r in observations),
        generic_or_visibility_not_used_for_action_training=sum(r['kind'] not in ACTION_KINDS for r in observations),
        split=split, results=results, selected_candidate_variant=candidate, selected_action_variant=action,
        elapsed_sec=time.monotonic()-started, automatic_production_replacement=False,
        reserved_test_evaluated=False, limitations=LIMITATIONS)
    save_json(args.output / 'metrics.json', report)
    save_json(args.output / 'model_bundle.json', dict(version=1, candidate=artifacts[candidate], actions=artifacts[action],
        split=split, requires_review=True, automatic_violation_detection=False, reserved_test_evaluated=False))
    save_json(ROOT / 'validation/reviewed_training_summary.json', report)
    print(f'Finished in {report["elapsed_sec"]:.1f}s. Candidate={candidate}, actions={action}. Reserved test untouched.', flush=True)


if __name__ == '__main__':
    main()
