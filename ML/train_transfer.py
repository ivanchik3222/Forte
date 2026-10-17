"""External video-label MIL pretraining, then bank point-supervised head fine-tuning.

R3D18 stays frozen. A 512 -> 64 -> 1 adapter is trained locally on CPU; expensive
video features are cached from MPS. A matched random-init adapter measures transfer.
"""
import argparse
import copy
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold, train_test_split
from torch import nn

from pipeline import manifest, save_json
from training_split import development_records
from prepare_external_features import EXTERNAL_CONFIG, cache_directory
from temporal_model import CONFIG, ROOT, WEIGHTS_SHA256, scene_group, training_samples
from train_temporal import metrics, predict

PROTOCOL = dict(seed=42, hidden_features=64, dropout=.2, external_epochs=100, bank_epochs=60,
                external_lr=.002, bank_lr=.001, weight_decay=.01, mil_top_fraction=.2,
                hard_negative_fraction=1.,
                input_normalization='per-window L2 times sqrt(512); no fitted statistics')


def normalize(features):
    features = np.asarray(features, dtype=np.float32)
    return features * (np.float32(np.sqrt(512.)) / np.maximum(np.linalg.norm(features, axis=1, keepdims=True), np.float32(1e-8)))


class Adapter(nn.Module):
    def __init__(self):
        super().__init__()
        self.projection = nn.Linear(512, PROTOCOL['hidden_features'])
        self.dropout = nn.Dropout(PROTOCOL['dropout'])
        self.output = nn.Linear(PROTOCOL['hidden_features'], 1)

    def forward(self, x):
        return self.output(self.dropout(torch.relu(self.projection(x)))).squeeze(-1)

    def predict_proba(self, features):
        self.eval()
        with torch.inference_mode():
            scores = torch.sigmoid(self(torch.from_numpy(normalize(features)))).numpy()
        return np.column_stack([1. - scores, scores])


def new_adapter(state=None):
    torch.manual_seed(PROTOCOL['seed'])
    model = Adapter()
    if state is not None:
        model.load_state_dict(copy.deepcopy(state))
    return model


def load_cache(records, config):
    result = {}
    for record in records:
        path = cache_directory(config) / (record['sha256'] + '.npz')
        with np.load(path, allow_pickle=False) as data:
            times, features = data['times'], data['features']
        if features.shape != (len(times), 512) or not np.isfinite(features).all() or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
            raise ValueError('Invalid cached encoder features')
        result[record['sha256']] = (times, features)
    return result


def fit_external(records, cache):
    model = new_adapter()
    optimizer = torch.optim.AdamW(model.parameters(), lr=PROTOCOL['external_lr'], weight_decay=PROTOCOL['weight_decay'])
    tensors = [torch.from_numpy(normalize(cache[r['sha256']][1])) for r in records]
    sizes = [len(x) for x in tensors]
    x = torch.cat(tensors)
    y = torch.tensor([r['label'] for r in records], dtype=torch.float32)
    weight = torch.where(y == 1, .5 / (y == 1).sum(), .5 / (y == 0).sum())
    losses = []
    model.train()
    for epoch in range(PROTOCOL['external_epochs']):
        optimizer.zero_grad()
        # One video is one bag. Never assign a positive video label to every frame.
        bags = model(x).split(sizes)
        logits = torch.stack([bag.topk(max(1, math.ceil(len(bag) * PROTOCOL['mil_top_fraction']))).values.mean() for bag in bags])
        loss = (nn.functional.binary_cross_entropy_with_logits(logits, y, reduction='none') * weight).sum()
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach()))
    return model.eval(), losses


