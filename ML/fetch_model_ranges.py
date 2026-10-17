"""Resume the pinned public 8B weight shard with verified parallel HTTP ranges.

Used when the hub/Xet transport repeatedly disconnects. Only a final SHA-verified
file is promoted. Partial downloads remain local and can be resumed.
"""
import argparse
import hashlib
import shutil
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

import requests
from download_review_model import MODEL_SPECS

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prefix',type=Path,required=True,help='Sequential HTTP prefix from the interrupted download')
    a=p.parse_args();spec=MODEL_SPECS['8b']
    name='model-00001-of-00002.safetensors';expected=spec['files'][name];total=5353972197
    folder=ROOT/'models/qwen3_vl_8b_mlx';parts=folder/'.range_parts';parts.mkdir(exist_ok=True)
    prefix=parts/'prefix'
    if not prefix.exists():shutil.copyfile(a.prefix,prefix)
    start=prefix.stat().st_size
    if not 0<start<total:raise ValueError('Unexpected HTTP prefix length')
    size=128*1024*1024
    ranges=[(i,s,min(total-1,s+size-1)) for i,s in enumerate(range(start,total,size))]
    url=f'https://huggingface.co/{spec["repository"]}/resolve/{spec["revision"]}/{name}'
    def fetch(item):
        index,left,right=item;path=parts/f'{index:04d}'
        if path.exists() and path.stat().st_size==right-left+1:return index
        for attempt in range(4):
            try:
                with requests.get(url,headers={'Range':f'bytes={left}-{right}','Accept-Encoding':'identity'},stream=True,timeout=(20,90)) as response:
                    response.raise_for_status()
                    if response.status_code!=206 or response.headers.get('Content-Range')!=f'bytes {left}-{right}/{total}':
                        raise ValueError('Wrong weight range returned')
                    temp=path.with_suffix('.tmp')
                    with temp.open('wb') as dest:
                        for chunk in response.iter_content(2*1024*1024):dest.write(chunk)
                if temp.stat().st_size!=right-left+1:raise ValueError('Incomplete weight range')
                temp.replace(path);return index
            except (requests.RequestException,ValueError):
                if attempt==3:raise RuntimeError(f'Could not download verified range {index}') from None
                time.sleep(2*(attempt+1))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(fetch,item) for item in ranges]
        for count,future in enumerate(as_completed(futures),1):
            future.result();print(f'Ranges completed {count}/{len(ranges)}',flush=True)
    dest=folder/(name+'.verified.tmp');digest=hashlib.sha256()
    with dest.open('wb') as output:
        for part in [prefix]+[parts/f'{i:04d}' for i,_,_ in ranges]:
            with part.open('rb') as file:
                while chunk:=file.read(8*1024*1024):output.write(chunk);digest.update(chunk)
    if dest.stat().st_size!=total or digest.hexdigest()!=expected:raise ValueError('Complete 8B shard checksum mismatch')
    dest.replace(folder/name)
    print('Pinned 8B shard SHA-256 verified',flush=True)


if __name__=='__main__':main()
