"""Resumable official Windows/Python 3.11 CUDA wheel download with SHA-256 check."""
import concurrent.futures
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'cache/wheels'
CHUNK=8*1024*1024


def fetch(package,filename):
    index=f'https://download.pytorch.org/whl/cu124/{package}/'
    with urllib.request.urlopen(index,timeout=40) as r:
        html=r.read().decode()
    href=next(h for h in re.findall(r'href="([^"]+)"',html)
              if urllib.parse.unquote(h.split('#')[0]).endswith('/'+filename))
    expected=urllib.parse.parse_qs(urllib.parse.urlsplit(href).fragment)['sha256'][0]
    # Use the official CloudFront host; the index can link to the other official CDN.
    url='https://download.pytorch.org/whl/cu124/'+urllib.parse.quote(filename,safe='')
    destination=CACHE/filename;CACHE.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        with destination.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()==expected:
                print('Already verified:',filename,flush=True)
                return
    request=urllib.request.Request(url+'?probe=range',headers={'Range':'bytes=0-0'})
    with urllib.request.urlopen(request,timeout=40) as r:
        if r.status!=206:raise ValueError('Server must support byte ranges')
        total=int(r.headers['Content-Range'].split('/')[-1]);r.read()
    parts=CACHE/(filename+'.parts_8m');parts.mkdir(exist_ok=True)
    count=(total+CHUNK-1)//CHUNK

    def download_part(i):
        start=i*CHUNK;end=min(total,start+CHUNK)-1;size=end-start+1
        part=parts/f'{i:04d}.part'
        if part.exists() and part.stat().st_size==size:return part
        for attempt in range(5):
            try:
                req=urllib.request.Request(url+f'?range={start}-{end}',headers={'Range':f'bytes={start}-{end}'})
                partial=part.with_suffix('.download')
                with urllib.request.urlopen(req,timeout=60) as r,partial.open('wb') as f:
                    if r.status!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{total}':
                        raise ValueError('Wrong range response')
                    while chunk:=r.read(64*1024):f.write(chunk)
                if partial.stat().st_size!=size:raise ValueError('Incomplete part')
                partial.replace(part)
                return part
            except Exception:
                if attempt==4:raise
                time.sleep(1+attempt)

    completed=0;began=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures=[pool.submit(download_part,i) for i in range(count)]
        for future in concurrent.futures.as_completed(futures):
            part=future.result();completed+=part.stat().st_size
            state=dict(filename=filename,completed_bytes=completed,total_bytes=total,
                       percent=round(100*completed/total,1),seconds=round(time.perf_counter()-began))
            (CACHE/(package+'_download_progress.json')).write_text(json.dumps(state),encoding='utf-8')
            print(filename, str(state['percent'])+'%',flush=True)
    temporary=destination.with_suffix('.assembling')
    with temporary.open('wb') as out:
        for i in range(count):
            with (parts/f'{i:04d}.part').open('rb') as f:
                while data:=f.read(8*1024*1024):out.write(data)
    with temporary.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=expected:raise ValueError('Wheel SHA-256 differs from official index')
    temporary.replace(destination)
    (CACHE/(package+'_wheel_source.json')).write_text(json.dumps(dict(url=url,sha256=actual,bytes=total),indent=2),encoding='utf-8')
    for i in range(count):
        part=parts/f'{i:04d}.part'
        if not part.resolve().is_relative_to(CACHE.resolve()):raise ValueError('Unsafe cache path')
        part.unlink()
    print('SHA-256 verified:',filename,flush=True)


if __name__=='__main__':
    fetch('torch','torch-2.6.0+cu124-cp311-cp311-win_amd64.whl')
    fetch('torchvision','torchvision-0.21.0+cu124-cp311-cp311-win_amd64.whl')
