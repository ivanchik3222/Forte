"""Cache augmented training views; evaluation always uses the original feature cache."""
import argparse
import time
from pathlib import Path

import numpy as np

from pipeline import manifest
from training_split import development_records
from prepare_external_features import cache_directory
from temporal_model import CONFIG, extract, load_encoder

AUGMENT_CONFIG = dict(CONFIG, augmentation='mild_video_v1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--device', choices=['auto', 'mps', 'cpu', 'cuda'], default='auto')
    args = parser.parse_args()
    records = development_records(manifest(args.data))
    cache = cache_directory(AUGMENT_CONFIG)
    cache.mkdir(parents=True, exist_ok=True)
    encoder, device = load_encoder(args.device)
    for i, record in enumerate(records):
        path = cache / (record['sha256'] + '.npz')
        if path.exists():
            continue
        began = time.monotonic()
        times, features, duration = extract(record['path'], encoder, device, AUGMENT_CONFIG)
        np.savez_compressed(path, times=times, features=features, duration=duration)
        print(f'augmented {i+1}/{len(records)} ids={record["video_ids"]} '
              f'elapsed={time.monotonic()-began:.1f}s', flush=True)


if __name__ == '__main__':
    main()
