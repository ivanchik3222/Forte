"""Persistent, hash-based reservation for future bank-video testing."""
import json
from pathlib import Path

SPLIT_PATH = Path(__file__).resolve().parent / 'validation/bank_holdout_v1.json'


def read_split(path=SPLIT_PATH):
    if not Path(path).exists():
        return None
    split = json.loads(Path(path).read_text())
    if split.get('version') != 1 or not split.get('holdout_source_hashes'):
        raise ValueError('Invalid bank holdout reservation')
    if set(split['holdout_source_hashes']) & set(split['development_source_hashes']):
        raise ValueError('Holdout/development overlap')
    return split


def development_records(records, path=SPLIT_PATH, required=False):
    split = read_split(path)
    if split is None:
        if required:
            raise ValueError('Import reviewed annotations and reserve test videos first')
        return records
    known = set(split['development_source_hashes']) | set(split['holdout_source_hashes'])
    if not {r['sha256'] for r in records} <= known:
        raise ValueError('Dataset changed: reconcile the locked split before training')
    held = set(split['holdout_source_hashes'])
    return [r for r in records if r['sha256'] not in held]


def assert_training_sources(hashes, split):
    hashes = set(hashes)
    if hashes & set(split['holdout_source_hashes']):
        raise ValueError('Reserved test video attempted to enter training')
    if not hashes <= set(split['development_source_hashes']):
        raise ValueError('Unregistered source attempted to enter bank training')
