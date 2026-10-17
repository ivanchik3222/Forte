"""Local YOLO11n fine-tuning with saved weights and reproducible run metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('YOLO_CONFIG_DIR',str(ROOT/'cache/ultralytics'))
Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True,exist_ok=True)
os.environ.setdefault('YOLO_AUTOINSTALL','false')
os.environ['YOLO_OFFLINE']='true'
os.environ.setdefault('WANDB_DISABLED','true')
os.environ.setdefault('OMP_NUM_THREADS','4')


def local_yolo():
    from ultralytics import YOLO, settings
    # All training/inference is local. Disable optional external experiment integrations.
    disabled={k:False for k in ['sync','hub','wandb','mlflow','comet','clearml','neptune','raytune','dvc','tensorboard'] if k in settings}
    settings.update(disabled)
    return YOLO


def download_weights(path):
    import urllib.request
    if path.exists():
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    url='https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt'
    partial=path.with_suffix('.download')
    with urllib.request.urlopen(url,timeout=60) as response,partial.open('wb') as output:
        expected=response.headers.get('Content-Length')
        while chunk:=response.read(1024*1024):
            output.write(chunk)
    if partial.stat().st_size<4_000_000 or (expected and partial.stat().st_size!=int(expected)):
        raise ValueError('Incomplete model download')
    partial.replace(path)
    metadata=dict(url=url,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  license='AGPL-3.0; https://www.ultralytics.com/license')
    path.with_suffix('.source.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=ROOT/'datasets/cash_objects_aug_v1/data.yaml')
    parser.add_argument('--weights',type=Path,default=ROOT/'models/yolo11n.pt')
    parser.add_argument('--name',default='detector_augmented')
    parser.add_argument('--epochs',type=int,default=10)
    parser.add_argument('--batch',type=int,default=5)
    parser.add_argument('--imgsz',type=int,default=640)
    parser.add_argument('--device',default=None)
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--lr',type=float,default=.0015)
    parser.add_argument('--freeze',type=int,default=0)
    parser.add_argument('--download-only',action='store_true')
    args=parser.parse_args()
    download_weights(args.weights)
    if args.download_only:
        print('Pretrained weights:',args.weights,flush=True)
        return
    import torch,ultralytics
    if args.device is None:
        args.device='0' if torch.cuda.is_available() else 'cpu'
    torch.set_num_threads(args.threads)
    YOLO=local_yolo()
    run=ROOT/'runs'/args.name
    if run.exists():
        raise FileExistsError(f'Choose a new --name: {run} already exists')
    data=args.data.resolve();manifest=data.parent/'manifest.json'
    metadata=dict(seed=args.seed,torch=torch.__version__,ultralytics=ultralytics.__version__,
                  epochs=args.epochs,batch=args.batch,imgsz=args.imgsz,lr=args.lr,freeze=args.freeze,
                  device=args.device,cuda=torch.version.cuda,
                  gpu=torch.cuda.get_device_name(0) if args.device!='cpu' else None,
                  pretrained_sha256=hashlib.sha256(args.weights.read_bytes()).hexdigest(),
                  dataset_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                  dataset_summary=json.loads((data.parent/'summary.json').read_text(encoding='utf-8')),
                  note='Offline train-only variants; online image augmentations disabled for comparison')
    model=YOLO(str(args.weights))
    model.add_callback('on_pretrain_routine_end',lambda trainer:torch.set_num_threads(args.threads))
    # Equal batch/update counts can be used to compare original vs expanded data.
    results=model.train(data=str(data),epochs=args.epochs,batch=args.batch,imgsz=args.imgsz,
                        device=args.device,workers=0,seed=args.seed,deterministic=True,
                        optimizer='AdamW',lr0=args.lr,lrf=.1,cos_lr=True,warmup_epochs=0.,
                        nbs=args.batch,weight_decay=.0005,freeze=args.freeze,amp=False,
                        hsv_h=0.,hsv_s=0.,hsv_v=0.,degrees=0.,translate=0.,scale=0.,
                        shear=0.,perspective=0.,flipud=0.,fliplr=0.,mosaic=0.,mixup=0.,
                        copy_paste=0.,erasing=0.,auto_augment=None,
                        project=str(ROOT/'runs'),name=args.name,exist_ok=False,
                        save=True,save_period=5,patience=args.epochs+1,plots=True,
                        cache=False,verbose=False)
    run=Path(model.trainer.save_dir)
    metadata['best_weights']=str(run/'weights/best.pt')
    metadata['last_weights']=str(run/'weights/last.pt')
    metadata['completed_epochs']=int(model.trainer.epoch)+1
    metadata['final_validation']=results.results_dict if results else {}
    (run/'run_metadata.json').write_text(json.dumps(metadata,indent=2,default=str),encoding='utf-8')
    print('Saved:',metadata['best_weights'],flush=True)


if __name__=='__main__':
    main()
