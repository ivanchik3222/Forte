"""Offline research inference with reviewed action suggestions, no automatic verdict."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from pipeline import ROOT, save_json
from reviewed_model import ACTION_KINDS, VIEWS, join_views, load_model
from render_reviewed_report import render_report
from temporal_model import candidate_events, extract, load_encoder, nearest_indices


def load_bundle(path):
    bundle = json.loads(path.read_text())
    if bundle.get('version') != 1:
        raise ValueError('Unsupported reviewed model bundle')
    loaded = {}
    for key in ('candidate', 'actions'):
        entry = bundle[key]
        artifact = (path.parent / entry['file']).resolve()
        if artifact.parent != path.parent.resolve() or hashlib.sha256(artifact.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Unexpected model artifact path/checksum')
        loaded[key] = load_model(artifact)
        if loaded[key][1]['split'] != bundle['split']:
            raise ValueError('Models disagree on the reserved test split')
    if loaded['candidate'][1]['training_source_hashes'] != loaded['actions'][1]['training_source_hashes']:
        raise ValueError('Models trained on different bank sources')
    if loaded['candidate'][1].get('model_role') == 'conditional_action_only':
        raise ValueError('An action-only head cannot score bank-event candidates')
    return bundle, loaded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'runs/mac_reviewed_v1/model_bundle.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs/reviewed_prediction.json')
    parser.add_argument('--device', choices=['auto', 'mps', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--allow-reserved-test', action='store_true', help='Explicitly open a reserved test video for evaluation')
    args = parser.parse_args(); started = time.monotonic()
    bundle, loaded = load_bundle(args.bundle)
    digest = hashlib.sha256(args.video.read_bytes()).hexdigest()
    reserved = digest in bundle['split']['holdout_source_hashes']
    if reserved and not args.allow_reserved_test:
        parser.error('This is a reserved test video. Pass --allow-reserved-test only when ready to evaluate it.')
    candidate, metadata = loaded['candidate']; action, action_metadata = loaded['actions']
    encoder, device = load_encoder(args.device)
    caches, durations = [], []
    for view in VIEWS:
        times, features, duration = extract(args.video, encoder, device, view)
        caches.append({digest:(times, features)}); durations.append(duration)
    times, features = join_views(*caches)[digest]
    scores = candidate.predict_proba(features)[:, 1]
    threshold = metadata['protocol']['threshold']
    events = candidate_events(times, scores, threshold)
    action_scores = action.action_scores(features)
    for event in events:
        index = int(nearest_indices(times, np.asarray([event['timecode_sec']]))[0])
        ranked = [int(i) for i in np.argsort(-action_scores[index]) if action.active[i]][:3]
        event['action_suggestions'] = [dict(kind=ACTION_KINDS[i], relative_score=float(action_scores[index, i]),
            training_source_videos=action_metadata['training_action_support'][ACTION_KINDS[i]],
            status='unconfirmed_suggestion') for i in ranked]
        # Deliberately preserve type=None and rule_id=None from candidate_events.
    report = dict(version=1, status='done', model='reviewed_dual_view_r3d18',
        source_sha256=digest, candidate_status='candidates_found' if events else 'no_candidates_found',
        events=events, max_score=float(scores.max()), threshold=threshold,
        scores=[dict(timestamp_sec=float(t), score=float(s)) for t,s in zip(times,scores)],
        source_seen_during_training=digest in metadata['training_source_hashes'],
        reserved_test=reserved, historical_test_contamination=bundle['split']['historical_contamination'] if reserved else None,
        automatic_violation_detection=False, requires_review=True, rule_evaluation='not_performed',
        action_score_interpretation='Relative ranking among known actions; not occurrence probability or evidence of a violation',
        candidate_variant=metadata['variant'], action_variant=action_metadata['variant'],
        duration_sec=min(durations), elapsed_sec=time.monotonic()-started, device=device,
        limitations=metadata['evaluation']['limitations'])
    save_json(args.output, report)
    render_report(report, args.video, args.output.with_suffix('.html'))
    if reserved:
        save_json(args.output.with_suffix('.test-use.json'), dict(source_sha256=digest,
            evaluated_at_unix=time.time(), bundle_sha256=hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
            output=str(args.output.resolve()), instruction='Do not tune the frozen bundle using this result and call it an independent test'))
    print(json.dumps({k:report[k] for k in ('candidate_status','source_seen_during_training','reserved_test','elapsed_sec')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
