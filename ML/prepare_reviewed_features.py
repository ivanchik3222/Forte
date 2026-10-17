"""Cache whole-scene context and augmented views, excluding reserved test sources."""
import argparse
import time

import numpy as np

from pipeline import ROOT, manifest
from prepare_external_features import cache_directory
from reviewed_model import VIEWS
from temporal_model import extract, load_encoder
from training_split import development_records
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--device', choices=['auto', 'mps', 'cpu', 'cuda'], default='auto')
    args = parser.parse_args()
    records = development_records(manifest(args.data), required=True)
    configs = VIEWS + [dict(view, augmentation='mild_video_v1') for view in VIEWS]
    encoder, device = None, None
    for config in configs:
        folder = cache_directory(config); folder.mkdir(parents=True, exist_ok=True)
        for i, record in enumerate(records):
            target = folder / (record['sha256'] + '.npz')
            if target.exists():
                continue
            if encoder is None:
                encoder, device = load_encoder(args.device)
            began = time.monotonic()
            times, features, duration = extract(record['path'], encoder, device, config)
            np.savez_compressed(target, times=times, features=features, duration=duration)
            print(f'{config["camera_profile"]} aug={bool(config.get("augmentation"))} {i+1}/{len(records)} '
                  f'ids={record["video_ids"]} elapsed={time.monotonic()-began:.1f}s', flush=True)
    print('Development features ready; reserved test sources were not accessed for extraction.', flush=True)


if __name__ == '__main__':
    main()
