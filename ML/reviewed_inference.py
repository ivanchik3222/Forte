"""Offline serving of the frozen bank_only candidate head; no legal verdicts."""
import argparse
import hashlib
import json
import time
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def save_evidence(source, events, times, output, deadline):
    import av
    wanted = sorted({t for e in events for t in (e['start_sec'], e['timecode_sec'], e['end_sec'])})
    if not wanted:
        wanted = sorted({float(times[i]) for i in (0, len(times)//2, len(times)-1)})
    evidence, lookup, index = [], {}, 0
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        origin = float(stream.start_time * stream.time_base) if stream.start_time is not None else None
        for frame in container.decode(stream):
            if time.monotonic() > deadline:
                raise TimeoutError('Evidence extraction timed out')
            if frame.time is None:
                raise ValueError('Missing evidence PTS')
            if origin is None:
                origin = float(frame.time)
            sec = float(frame.time) - origin
            if sec + 1e-6 < wanted[index]:
                continue
            # Candidate times originate from the same decoder. Never substitute an unrelated frame.
            if abs(sec - wanted[index]) > 1e-5:
                raise ValueError('Candidate/evidence PTS mismatch')
            name = f'evidence-{index:04d}.jpg'
            frame.to_image().convert('RGB').save(output / name, quality=92)
            lookup[wanted[index]] = index
            evidence.append(dict(timestamp_sec=sec, image_file=name, boxes=[]))
            index += 1
            if index == len(wanted):
                break
    if index != len(wanted):
        raise ValueError('Incomplete evidence extraction')
    for event in events:
        event['evidence_indices'] = [lookup[t] for t in sorted({event['start_sec'], event['timecode_sec'], event['end_sec']})]
    return evidence


def analyze(source, output, bundle_path, backbone, device='auto', timeout=280, allow_reserved_test=False):
    import av
    import numpy as np
    from reviewed_model import VIEWS, load_model
    from temporal_model import extract, load_encoder, candidate_events

    started = time.monotonic(); deadline = started + timeout
    source, output, bundle_path = Path(source), Path(output), Path(bundle_path)
    output.mkdir(parents=True, exist_ok=True)
    bundle = json.loads(bundle_path.read_text())
    if bundle.get('version') != 1 or bundle.get('variant') != 'bank_only':
        raise ValueError('Unsupported deployed candidate model')
    artifact = (bundle_path.parent / bundle['candidate']['file']).resolve()
    if artifact.parent != bundle_path.parent.resolve() or sha256(artifact) != bundle['candidate']['sha256']:
        raise ValueError('Candidate weights checksum mismatch')
    model, metadata = load_model(artifact)
    if metadata['variant'] != 'bank_only' or metadata['protocol']['threshold'] != .5:
        raise ValueError('Unexpected candidate variant or threshold')
    digest = sha256(source)
    reserved = digest in metadata['split']['holdout_source_hashes']
    if reserved and not allow_reserved_test:
        raise ValueError('Reserved test video; use explicit research test workflow')
    if reserved:
        (output/'test-use.json').write_text(json.dumps(dict(source_sha256=digest,
            used_at_unix=time.time(), purpose='inference_only', weights_updated=False)))
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        dimensions = (stream.codec_context.width, stream.codec_context.height)
    if dimensions != (464, 848):
        return dict(engine='reviewed_temporal', candidate_status='unsupported_camera', events=[],
            frames=[], evidence_frames=[], processed_frames=0, sampled_fps=1.,
            elapsed_seconds=time.monotonic()-started, model_sha256=bundle['candidate']['sha256'],
            source_sha256=digest, source_seen_during_training=digest in metadata['training_source_hashes'], reserved_test=reserved,
            verdict='requires_review', violations=[], rule_evaluation='not_performed',
            limitations=['The frozen bank candidate model requires the original 464x848 camera view.'])
    encoder, device = load_encoder(device, backbone)
    views = [extract(source, encoder, device, config=view, timeout=max(.01, deadline-time.monotonic())) for view in VIEWS]
    times, desk, duration = views[0]
    if not np.array_equal(times, views[1][0]):
        raise ValueError('Camera views have different timestamps')
    scores = model.predict_proba(np.concatenate([desk, views[1][1]], axis=1))[:, 1]
    events = candidate_events(times, scores, .5)
    for event in events:
        event.update(kind='bank_event_candidate', mean_detector_confidence=None, requires_human_review=True,
            description='Модель выделила этот интервал для проверки по исходной записи.')
    evidence = save_evidence(source, events, times, output, deadline)
    return dict(engine='reviewed_temporal', verdict='requires_review', violations=[], rule_evaluation='not_performed',
        candidate_status='candidates_found' if events else 'no_candidates_found',
        events=events, observations=[], frames=[dict(timestamp_sec=float(t), boxes=[]) for t in times],
        evidence_frames=evidence, processed_frames=len(times), sampled_fps=1.,
        duration_sec=duration, elapsed_seconds=time.monotonic()-started,
        model_sha256=bundle['candidate']['sha256'], backbone_sha256=bundle['backbone_sha256'],
        source_sha256=digest, source_seen_during_training=digest in metadata['training_source_hashes'], reserved_test=reserved,
        threshold=.5, max_score=float(scores.max()),
        score_interpretation='Uncalibrated model score, not a probability of a violation',
        candidate_model=bundle['model_name'], candidate_evaluation=bundle['development_evaluation'],
        view_configs=VIEWS, device=device, limitations=metadata['evaluation']['limitations'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--backbone', type=Path, required=True)
    parser.add_argument('--device', default='auto')
    parser.add_argument('--timeout', type=float, default=280)
    parser.add_argument('--allow-reserved-test', action='store_true', help='Explicit inference only; records test usage, never trains')
    args = parser.parse_args()
    report = analyze(args.source, args.output, args.bundle, args.backbone, args.device, args.timeout, args.allow_reserved_test)
    (args.output/'result.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('candidate_status', 'processed_frames', 'elapsed_seconds')}))


if __name__ == '__main__':
    main()