def evaluate_external(model, records, cache):
    scores = []
    with torch.inference_mode():
        for record in records:
            logits = model(torch.from_numpy(normalize(cache[record['sha256']][1])))
            pooled = logits.topk(max(1, math.ceil(len(logits) * PROTOCOL['mil_top_fraction']))).values.mean()
            scores.append(float(torch.sigmoid(pooled)))
    y = np.asarray([r['label'] for r in records])
    predicted = np.asarray(scores) >= .5
    p, r, f, _ = precision_recall_fscore_support(y, predicted, average='binary', zero_division=0)
    return dict(videos=len(y), precision=float(p), recall=float(r), f1=float(f),
                roc_auc=float(roc_auc_score(y, scores)),
                confusion_matrix_labels_0_1=confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
                predictions=[dict(source_sha256=record['sha256'], label=record['label'], score=score)
                             for record, score in zip(records, scores)],
                limitation='Deduplicated video split; actors/scenes are not independently held out')


def fit_bank(records, cache, state=None, augmented_cache=None):
    model = new_adapter(state)
    x, y, weights, groups = training_samples(records, cache, CONFIG['point_radius_sec'], return_groups=True)
    if augmented_cache is not None:
        # Only records in this fold's TRAIN list contribute augmented samples.
        ax, ay, aw, ag = training_samples(records, augmented_cache, CONFIG['point_radius_sec'], return_groups=True)
        x, y, weights = np.concatenate([x, ax]), np.concatenate([y, ay]), np.concatenate([weights*.5, aw*.5])
        groups = np.concatenate([groups, ag])
    x = torch.from_numpy(normalize(x))
    y = torch.tensor(y, dtype=torch.float32)
    weights = torch.tensor(weights / weights.sum(), dtype=torch.float32)
    group_indices = [torch.from_numpy(np.flatnonzero(groups == group)) for group in np.unique(groups)]
    optimizer = torch.optim.AdamW(model.parameters(), lr=PROTOCOL['bank_lr'], weight_decay=PROTOCOL['weight_decay'])
    model.train()
    for _ in range(PROTOCOL['bank_epochs']):
        optimizer.zero_grad()
        losses = nn.functional.binary_cross_entropy_with_logits(model(x), y, reduction='none')
        if PROTOCOL['hard_negative_fraction'] < 1.:
            terms = []
            for indices in group_indices:
                group_loss = losses[indices]
                # Every sampled window in a source-labeled normal TRAIN video is
                # negative. Focus on its highest-scored windows, never holdout data.
                if y[indices[0]] == 0:
                    count = max(1, math.ceil(len(indices) * PROTOCOL['hard_negative_fraction']))
                    group_loss = group_loss.topk(count).values
                terms.append(group_loss.mean() * weights[indices].sum())
            loss = torch.stack(terms).sum()
        else:
            loss = (losses * weights).sum()
        loss.backward()
        optimizer.step()
    return model.eval()


def export_adapter(model, path, metadata):
    state = model.state_dict()
    np.savez_compressed(path, projection_weight=state['projection.weight'].numpy(),
        projection_bias=state['projection.bias'].numpy(), output_weight=state['output.weight'][0].numpy(),
        output_bias=state['output.bias'].numpy(), metadata=np.asarray(json.dumps(metadata, ensure_ascii=False)))


