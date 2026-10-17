"""Download/audit the MNNIT dataset via its attributed Kaggle mirror (no uploads)."""
import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'external/shoplifting_kaggle'
SOURCE = 'https://data.mendeley.com/datasets/r3yjf35hzr/1'
MIRROR = 'https://www.kaggle.com/datasets/kipshidze/shoplifting-video-dataset'
DOWNLOAD = 'https://www.kaggle.com/api/v1/datasets/download/kipshidze/shoplifting-video-dataset?datasetVersionNumber=2'


def audit_archive(archive, destination):
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as data:
        members = data.infolist()
        if len(members) > 4096 or sum(m.file_size for m in members) > 10 * 1024**3:
            raise ValueError('Archive unexpectedly large')
        for member in members:
            target = (destination / member.filename).resolve()
            if (not target.is_relative_to(destination) or
                    ((member.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError('Unsafe archive member')
        bad = data.testzip()
        if bad:
            raise ValueError('Archive CRC failure')
        data.extractall(destination)
    records = {}
    for path in sorted(destination.rglob('*.mp4')):
        label_name = path.parent.name.lower()
        if label_name not in {'normal', 'shoplifting'}:
            raise ValueError(f'Unrecognized class directory: {label_name}')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        label = int(label_name == 'shoplifting')
        if digest in records and records[digest]['label'] != label:
            raise ValueError('Conflicting labels for identical videos')
        if digest not in records:
            records[digest] = dict(sha256=digest, path=str(path.resolve()), label=label,
                                   source_files=[], timestamps_sec=[], supervision='video_label_only')
        records[digest]['source_files'].append(str(path.relative_to(destination)))
    if not records:
        raise ValueError('No labeled MP4 videos found')
    return list(records.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Use an already completed download')
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    archive = args.archive or DEST / 'dataset.zip'
    if not archive.is_file():
        if args.archive:
            raise FileNotFoundError(archive)
        partial = archive.with_suffix('.zip.download')
        total = 0
        with requests.get(DOWNLOAD, stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            with partial.open('wb') as output:
                for chunk in response.iter_content(4 * 1024 * 1024):
                    output.write(chunk)
                    total += len(chunk)
                    print(f'downloaded {total // (1024*1024)} MiB', flush=True)
        if not zipfile.is_zipfile(partial):
            raise ValueError('Download did not return a complete ZIP archive')
        partial.replace(archive)
    records = audit_archive(archive, DEST / 'videos')
    provenance = dict(source=SOURCE, mirror=MIRROR, mirror_version=2,
        authors=['Mohd. Aquib Ansari', 'Dushyant Kumar Singh'], mirror_uploader='Nick Kipshidze',
        doi='10.17632/r3yjf35hzr.1', license='CC BY 4.0',
        license_url='https://creativecommons.org/licenses/by/4.0/',
        downloaded_utc=datetime.now(timezone.utc).isoformat(),
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        archive_bytes=archive.stat().st_size,
        unique_videos=len(records), original_videos=sum(len(r['source_files']) for r in records),
        class_counts={name: sum(r['label'] == label for r in records)
                      for label, name in [(0, 'normal'), (1, 'shoplifting')]},
        notes=['Innovatiana links to this same mirror; do not count it as a second dataset',
               'Video-level action labels only; not banking rules or temporal intervals'])
    for name, content in [('manifest.json', records), ('provenance.json', provenance)]:
        (DEST / name).write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(provenance, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
