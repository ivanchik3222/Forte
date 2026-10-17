"""Train expanded augmentations and a matched-update v1 control; evaluate VAL only."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from train_detector import ROOT


def execute(command, log):
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    with log.open('w',encoding='utf-8') as output:
        subprocess.run([sys.executable,'-X','utf8',*command],stdout=output,stderr=subprocess.STDOUT,check=True,env=env)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix',default='cash_aug_v2')
    parser.add_argument('--epochs',type=int,default=20)
    parser.add_argument('--model-dir',type=Path,default=ROOT/'models/cash_detector_aug_v2')
    args=parser.parse_args()
    control=ROOT/'datasets/cash_objects_aug_v1';expanded=ROOT/'datasets/cash_objects_aug_v2'
    sizes={}
    for key,path in (('control',control),('expanded',expanded)):
        rows=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
        sizes[key]=sum(r['split']=='train' for r in rows)
    updates=(sizes['expanded']//5)*args.epochs
    if any(v%5 for v in sizes.values()) or updates%(sizes['control']//5):
        raise ValueError('Choose epochs giving equal complete optimizer update counts')
    epochs=dict(expanded=args.epochs,control=updates//(sizes['control']//5))
    if args.model_dir.exists():raise FileExistsError(args.model_dir)
    for kind in ('control','expanded'):
        for suffix in ('','_val'):
            if (ROOT/'runs'/(args.prefix+'_'+kind+suffix)).exists():raise FileExistsError('Choose a new --prefix')
    results={}
    for kind,path in (('control',control),('expanded',expanded)):
        name=args.prefix+'_'+kind
        execute([str(ROOT/'train_detector.py'),'--data',str(path/'data.yaml'),'--name',name,
                 '--epochs',str(epochs[kind]),'--batch','5','--imgsz','640','--device','0',
                 '--lr','0.0005','--freeze','10'],ROOT/'runs'/(name+'.log'))
        print('Trained',name,epochs[kind],'epochs',updates,'updates',flush=True)
        weights=ROOT/'runs'/name/'weights/best.pt'
        execute([str(ROOT/'evaluate_detector.py'),str(weights),'--data',str(ROOT/'datasets/cash_objects_v1'),
                 '--split','val','--name',name+'_val','--device','0'],ROOT/'runs'/(name+'_val.log'))
        results[kind]=json.loads((ROOT/'runs'/(name+'_val')/'metrics.json').read_text(encoding='utf-8'))
        print('VAL',kind,'mAP50-95',round(results[kind]['map50_95'],4),flush=True)
    winner=max(results,key=lambda k:results[k]['map50_95'])
    report=dict(task='Object detector augmentation comparison',optimizer_updates_per_run=updates,
                train_images=sizes,epochs=epochs,results=results,winner_by_val_map50_95=winner,
                delta_map50_95=results['expanded']['map50_95']-results['control']['map50_95'],
                production_model_replaced=False,new_candidate=str(args.model_dir.resolve()),
                limitations=['10 validation frames, one seed, repeated development on the same VAL',
                             'No new test evaluation; v1 test remains historical',
                             'Validation frequency and epoch LR scheduling differ with train size',
                             'FPS clips are separate temporal assets, not dense object training labels',
                             'More synthetic views do not add independent videos or true cash examples'])
    args.model_dir.mkdir(parents=True)
    trained=ROOT/'runs'/(args.prefix+'_expanded')
    for name in ('best.pt','last.pt'):shutil.copyfile(trained/'weights'/name,args.model_dir/name)
    shutil.copyfile(trained/'args.yaml',args.model_dir/'training_args.yaml')
    shutil.copyfile(expanded/'ATTRIBUTION.md',args.model_dir/'DATA_ATTRIBUTION.md')
    report['new_candidate_sha256']=hashlib.sha256((args.model_dir/'best.pt').read_bytes()).hexdigest()
    (args.model_dir/'model_card.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (ROOT/'runs'/(args.prefix+'_comparison.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
