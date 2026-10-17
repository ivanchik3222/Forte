"""Explicit download step. Never uploads dataset images or videos."""
import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DINO_REVISION='a2bb814dd30d776dcf7e30523b00659f4f141c71'

def main():
    p=argparse.ArgumentParser();p.add_argument('--resnet',action='store_true');p.add_argument('--grounding-dino',action='store_true');args=p.parse_args()
    dest=ROOT/'models';dest.mkdir(parents=True,exist_ok=True)
    if args.resnet:
        path=dest/'resnet18-f37072fd.pth'
        if not path.exists():
            temporary=path.with_suffix('.download')
            urllib.request.urlretrieve('https://download.pytorch.org/models/resnet18-f37072fd.pth',temporary)
            digest=hashlib.sha256(temporary.read_bytes()).hexdigest()
            if not digest.startswith('f37072fd'):raise ValueError('ResNet download hash mismatch')
            temporary.replace(path)
        print('ResNet18',path,'sha256',hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
    if args.grounding_dino:
        os.environ.setdefault('HF_HOME',str(ROOT/'cache/huggingface'))
        os.environ.setdefault('HF_HUB_DISABLE_XET','1')
        os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT','60')
        from huggingface_hub import snapshot_download
        path=snapshot_download('IDEA-Research/grounding-dino-tiny',revision=DINO_REVISION,local_dir=str(dest/'grounding-dino-tiny'),
                               allow_patterns=['*.json','*.txt','README.md','LICENSE*'])
        model_path=Path(path)/'model.safetensors'
        expected='1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3'
        if not model_path.exists() or hashlib.sha256(model_path.read_bytes()).hexdigest()!=expected:
            temporary=model_path.with_suffix('.download')
            url=f'https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/{DINO_REVISION}/model.safetensors'
            digest=hashlib.sha256();total=0
            with urllib.request.urlopen(url,timeout=60) as response,temporary.open('wb') as out:
                while chunk:=response.read(4*1024*1024):
                    out.write(chunk);digest.update(chunk);total+=len(chunk)
                    if total%(32*1024*1024)==0:print('Grounding DINO downloaded MiB',total//(1024*1024),flush=True)
            if total!=689359096 or digest.hexdigest()!=expected:
                raise ValueError(f'Truncated/corrupt Grounding DINO download: {total} bytes, sha256={digest.hexdigest()}')
            temporary.replace(model_path)
        print('Grounding DINO verified',model_path,flush=True)

if __name__=='__main__':main()
