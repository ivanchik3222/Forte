"""Create a local review queue around bank points and out-of-fold hard negatives."""
import argparse
import json
from pathlib import Path

from PIL import Image

KINDS = ['cash_handling', 'cash_on_work_surface', 'object_handover',
         'object_moved_toward_clothing', 'object_moved_into_bag',
         'cabinet_door_opening', 'cabinet_door_closing', 'person_leaves_work_area',
         'document_presented', 'other_visible_action', 'visibility_insufficient']


def sample_images(source, requested, destination):
    import av
    index, sampled = 0, []
    with av.open(str(source)) as video:
        stream = video.streams.video[0]
        origin = float(stream.start_time * stream.time_base) if stream.start_time is not None else None
        for frame in video.decode(stream):
            if frame.time is None:
                raise ValueError('Missing video PTS')
            if origin is None:
                origin = float(frame.time)
            sec = float(frame.time) - origin
            while index < len(requested) and sec + 1e-6 >= requested[index]:
                image = frame.to_image().convert('RGB')
                image.thumbnail((700, 700), Image.Resampling.LANCZOS)
                path = destination / f'{index:02d}.jpg'
                image.save(path, quality=92)
                sampled.append(dict(timestamp_sec=sec, image=str(path.resolve())))
                index += 1
            if index == len(requested):
                break
    if not sampled:
        raise ValueError('Cannot decode review frames')
    return sampled


def main():
    from pipeline import ROOT, manifest, save_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, default=ROOT / 'runs/mac_temporal/oof_predictions.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'annotations/local_review')
    args = parser.parse_args()
    records = manifest(args.data)
    predictions = {p['source_sha256']: p for p in json.loads(args.predictions.read_text())}
    tasks = []
    for record in records:
        prediction = predictions[record['sha256']]
        end = prediction['times_sec'][-1]
        centers = list(record['timestamps_sec']) if record['label'] else [prediction['predicted_time_sec']]
        for center in centers:
            task_id = f'{record["sha256"][:12]}_{center:.2f}'
            folder = args.output / 'frames' / task_id
            folder.mkdir(parents=True, exist_ok=True)
            requested = sorted(set(max(0., min(end, center + offset)) for offset in [-4., -2., 0., 2., 4.]))
            images = sample_images(record['path'], requested, folder)
            tasks.append(dict(id=task_id, video_ids=record['video_ids'], source_sha256=record['sha256'],
                source_path=record['path'], source_label=record['label'],
                original_points_sec=record['timestamps_sec'], center_sec=center,
                reason='original_bank_point' if record['label'] else 'out_of_fold_negative_peak',
                frame_samples=images, review_status='pending', human_annotations=[],
                machine_annotations=None, legal_rule_id=None))
    save_json(args.output / 'queue.json', dict(version=1, allowed_kinds=KINDS, tasks=tasks,
        warning='Machine proposals are not confirmed labels. Original bank labels are preserved separately.'))
    print(f'Review queue: {len(tasks)} windows; {args.output / "queue.json"}')


if __name__ == '__main__':
    main()
