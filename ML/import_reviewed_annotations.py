"""Validate a human export locally, preserve it verbatim, and lock two test videos.

Descriptions are retained locally, never printed or sent to a model/API. Empty
reviewed tasks and missing tasks are NOT negative labels. Bank labels stay separate.
"""
import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from pipeline import ROOT, manifest, save_json
from prepare_local_review import KINDS
from temporal_model import scene_group
from training_split import SPLIT_PATH, read_split


def validate_export(document, queue, records):
    if document.get('version') != 1 or document.get('review_source') != 'explicit_user_review':
        raise ValueError('Expected an explicit human-review export v1')
    tasks = document.get('tasks')
    if not isinstance(tasks, list):
        raise ValueError('Missing tasks list')
    by_task = {t['id']: t for t in queue['tasks']}
    by_source = {r['sha256']: r for r in records}
    seen, observations, empty, warnings = set(), [], [], []
    for task in tasks:
        task_id = task.get('task_id')
        if task_id in seen or task_id not in by_task:
            raise ValueError('Duplicate or unknown review task')
        seen.add(task_id)
        if task.get('reviewed') is not True:
            raise ValueError('Unreviewed task in confirmed export')
        reference = by_task[task_id]
        for field in ('source_sha256', 'video_ids', 'source_label', 'original_points_sec'):
            if task.get(field) != reference[field]:
                raise ValueError(f'Review task changed original provenance: {field}')
        source = by_source.get(task['source_sha256'])
        if source is None or source['video_ids'] != task['video_ids'] or source['label'] != task['source_label'] or source['timestamps_sec'] != task['original_points_sec']:
            raise ValueError('Review source does not match current bank manifest')
        rows = task.get('observations')
        if not isinstance(rows, list):
            raise ValueError('Missing observations list')
        if not rows:
            empty.append(task_id)
        for number, row in enumerate(rows):
            if row.get('review_status') != 'human_reviewed' or row.get('kind') not in KINDS:
                raise ValueError('Unconfirmed or unknown action label')
            if row.get('legal_rule_id') is not None:
                raise ValueError('Visual observations cannot silently supply legal rules')
            start, end = row.get('start_sec'), row.get('end_sec')
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)):
                raise ValueError('Invalid annotation time')
            if not 0 <= start <= end <= source['duration_sec']:
                raise ValueError(f'Annotation outside video: ids={source["video_ids"]}, row={number}')
            if not isinstance(row.get('description'), str) or not row['description'].strip():
                raise ValueError('Missing human observation description')
            observation = dict(row, annotation_id=f'{task_id}:{number}', task_id=task_id,
                source_sha256=source['sha256'], video_ids=source['video_ids'])
            observations.append(observation)
            if row['kind'] in ('cabinet_door_opening', 'cabinet_door_closing') and end - start > 8:
                warnings.append(dict(annotation_id=observation['annotation_id'], video_ids=source['video_ids'],
                    code='long_door_transition_check_action_vs_state', start_sec=start, end_sec=end))
    return observations, dict(exported_tasks=len(tasks), reviewed_unique_videos=len({t['source_sha256'] for t in tasks}),
        observations=len(observations), empty_reviewed_tasks=empty,
        missing_tasks=sorted(set(by_task) - seen), structural_errors=0, semantic_review_warnings=warnings)


def make_split(records, holdout_ids=(16, 17)):
    held = [r for r in records if set(r['video_ids']) & set(holdout_ids)]
    if len(held) != 2 or {r['label'] for r in held} != {0, 1}:
        raise ValueError('Expected two unique test videos, one of each bank label')
    held_hashes = {r['sha256'] for r in held}
    held_groups = {scene_group(r) for r in held}
    development = [r for r in records if r['sha256'] not in held_hashes]
    if held_groups & {scene_group(r) for r in development}:
        raise ValueError('Reserve a complete scene group, not two members shared with training')
    return dict(version=1, name='bank_future_test_v1',
        holdout_source_hashes=sorted(held_hashes),
        development_source_hashes=sorted(r['sha256'] for r in development),
        holdout_videos=[dict(video_ids=r['video_ids'], source_sha256=r['sha256'],
            filename=Path(r['path']).name, bank_label=r['label']) for r in held],
        held_scene_groups=sorted(held_groups),
        selection='Complete green_bag scene group; one bank-positive and one bank-negative; no prediction-based selection',
        historical_contamination='Earlier experiments used all bank videos. This reservation applies to fresh subsequent training, not a previously unseen historical test.',
        evaluation_status='reserved_not_evaluated',
        policy='No train/validation/threshold selection/augmentation on these source hashes or their copies')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--queue', type=Path, default=ROOT / 'annotations/local_review/queue.json')
    parser.add_argument('--audit-manifest', type=Path, default=ROOT / 'audit/mac_manifest.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'annotations/reviewed')
    args = parser.parse_args()
    raw = args.export.read_bytes()
    export_sha = hashlib.sha256(raw).hexdigest()
    records = manifest(args.data)  # Re-hash current videos, including duplicate originals.
    audit = {r['sha256']: r for r in json.loads(args.audit_manifest.read_text())}
    for record in records:
        record['duration_sec'] = audit[record['sha256']]['duration_sec']
    observations, report = validate_export(json.loads(raw), json.loads(args.queue.read_text()), records)
    split = make_split(records)
    existing = read_split()
    if existing is not None and existing != split:
        raise ValueError('Refusing to change an existing test reservation')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / f'export_{export_sha}.json').write_bytes(raw)
    save_json(SPLIT_PATH, split)
    counts, sources = Counter(), defaultdict(set)
    for observation in observations:
        counts[observation['kind']] += 1
        sources[observation['kind']].add(observation['source_sha256'])
    report.update(export_sha256=export_sha, per_kind={k:dict(observations=counts[k], unique_videos=len(sources[k])) for k in sorted(counts)},
        reserved_video_ids=[r['video_ids'] for r in split['holdout_videos']],
        development_videos=len(split['development_source_hashes']),
        generic_observations_are_not_background=True, empty_reviews_are_not_negatives=True)
    save_json(args.output / 'annotations.json', dict(version=1, export_sha256=export_sha,
        observations=observations, audit=report, training_allowed_only_with_split=str(SPLIT_PATH)))
    save_json(ROOT / 'validation/reviewed_annotation_audit.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
