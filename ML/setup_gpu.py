"""Install verified local CUDA wheels, check GPU kernels, optionally train locally."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'cache/wheels'
WHEELS=[('torch','torch-2.6.0+cu124-cp311-cp311-win_amd64.whl'),
        ('torchvision','torchvision-0.21.0+cu124-cp311-cp311-win_amd64.whl')]


def run(arguments):
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1')
    subprocess.run([sys.executable,*map(str,arguments)],cwd=ROOT.parent,env=env,
                   stderr=subprocess.STDOUT,check=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wait-for-download',action='store_true',help='Wait for an already running fetch_cuda_wheels.py')
    parser.add_argument('--train',action='store_true')
    parser.add_argument('--lr',type=float,default=.0005)
    parser.add_argument('--freeze',type=int,default=10)
    args=parser.parse_args()
    if args.wait_for_download:
        began=time.monotonic();last_status=0.
        while not all((CACHE/name).exists() and (CACHE/(package+'_wheel_source.json')).exists() for package,name in WHEELS):
            if time.monotonic()-began>3600:raise TimeoutError('CUDA download has not completed in one hour')
            if time.monotonic()-last_status>=60:
                state=CACHE/'torch_download_progress.json'
                print('Waiting for verified CUDA wheels:',state.read_text(encoding='utf-8') if state.exists() else 'starting',flush=True)
                last_status=time.monotonic()
            time.sleep(5)
    else:
        run([ROOT/'fetch_cuda_wheels.py'])
    paths=[]
    for package,name in WHEELS:
        path=CACHE/name;source=json.loads((CACHE/(package+'_wheel_source.json')).read_text(encoding='utf-8'))
        with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=source['sha256']:raise ValueError('Cached CUDA wheel hash mismatch')
        paths.append(path)
    print('Installing verified CUDA wheels into:',sys.prefix,flush=True)
    run(['-m','pip','install','--disable-pip-version-check','--no-deps','--ignore-installed','--no-cache-dir',*paths])
    # Fresh interpreter: never reuse an already imported CPU torch after installation.
    code="""import json,pathlib,torch,torchvision
assert torch.cuda.is_available(), 'CUDA is not available'
x=torch.randn(256,256,device='cuda'); y=x@x
assert torch.isfinite(y).all()
boxes=torch.tensor([[0.,0.,10.,10.],[1.,1.,9.,9.],[20.,20.,30.,30.]],device='cuda')
scores=torch.tensor([.9,.8,.7],device='cuda')
assert torchvision.ops.nms(boxes,scores,.5).cpu().tolist()==[0,2]
torch.cuda.synchronize()
report=dict(torch=torch.__version__,torchvision=torchvision.__version__,cuda=torch.version.cuda,
            cuda_available=True,gpu=torch.cuda.get_device_name(0),
            torch_file=torch.__file__,torchvision_file=torchvision.__file__,
            matrix_multiplication='passed',cuda_nms='passed')
pathlib.Path('ML/runs/gpu_smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
"""
    run(['-c',code])
    run(['-m','unittest','discover','-s','ML','-p','test_*.py'])
    if args.train:
        run([ROOT/'run_detector_experiment.py','--device','0','--lr',args.lr,'--freeze',args.freeze])


if __name__=='__main__':
    main()
