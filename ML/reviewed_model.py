"""Human-supervised auxiliary action model, with separate bank-event scoring.

Action scores rank known observed actions CONDITIONALLY on an annotated/reviewed
window. They do not estimate occurrence, absence, legality, emotion or intention.
"""
import json
from collections import defaultdict

import numpy as np
import torch
from torch import nn

from prepare_local_review import KINDS
from temporal_model import CONFIG, WEIGHTS_SHA256, nearest_indices, training_samples
from training_split import assert_training_sources

CONTEXT_CONFIG = dict(CONFIG, camera_profile='full_frame', roi_xyxy=None)
VIEWS = [CONFIG, CONTEXT_CONFIG]
ACTION_KINDS = [k for k in KINDS if k not in ('other_visible_action', 'visibility_insufficient')]
PROTOCOL = dict(seed=42, hidden_features=64, epochs=120, learning_rate=.001,
    weight_decay=.01, dropout=.2, action_loss_weight=.25, min_action_source_videos=2,
    threshold=.5, point_tolerance_sec=.6, interval_tolerance_sec=.05,
    missing_annotation_policy='unknown; never background/negative',
    action_objective='conditional soft-target classification on human-annotated windows only',
    model_selection='development scene-CV balanced accuracy; localization as tie-break; test never read')


def normalize(features):
    features = np.asarray(features, dtype=np.float32)
    if features.ndim != 2 or features.shape[1] != 1024 or not np.isfinite(features).all():
        raise ValueError('Expected finite desk/context features of dimension 1024')
    # Each camera view has equal weight, independent of activation magnitude.
    parts = np.split(features, 2, axis=1)
    return np.concatenate([p * (np.float32(np.sqrt(512.)) /
        np.maximum(np.linalg.norm(p, axis=1, keepdims=True), np.float32(1e-8))) for p in parts], axis=1)


def join_views(desk, context):
    if set(desk) != set(context):
        raise ValueError('Desk/context cache sources differ')
    result = {}
    for sha, (times, features) in desk.items():
        ct, cf = context[sha]
        if len(times) != len(ct) or not np.allclose(times, ct, atol=1e-6):
            raise ValueError('Camera view timestamps differ')
        result[sha] = (times, np.concatenate([features, cf], axis=1))
    return result


def merged_observations(observations, source_hashes):
    grouped = defaultdict(list)
    for row in observations:
        if row['source_sha256'] in source_hashes and row['kind'] in ACTION_KINDS:
            grouped[(row['source_sha256'], row['kind'])].append(row)
    result = []
    for (sha, kind), rows in sorted(grouped.items()):
        intervals = []
        for row in sorted(rows, key=lambda r:(r['start_sec'], r['end_sec'])):
            if intervals and row['start_sec'] <= intervals[-1]['end_sec'] + 1e-6:
                intervals[-1]['end_sec'] = max(intervals[-1]['end_sec'], row['end_sec'])
                intervals[-1]['annotation_ids'].append(row['annotation_id'])
            else:
                intervals.append(dict(source_sha256=sha, kind=kind, start_sec=row['start_sec'],
                    end_sec=row['end_sec'], annotation_ids=[row['annotation_id']]))
        result.extend(intervals)
    return result


def action_samples(records, cache, observations):
    """Multi-action target distributions only where at least one human action exists.

No unlabeled time, generic observation, or visibility flag becomes background.
Overlapping actions share target mass; touching same-action intervals are merged.
"""
    allowed = {r['sha256'] for r in records}
    rows = merged_observations(observations, allowed)
    by_source = defaultdict(list)
    for row in rows:
        by_source[row['source_sha256']].append(row)
    xs, targets, weights, sources, centers = [], [], [], [], []
    support = {kind:sorted({r['source_sha256'] for r in rows if r['kind'] == kind}) for kind in ACTION_KINDS}
    for record in records:
        sha = record['sha256']
        if sha not in by_source:
            continue  # A missing/empty review does not access the cache or create labels.
        times, features = cache[sha]
        y = np.zeros((len(times), len(ACTION_KINDS)), dtype=np.float32)
        for row in by_source[sha]:
            start, end = row['start_sec'], row['end_sec']
            if start == end:
                index = int(nearest_indices(times, np.asarray([start]))[0])
                indices = [index] if abs(times[index] - start) <= PROTOCOL['point_tolerance_sec'] else []
            else:
                indices = np.flatnonzero((times >= start-PROTOCOL['interval_tolerance_sec']) &
                                         (times <= end+PROTOCOL['interval_tolerance_sec']))
                if not len(indices):
                    center = (start + end) / 2
                    index = int(nearest_indices(times, np.asarray([center]))[0])
                    indices = [index] if abs(times[index]-center) <= PROTOCOL['point_tolerance_sec'] else []
            y[indices, ACTION_KINDS.index(row['kind'])] = 1.
        keep = y.sum(axis=1) > 0
        if not keep.any():
            continue
        labels = y[keep]
        labels /= labels.sum(axis=1, keepdims=True)
        xs.append(features[keep]); targets.append(labels)
        weights.extend([1. / int(keep.sum())] * int(keep.sum()))
        sources.extend([sha] * int(keep.sum())); centers.extend(times[keep])
    if not xs:
        return (np.empty((0, 1024), np.float32), np.empty((0, len(ACTION_KINDS)), np.float32),
                np.empty(0), np.asarray([], dtype=str), np.empty(0), support)
    return np.concatenate(xs), np.concatenate(targets), np.asarray(weights), np.asarray(sources), np.asarray(centers), support


