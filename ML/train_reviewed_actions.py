"""Development-only follow-up: isolate action recognition from bank-event loss.

Fit a regularized, class-balanced linear softmax on human-annotated windows.
Export it exactly through the existing ReLU adapter (positive/negative pairs).
Unknown time ranges never enter the objective. Reserved test footage is not read.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler

from pipeline import ROOT, manifest, save_json
from reviewed_model import (ACTION_KINDS, PROTOCOL, VIEWS, ReviewedAdapter, action_samples,
                            export_model, join_views, normalize)
from temporal_model import WEIGHTS_SHA256, scene_group
from train_reviewed import LIMITATIONS, action_metrics, evaluate_actions
from train_transfer import load_cache
from training_split import assert_training_sources, development_records, read_split

ACTION_PROTOCOL = dict(seed=42, epochs=200, learning_rate=.01, l2_coefficient=.05,
    standard_deviation_floor=.01, class_balance='equal target mass over known train labels',
    objective='conditional classification on human windows; no event loss or background class',
    selection='development source-balanced top1 known-label hit rate; no reserved-test evaluation')


def fit_actions(records, cache, observations, split, augmented_cache=None):
    assert_training_sources([r['sha256'] for r in records], split)
    torch.manual_seed(ACTION_PROTOCOL['seed'])
    x, y, weights, _, _, support = action_samples(records, cache, observations)
    model = ReviewedAdapter()
    model.active = np.asarray([len(support[k]) >= PROTOCOL['min_action_source_videos'] for k in ACTION_KINDS])
    if augmented_cache is not None:
        ax, ay, aw, _, _, _ = action_samples(records, augmented_cache, observations)
        x, y, weights = np.concatenate([x,ax]), np.concatenate([y,ay]), np.r_[weights*.5,aw*.5]
    if model.active.sum() < 2:
        model.active[:] = False
        return model.eval(), support
    y[:, ~model.active] = 0
    keep = y.sum(axis=1) > 0
    x, y, weights = normalize(x[keep]), y[keep], weights[keep]
    y /= y.sum(axis=1, keepdims=True)
    weights /= weights.sum()
    scaler = StandardScaler().fit(x, sample_weight=weights)
    scale = np.maximum(scaler.scale_, ACTION_PROTOCOL['standard_deviation_floor']).astype(np.float32)
    mean = scaler.mean_.astype(np.float32)
    tx = torch.from_numpy((x-mean)/scale)
    # Equal mass per represented class; overlap remains a distribution over known labels.
    mass = (y * weights[:,None]).sum(axis=0)
    class_weights = np.where(model.active, 1. / np.maximum(mass, 1e-8), 0.)
    target = torch.tensor(y * class_weights, dtype=torch.float32)
    weight = torch.tensor(weights / model.active.sum(), dtype=torch.float32)
    classifier = torch.nn.Linear(1024, len(ACTION_KINDS))
    torch.nn.init.zeros_(classifier.weight); torch.nn.init.zeros_(classifier.bias)
    optimizer = torch.optim.Adam(classifier.parameters(), lr=ACTION_PROTOCOL['learning_rate'])
    for _ in range(ACTION_PROTOCOL['epochs']):
        optimizer.zero_grad()
        logits = classifier(tx).masked_fill(torch.tensor(~model.active)[None,:], -1e9)
        loss = (-(target * torch.log_softmax(logits, dim=1)).sum(dim=1) * weight).sum()
        loss = loss + ACTION_PROTOCOL['l2_coefficient'] * classifier.weight.square().sum()
        loss.backward(); optimizer.step()
    # Fold fitted scaling into the linear projection. ReLU(z)-ReLU(-z) == z.
    w = classifier.weight.detach().numpy() / scale[None,:]
    b = classifier.bias.detach().numpy() - w @ mean
    count = len(ACTION_KINDS)
    if 2*count > PROTOCOL['hidden_features']:
        raise ValueError('Action taxonomy exceeds exact export capacity')
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.projection.weight[:count] = torch.from_numpy(w)
        model.projection.weight[count:2*count] = torch.from_numpy(-w)
        model.projection.bias[:count] = torch.from_numpy(b)
        model.projection.bias[count:2*count] = torch.from_numpy(-b)
        model.actions.weight[:, :count] = torch.eye(count)
        model.actions.weight[:, count:2*count] = -torch.eye(count)
    model.eval()
    with torch.inference_mode():
        logits = classifier(tx).masked_fill(torch.tensor(~model.active)[None,:], -1e9)
        expected = torch.softmax(logits, dim=1).numpy()
    np.testing.assert_allclose(_scores_normalized(model, x), expected, rtol=1e-4, atol=1e-5)
    return model, support


def _scores_normalized(model, x):
    with torch.inference_mode():
        _, logits = model(torch.from_numpy(x))
        logits[:, ~model.active] = -1e9
        return torch.softmax(logits, dim=1).numpy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--annotations', type=Path, default=ROOT / 'annotations/reviewed/annotations.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs/mac_reviewed_v1')
    args = parser.parse_args(); torch.set_num_threads(4)
    bank = development_records(manifest(args.data), required=True); split = read_split()
    document = json.loads(args.annotations.read_text())
    observations = [r for r in document['observations'] if r['source_sha256'] in split['development_source_hashes']]
    if any(r['review_status'] != 'human_reviewed' for r in observations):
        raise ValueError('Unconfirmed action annotation')
    cache = join_views(*(load_cache(bank, v) for v in VIEWS))
    augmented = join_views(*(load_cache(bank, dict(v, augmentation='mild_video_v1')) for v in VIEWS))
    groups = [scene_group(r) for r in bank]
    report = json.loads((args.output / 'metrics.json').read_text())
    bundle = json.loads((args.output / 'model_bundle.json').read_text())
    if bundle['split'] != split:
        raise ValueError('Existing bundle has a different split')
    additional = {}
    for name, aug in [('actions_linear', None), ('actions_linear_augmented', augmented)]:
        rows = []
        for tr, va in LeaveOneGroupOut().split(bank, groups=groups):
            train, val = [bank[i] for i in tr], [bank[i] for i in va]
            model, support = fit_actions(train, cache, observations, split, aug)
            rows.extend(evaluate_actions(model, val, cache, observations, support, groups[va[0]]))
        evaluation = action_metrics(rows)
        save_json(args.output / f'{name}_action_predictions.json', rows)
        model, support = fit_actions(bank, cache, observations, split, aug)
        metadata = dict(format_version=1, model_family='reviewed_dual_view_r3d18', backbone_sha256=WEIGHTS_SHA256,
            view_configs=VIEWS, action_kinds=ACTION_KINDS, protocol=PROTOCOL, action_protocol=ACTION_PROTOCOL,
            variant=name, model_role='conditional_action_only', split=split,
            training_source_hashes=sorted(r['sha256'] for r in bank),
            annotation_export_sha256=document['export_sha256'],
            training_action_support={k:len(v) for k,v in support.items()},
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            automatic_violation_detection=False, requires_review=True,
            evaluation=dict(actions_development_scene_cv=evaluation, reserved_test='not_evaluated', limitations=LIMITATIONS))
        path = args.output / f'{name}.npz'; export_model(model, path, metadata)
        additional[name] = dict(metrics=evaluation, artifact=dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        print(name, json.dumps(evaluation), flush=True)
    report['action_only_followup'] = dict(protocol=ACTION_PROTOCOL, results=additional,
        reason='Exploratory development follow-up after weak auxiliary-action results; no new independent evaluation')
    current = report['selected_action_variant']
    current_metrics = additional[current]['metrics'] if current in additional else report['results'][current]['actions_development_scene_cv']
    candidates = {current:current_metrics['source_balanced_top1_hit_rate']}
    candidates.update({k:v['metrics']['source_balanced_top1_hit_rate'] for k,v in additional.items()})
    chosen = max(candidates, key=candidates.get)
    if chosen in additional:
        bundle['actions'] = additional[chosen]['artifact']
        report['selected_action_variant'] = chosen
    save_json(args.output / 'metrics.json', report)
    save_json(args.output / 'model_bundle.json', bundle)
    save_json(ROOT / 'validation/reviewed_training_summary.json', report)
    print(f'Action choice={chosen}; candidate model unchanged; reserved test untouched.', flush=True)


if __name__ == '__main__':
    main()