def run(args):
    torch.set_num_threads(4)
    PROTOCOL['hard_negative_fraction'] = .2 if args.hard_negatives else 1.
    began = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=True)
    external = json.loads(args.external_manifest.read_text())
    bank = development_records(manifest(args.data))
    if set(r['sha256'] for r in bank) & set(r['sha256'] for r in external):
        raise ValueError('Bank video appears in the external source')
    save_json(args.output / 'protocol.json', dict(PROTOCOL, bank_config=CONFIG, external_config=EXTERNAL_CONFIG,
        selection='Fixed hyperparameters/epochs; compare matched initialization, no holdout threshold tuning'))
    ext_cache = load_cache(external, EXTERNAL_CONFIG)
    bank_cache = load_cache(bank, CONFIG)
    train, val = train_test_split(external, test_size=.2, random_state=42, stratify=[r['label'] for r in external])
    pilot, pilot_losses = fit_external(train, ext_cache)
    external_validation = evaluate_external(pilot, val, ext_cache)
    print('external validation', {k: external_validation[k] for k in ['videos', 'precision', 'recall', 'f1']}, flush=True)
    pretrained, losses = fit_external(external, ext_cache)
    state = copy.deepcopy(pretrained.state_dict())
    torch.save(state, args.output / 'external_adapter.pt')
    save_json(args.output / 'external_metrics.json', dict(validation=external_validation,
        train_source_hashes=[r['sha256'] for r in train], val_source_hashes=[r['sha256'] for r in val],
        pilot_losses=pilot_losses, final_losses=losses))
    result = {}
    labels = [r['label'] for r in bank]
    groups = [scene_group(r) for r in bank]
    variants = [('random_init_control', None, None), ('external_pretrained', state, None)]
    if args.with_augmentation:
        from prepare_bank_augmentation import AUGMENT_CONFIG
        augmented_cache = load_cache(bank, AUGMENT_CONFIG)
        variants.extend([('random_init_augmented', None, augmented_cache),
                         ('external_pretrained_augmented', state, augmented_cache)])
    for variant, initial, augmented in variants:
        oof, grouped = [], []
        for fold, (tr, va) in enumerate(StratifiedKFold(5, shuffle=True, random_state=42).split(bank, labels)):
            model = fit_bank([bank[i] for i in tr], bank_cache, initial, augmented)
            oof.extend(dict(predict(model, bank[i], bank_cache, CONFIG), fold=fold) for i in va)
        for tr, va in LeaveOneGroupOut().split(bank, labels, groups):
            model = fit_bank([bank[i] for i in tr], bank_cache, initial, augmented)
            grouped.extend(predict(model, bank[i], bank_cache, CONFIG) for i in va)
        tr = [r for r in bank if r['appearance_group'] == 'pink']
        va = [r for r in bank if r['appearance_group'] == 'white']
        model = fit_bank(tr, bank_cache, initial, augmented)
        cross = [predict(model, r, bank_cache, CONFIG) for r in va]
        result[variant] = dict(oof_same_scene=metrics(oof), leave_one_scene_group_out=metrics(grouped),
                               appearance_holdout_pink_to_white=metrics(cross))
        for name, predictions in [('oof', oof), ('scene', grouped), ('appearance', cross)]:
            save_json(args.output / f'{variant}_{name}.json', predictions)
        final = fit_bank(bank, bank_cache, initial, augmented)
        metadata = dict(format_version=2, head_type='mil_mlp64', backbone_sha256=WEIGHTS_SHA256,
            config=CONFIG, protocol=PROTOCOL, variant=variant, training_augmentation='mild_video_v1' if augmented is not None else None,
            training_source_hashes=[r['sha256'] for r in bank],
            external_source_hashes=[r['sha256'] for r in external] if initial is not None else [],
            automatic_violation_detection=False, requires_review=True,
            evaluation=dict(metrics=result[variant], limitations=[
                'Candidate score, not a calibrated probability or legal violation type',
                'R3D18 is frozen; only the 64-unit adapter is fine-tuned',
                'External videos have clip-level labels, no confirmed action intervals',
                'One bank camera; no independent new-camera evaluation',
                'Final artifact has seen all bank videos; use held-out predictions for quality',
                'Symmetric four-second context; not a causal early-warning model']))
        export_adapter(final, args.output / f'{variant}_head.npz', metadata)
        print(variant, json.dumps(result[variant]), flush=True)
    report = dict(protocol=PROTOCOL, bank_videos=len(bank), external_videos=len(external),
                  results=result, elapsed_sec=time.monotonic()-began,
                  backbone_frozen=True, automatic_production_replacement=False)
    save_json(args.output / 'metrics.json', report)
    print(f'Transfer comparison complete in {report["elapsed_sec"]:.1f}s', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--external-manifest', type=Path, default=ROOT / 'external/shoplifting_kaggle/manifest.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs/mac_transfer')
    parser.add_argument('--with-augmentation', action='store_true', help='Also compare two matched train-only augmentation variants')
    parser.add_argument('--hard-negatives', action='store_true', help='Train against the hardest 20%% of normal-video windows (exploratory comparison)')
    run(parser.parse_args())
