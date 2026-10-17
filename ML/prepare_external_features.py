"""Extract local R3D18 features from downloaded, deduplicated external videos."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from temporal_model import CONFIG, ROOT, extract, load_encoder

EXTERNAL_CONFIG = dict(CONFIG, camera_profile='full_frame', roi_xyxy=None, stride_sec=2.)


def cache_directory(config):
    key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    return ROOT / 'cache' / f'temporal_{key}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'external/shoplifting_kaggle/manifest.json')
    parser.add_argument('--device', choices=['auto', 'mps', 'cpu', 'cuda'], default='auto')
    args = parser.parse_args()
    records = json.loads(args.manifest.read_text())
    cache = cache_directory(EXTERNAL_CONFIG)
    cache.mkdir(parents=True, exist_ok=True)
    encoder, device = load_encoder(args.device)
    started = time.monotonic()
    for i, record in enumerate(records):
        dest = cache / (record['sha256'] + '.npz')
        if dest.exists():
            continue
        if hashlib.sha256(Path(record['path']).read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('External video changed since dataset audit')
        began = time.monotonic()
        times, features, duration = extract(record['path'], encoder, device, EXTERNAL_CONFIG)
        np.savez_compressed(dest, times=times, features=features, duration=duration)
        print(f'external {i+1}/{len(records)} {record["source_files"][0]} windows={len(times)} '
              f'elapsed={time.monotonic()-began:.1f}s', flush=True)
    (cache / 'provenance.json').write_text(json.dumps(dict(config=EXTERNAL_CONFIG,
        manifest=str(args.manifest.resolve()), videos=len(records), device=device,
        elapsed_sec=time.monotonic()-started), indent=2))
    print(f'External features ready: {cache}', flush=True)


if __name__ == '__main__':
    main()
