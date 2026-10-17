"""Explicit, pinned download for the optional local annotation assistant."""
import hashlib
import argparse
from pathlib import Path

REPOSITORY = 'mlx-community/Qwen3-VL-4B-Instruct-4bit'
REVISION = '2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b'
SHA256 = '90eeb02604181dbcccd0a30a1f550a4a8928ca7dcbee4aee1449239306cfdfca'
MODEL_SPECS = {
    '4b': dict(repository=REPOSITORY,revision=REVISION,files={'model.safetensors':SHA256}),
    '8b': dict(repository='mlx-community/Qwen3-VL-8B-Instruct-4bit',
        revision='defcdea7cc7a4b0858fea563cbbce171d328e457',files={
            'model-00001-of-00002.safetensors':'7c637158b2203e321d83596d3661f33b7b98a72beddfaaaa0eddc512acbdd1fb',
            'model-00002-of-00002.safetensors':'77190cd1dcf244522869bf923558340112b26d7db2ef3692f88407dd9b33c25d'}),
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size',choices=['4b','8b'],default='4b')
    args=parser.parse_args();spec=MODEL_SPECS[args.size]
    import os
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    from huggingface_hub import snapshot_download
    destination = Path(__file__).resolve().parent / f'models/qwen3_vl_{args.size}_mlx'
    snapshot_download(spec['repository'], revision=spec['revision'], local_dir=destination,
        allow_patterns=['*.json', '*.safetensors', '*.txt', '*.jinja', 'README.md'], max_workers=3)
    for filename,expected in spec['files'].items():
        digest = hashlib.sha256()
        with (destination / filename).open('rb') as source:
            while chunk := source.read(8 * 1024 * 1024):digest.update(chunk)
        if digest.hexdigest()!=expected:raise ValueError('Review-model weight checksum mismatch')
    print('Verified local review model:', destination)


if __name__ == '__main__':
    main()