class ReviewedAdapter(nn.Module):
    def __init__(self):
        super().__init__()
        self.projection = nn.Linear(1024, PROTOCOL['hidden_features'])
        self.dropout = nn.Dropout(PROTOCOL['dropout'])
        self.event = nn.Linear(PROTOCOL['hidden_features'], 1)
        self.actions = nn.Linear(PROTOCOL['hidden_features'], len(ACTION_KINDS))
        self.active = np.zeros(len(ACTION_KINDS), dtype=bool)

    def forward(self, x):
        hidden = self.dropout(torch.relu(self.projection(x)))
        return self.event(hidden).squeeze(-1), self.actions(hidden)

    def predict_proba(self, features):
        self.eval()
        with torch.inference_mode():
            logits, _ = self(torch.from_numpy(normalize(features)))
            scores = torch.sigmoid(logits).numpy()
        return np.column_stack([1. - scores, scores])

    def action_scores(self, features):
        self.eval()
        with torch.inference_mode():
            _, logits = self(torch.from_numpy(normalize(features)))
            logits[:, ~self.active] = -1e9
            return torch.softmax(logits, dim=1).numpy() if self.active.any() else np.zeros_like(logits.numpy())


def fit_reviewed(records, cache, observations, split, *, auxiliary=True, augmented_cache=None):
    assert_training_sources([r['sha256'] for r in records], split)
    torch.manual_seed(PROTOCOL['seed'])
    model = ReviewedAdapter()
    x, y, weights = training_samples(records, cache, CONFIG['point_radius_sec'])
    ax, ay, aw, _, _, support = action_samples(records, cache, observations)
    model.active = np.asarray([len(support[k]) >= PROTOCOL['min_action_source_videos'] for k in ACTION_KINDS]) if auxiliary else model.active
    if augmented_cache is not None:
        xx, yy, ww = training_samples(records, augmented_cache, CONFIG['point_radius_sec'])
        x, y, weights = np.concatenate([x, xx]), np.r_[y, yy], np.r_[weights*.5, ww*.5]
        if auxiliary:
            aax, aay, aaw, _, _, _ = action_samples(records, augmented_cache, observations)
            ax, ay, aw = np.concatenate([ax, aax]), np.concatenate([ay, aay]), np.r_[aw*.5, aaw*.5]
    x = torch.from_numpy(normalize(x)); y = torch.tensor(y, dtype=torch.float32)
    weights = torch.tensor(weights / weights.sum(), dtype=torch.float32)
    use_actions = auxiliary and model.active.sum() >= 2 and len(ax) > 0
    if not use_actions:
        model.active[:] = False  # Never expose an untrained/random action head.
    if use_actions:
        ay[:, ~model.active] = 0
        keep = ay.sum(axis=1) > 0
        ax, ay, aw = ax[keep], ay[keep], aw[keep]
        ay /= ay.sum(axis=1, keepdims=True)
        # Gentle class balancing, using this TRAIN fold's source counts only.
        class_weight = np.asarray([1 / np.sqrt(max(1, len(support[k]))) for k in ACTION_KINDS])
        aw = aw * (ay @ class_weight)
        ax = torch.from_numpy(normalize(ax)); ay = torch.from_numpy(ay)
        aw = torch.tensor(aw / aw.sum(), dtype=torch.float32)
    optimizer = torch.optim.AdamW(model.parameters(), lr=PROTOCOL['learning_rate'], weight_decay=PROTOCOL['weight_decay'])
    model.train()
    for _ in range(PROTOCOL['epochs']):
        optimizer.zero_grad()
        logits, _ = model(x)
        loss = (nn.functional.binary_cross_entropy_with_logits(logits, y, reduction='none') * weights).sum()
        if use_actions:
            _, alogits = model(ax)
            alogits = alogits.masked_fill(torch.tensor(~model.active)[None, :], -1e9)
            action_loss = (-(ay * torch.log_softmax(alogits, dim=1)).sum(dim=1) * aw).sum()
            loss = loss + PROTOCOL['action_loss_weight'] * action_loss
        loss.backward(); optimizer.step()
    return model.eval(), support


def export_model(model, path, metadata):
    state = model.state_dict()
    arrays = {name.replace('.', '_'): value.detach().cpu().numpy() for name, value in state.items()}
    np.savez_compressed(path, **arrays, active=model.active, metadata=np.asarray(json.dumps(metadata, ensure_ascii=False)))


def load_model(path):
    with np.load(path, allow_pickle=False) as data:
        metadata = json.loads(str(data['metadata']))
        if metadata.get('format_version') != 1 or metadata.get('model_family') != 'reviewed_dual_view_r3d18' or metadata.get('backbone_sha256') != WEIGHTS_SHA256 or metadata.get('action_kinds') != ACTION_KINDS or metadata.get('view_configs') != VIEWS:
            raise ValueError('Unsupported reviewed model format/backbone/views/taxonomy')
        model = ReviewedAdapter()
        state = {}
        for name, template in model.state_dict().items():
            array = data[name.replace('.', '_')]
            if array.shape != tuple(template.shape) or not np.isfinite(array).all():
                raise ValueError('Invalid reviewed model parameters')
            state[name] = torch.tensor(array, dtype=template.dtype)
        active = data['active']
        if active.shape != (len(ACTION_KINDS),) or active.dtype != np.bool_:
            raise ValueError('Invalid active action mask')
        assert_training_sources(metadata['training_source_hashes'], metadata['split'])
        model.load_state_dict(state); model.active = active.copy()
    return model.eval(), metadata
