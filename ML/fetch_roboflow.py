"""Download the authorized public dataset only; never sends ForteBank data."""
import hashlib,json,os,ssl,time,urllib.request,urllib.error,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DEST=ROOT/'external/cash_counter_theft_v2'

def main():
    try:
        import certifi
        tls=ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        tls=ssl.create_default_context()
    key=os.environ.get('ROBOFLOW_API_KEY','')
    if not key:
        env=ROOT/'.env'
        if env.exists():
            for line in env.read_text(encoding='utf-8-sig').splitlines():
                if line.strip().startswith('ROBOFLOW_API_KEY='):key=line.split('=',1)[1].strip().strip('\"\'')
    if not key:raise SystemExit('Missing ROBOFLOW_API_KEY in ML/.env or environment.')
    DEST.mkdir(parents=True,exist_ok=True)
    url='https://api.roboflow.com/ayaan-falfl/cash-counter-theft/2/coco'
    archive=DEST/'dataset.zip'
    if not archive.exists():
        for attempt in range(30):
            request=urllib.request.Request(url,headers={'Authorization':'Bearer '+key})
            try:
                with urllib.request.urlopen(request,timeout=40,context=tls) as r:data=json.load(r)
            except urllib.error.HTTPError as e:raise SystemExit(f'Roboflow export HTTP {e.code}; credentials not logged.') from None
            if data.get('export',{}).get('link'):break
            if data.get('ready') is False:
                print('Preparing public export',attempt+1,flush=True);time.sleep(2)
            else:raise SystemExit('Export unavailable; response not printed to protect credentials.')
        else:raise SystemExit('Export preparation timed out.')
        link=data['export']['link']
        partial=archive.with_suffix('.download')
        try:
            with urllib.request.urlopen(link,timeout=60,context=tls) as r,partial.open('wb') as f:
                while chunk:=r.read(1024*1024):f.write(chunk)
        except Exception as e:raise SystemExit(f'Dataset transfer failed: {type(e).__name__}; signed link not logged.') from None
        with zipfile.ZipFile(partial) as z:
            bad=z.testzip()
            if bad:raise SystemExit('Dataset ZIP failed CRC validation.')
        partial.replace(archive)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            target=(DEST/member.filename).resolve()
            if not target.is_relative_to(DEST.resolve()) or ((member.external_attr>>16)&0o170000)==0o120000:
                raise SystemExit('Unsafe archive member rejected.')
        z.extractall(DEST)
    metadata=dict(source='https://universe.roboflow.com/ayaan-falfl/cash-counter-theft/dataset/2',author='Ayaan',
                  license='CC BY 4.0',license_url='https://creativecommons.org/licenses/by/4.0/',
                  downloaded_on='2026-10-17',format='COCO',archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    (DEST/'provenance.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print('Downloaded and CRC-checked:',DEST,flush=True)
    for p in DEST.rglob('_annotations.coco.json'):
        d=json.loads(p.read_text());print(p.parent.name,'images',len(d['images']),'boxes',len(d['annotations']),
                                       'classes',[c['name'] for c in d['categories']],flush=True)

if __name__=='__main__':main()
