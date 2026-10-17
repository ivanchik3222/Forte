"""Offline experimental temporal candidates. Does not replace the production detector."""
import argparse
import hashlib
import json
import time
from pathlib import Path

from temporal_model import ROOT, candidate_events, extract, load_encoder, load_head, score_head


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--head', type=Path, default=ROOT / 'runs/mac_temporal/temporal_head.npz')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs/temporal_prediction.json')
    parser.add_argument('--device', choices=['auto', 'mps', 'cuda', 'cpu'], default='auto')
    args = parser.parse_args()
    started = time.monotonic()
    head, metadata = load_head(args.head)
    config = metadata['config']
    encoder, device = load_encoder(args.device)
    times, features, duration = extract(args.video, encoder, device, config)
    scores = score_head(head, features)
    events = candidate_events(times, scores, config['threshold'])
    digest = hashlib.sha256(args.video.read_bytes()).hexdigest()
    report = dict(status='done', model='r3d18_point_supervised_research',
        candidate_status='candidates_found' if events else 'no_candidates_found',
        automatic_violation_detection=False, requires_review=True, rule_evaluation='not_performed',
        events=events, max_score=float(scores.max()), threshold=config['threshold'],
        source_seen_during_training=digest in metadata['training_source_hashes'],
        scores=[dict(timestamp_sec=float(t), score=float(s)) for t, s in zip(times, scores)],
        duration_sec=duration, device=device, elapsed_sec=time.monotonic()-started,
        limitations=metadata['evaluation']['limitations'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('candidate_status', 'max_score',
          'source_seen_during_training', 'device', 'elapsed_sec')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
