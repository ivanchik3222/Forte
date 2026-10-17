"""Explicit download step. Never uploads dataset images or videos."""
import argparse
import hashlib
import json
import os
import ssl
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DINO_REVISION='a2bb814dd30d776dcf7e30523b00659f4f141c71'

def download_verified(url, path, expected):
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
        return
    # python.org builds on macOS may not have an installed system CA bundle.
    # Use a verified CA bundle, never disable TLS certificate verification.
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    temporary = path.with_suffix('.download')
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, context=context, timeout=60) as response, temporary.open('wb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError('Pretrained weight download hash mismatch')
    temporary.replace(path)

def main():
    p=argparse.ArgumentParser();p.add_argument('--resnet',action='store_true');p.add_argument('--grounding-dino',action='store_true')
    p.add_argument('--r3d',action='store_true',help='R3D18 Kinetics400 temporal encoder');args=p.parse_args()
    dest=ROOT/'models';dest.mkdir(parents=True,exist_ok=True)
    if args.resnet:
        path=dest/'resnet18-f37072fd.pth'
        download_verified('https://download.pytorch.org/models/resnet18-f37072fd.pth',path,
                          'f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec')
        print('ResNet18',path,'sha256',hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
    if args.r3d:
        path=dest/'r3d_18-b3b3357e.pth'
        download_verified('https://download.pytorch.org/models/r3d_18-b3b3357e.pth',path,
                          'b3b3357ead25631ec9c57362ff2128a92d0427e01e2cd184951a44380c3f2e9d')
        print('R3D18',path,'sha256',hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
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
