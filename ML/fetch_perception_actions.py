"""Download a bounded, action-balanced TRAIN subset of DeepMind Perception Test.

The 26.5 GB archive is accessed via checked HTTP byte ranges. Only selected video
members are transferred; video bytes are CRC-checked by zipfile. Never uses audio.
"""
import argparse
import hashlib
import io
import json
import random
import zipfile
from collections import Counter, OrderedDict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
BASE = 'https://storage.googleapis.com/dm-perception-test/zip_data/'
TARGETS = ['Opening something', 'Closing something', 'Putting something into something',
           'Taking something out of something', 'Putting something on top of something',
           'Showing something to the camera', 'Lifting something and placing it back down',
           'Holding something in a state']


class RemoteZipFile(io.RawIOBase):
    """Small bounded LRU cache; refuses servers that ignore the Range header."""
    def __init__(self, url, block_size=1024*1024):
        self.url, self.position, self.block_size = url, 0, block_size
        self.session = requests.Session()
        response = self.session.head(url, headers={'Accept-Encoding':'identity'}, timeout=45)
        response.raise_for_status()
        self.size = int(response.headers['Content-Length'])
        self.etag = response.headers.get('ETag')
        self.cache = OrderedDict(); self.transferred_bytes = 0

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.position

    def seek(self, offset, whence=0):
        self.position = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if self.position < 0:
            raise ValueError('Negative remote ZIP seek')
        return self.position

    def read(self, size=-1):
        size = max(0, self.size-self.position) if size < 0 else min(size, max(0,self.size-self.position))
        if size > 64*1024*1024:
            raise ValueError('Unexpected large remote ZIP read')
        result = bytearray()
        while size:
            block = self.position // self.block_size
            if block not in self.cache:
                start = block*self.block_size; end = min(self.size-1,start+self.block_size-1)
                headers = {'Range':f'bytes={start}-{end}', 'Accept-Encoding':'identity'}
                if self.etag: headers['If-Match'] = self.etag
                response = self.session.get(self.url, headers=headers, timeout=90)
                response.raise_for_status()
                if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{self.size}' or len(response.content) != end-start+1:
                    raise ValueError('Server did not honor the exact requested byte range')
                self.cache[block] = response.content
                self.transferred_bytes += len(response.content)
                while len(self.cache) > 4: self.cache.popitem(last=False)
            self.cache.move_to_end(block)
            offset = self.position % self.block_size
            chunk = self.cache[block][offset:offset+size]
            result.extend(chunk); self.position += len(chunk); size -= len(chunk)
        return bytes(result)

    def close(self):
        self.session.close(); super().close()


def download_annotations(folder):
    path = folder / 'action_localisation_train.json'
    if not path.exists():
        response = requests.get(BASE+'action_localisation_train_annotations.zip', timeout=90)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            path.write_bytes(archive.read('action_localisation_train.json'))
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--per-action', type=int, default=8)
    parser.add_argument('--output', type=Path, default=ROOT/'external/perception_test')
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    rows = download_annotations(args.output)
    rng = random.Random(42); ids = sorted(rows); rng.shuffle(ids)
    selected, coverage = [], Counter()
    for target in TARGETS:
        for vid in ids:
            if coverage[target] >= args.per_action: break
            labels = {a['label'] for a in rows[vid]['action_localisation']}
            if vid not in selected and target in labels:
                if rows[vid]['metadata']['split'] != 'train':
                    raise ValueError('Only upstream TRAIN videos may be imported')
                selected.append(vid); coverage.update(labels & set(TARGETS))
    folder = args.output/'videos';folder.mkdir(exist_ok=True)
    manifest = []; remote = RemoteZipFile(BASE+'train_videos.zip')
    with zipfile.ZipFile(remote) as archive:
        members = {Path(info.filename).stem:info for info in archive.infolist() if info.filename.endswith('.mp4')}
        expected = sum(members[vid].file_size for vid in selected)
        if expected > 2*1024**3:
            raise ValueError('Selected subset exceeds 2 GiB budget; lower --per-action')
        print(f'Selected {len(selected)} TRAIN videos; {expected/1024**2:.1f} MiB uncompressed media; {dict(coverage)}',flush=True)
        for i, vid in enumerate(selected):
            info = members[vid]; target=folder/(vid+'.mp4')
            if not target.exists():
                data = archive.read(info)  # zipfile checks CRC before returning data.
                temporary=target.with_suffix('.partial');temporary.write_bytes(data);temporary.replace(target)
            data=target.read_bytes()
            import zlib
            if len(data)!=info.file_size or zlib.crc32(data)&0xffffffff!=info.CRC:
                raise ValueError('Downloaded media CRC/length mismatch')
            record=rows[vid]
            duration=record['metadata']['num_frames']/record['metadata']['frame_rate']
            actions=[]
            for action in record['action_localisation']:
                start,end=[v/1e6 for v in action['timestamps']]
                if not 0<=start<=end<=duration+.1:
                    raise ValueError('External action timestamp outside source duration')
                actions.append(dict(label=action['label'],label_id=action['label_id'],start_sec=start,end_sec=end,
                    use_for_pretraining=action['label'] in TARGETS))
            manifest.append(dict(source='deepmind_perception_test',video_id=vid,source_split='train',
                sha256=hashlib.sha256(data).hexdigest(),path=str(target.resolve()),duration_sec=duration,
                actions=actions,metadata=record['metadata']))
            (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
            print(f'{i+1}/{len(selected)} {vid} CRC verified; total transferred {remote.transferred_bytes/1024**2:.1f} MiB',flush=True)
    provenance=dict(source_url='https://github.com/google-deepmind/perception_test',
        archive_url=BASE+'train_videos.zip',archive_size=remote.size,archive_etag=remote.etag,
        author='DeepMind Technologies Limited; Viorica Patraucean et al., Perception Test, NeurIPS 2023',
        license='CC BY 4.0 for materials; Apache 2.0 for upstream code',
        license_url='https://github.com/google-deepmind/perception_test#license-and-disclaimer',
        selection_seed=42,selection_targets=TARGETS,per_action=args.per_action,
        unique_videos=len({r['sha256'] for r in manifest}),audio_used=False,
        transfer_bytes=remote.transferred_bytes,
        limitations=['General object actions, not bank violations', 'No source label is renamed to theft or a bank-law violation',
                     'Source participants are not identified; bank holdout remains separate'])
    (args.output/'provenance.json').write_text(json.dumps(provenance,indent=2))
    remote.close()


if __name__=='__main__':main()
