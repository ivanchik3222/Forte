"""Matched-update augmentation comparison; choose by val and evaluate test once."""
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def plot_comparison(results,prefix,train_sizes):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig,(learning,classes_plot)=plt.subplots(1,2,figsize=(12,4.2),layout='constrained')
    colors={'augmented':'#2563eb','control':'#f97316'}
    for name in results:
        with (ROOT/'runs'/(prefix+'_'+name)/'results.csv').open(encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        learning.plot([int(r['epoch'])*train_sizes[name]//5 for r in rows],
                      [float(r['metrics/mAP50-95(B)']) for r in rows],label=name,color=colors[name])
    learning.set(xlabel='Optimizer updates',ylabel='Validation mAP50-95',ylim=(0,1),title='Original validation frames')
    learning.grid(alpha=.2);learning.legend()
    classes=list(results['augmented']['per_class_ap']);x=np.arange(len(classes))
    for name,offset in [('augmented',-.2),('control',.2)]:
        classes_plot.bar(x+offset,[results[name]['per_class_ap'].get(c,{}).get('map50_95',0) for c in classes],
                         width=.4,label=name,color=colors[name])
    classes_plot.set_xticks(x,[c.replace('_','\n') for c in classes],fontsize=9)
    classes_plot.set(ylim=(0,1),ylabel='Validation AP50-95',title='Best saved checkpoints, by class')
    classes_plot.grid(axis='y',alpha=.2);classes_plot.legend()
    fig.savefig(ROOT/'runs/detector_comparison.png',dpi=160)
    plt.close(fig)


def execute(arguments,log_name,marker):
    if marker.exists():
        print('Reusing completed stage:',marker,flush=True)
        return
    log=ROOT/'runs'/(log_name+'.log');log.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1')
    print('Starting:',log_name,'log:',log,flush=True)
    with log.open('w',encoding='utf-8') as output:
        result=subprocess.run([sys.executable,*map(str,arguments)],cwd=ROOT.parent,
                              env=env,stdout=output,stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{log_name} failed; inspect {log}')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--device',default='0')
    parser.add_argument('--augmented-epochs',type=int,default=20)
    parser.add_argument('--imgsz',type=int,default=640)
    parser.add_argument('--prefix',default='cash_yolo11n')
    parser.add_argument('--lr',type=float,default=.0015)
    parser.add_argument('--freeze',type=int,default=0)
    args=parser.parse_args()
    source=ROOT/'datasets/cash_objects_v1';augmented=ROOT/'datasets/cash_objects_aug_v1'
    src=json.loads((source/'summary.json').read_text(encoding='utf-8'))
    aug=json.loads((augmented/'summary.json').read_text(encoding='utf-8'))
    base_n=src['splits']['train']['images'];aug_n=aug['splits']['train']
    if aug_n%base_n:raise ValueError('Expected whole-number expansion for matched update count')
    epochs={'augmented':args.augmented_epochs,'control':args.augmented_epochs*(aug_n//base_n)}
    results={}
    for name,data in [('augmented',augmented),('control',source)]:
        run_name=args.prefix+'_'+name;run=ROOT/'runs'/run_name
        if (run/'run_metadata.json').exists():
            previous=json.loads((run/'run_metadata.json').read_text(encoding='utf-8'))
            expected=dict(epochs=epochs[name],batch=5,imgsz=args.imgsz,device=args.device,lr=args.lr,freeze=args.freeze,
                          dataset_manifest_sha256=hashlib.sha256((data/'manifest.json').read_bytes()).hexdigest())
            if any(previous.get(k)!=v for k,v in expected.items()):
                raise ValueError('Existing training differs from requested settings; choose a new --prefix')
        execute([ROOT/'train_detector.py','--data',data/'data.yaml','--epochs',epochs[name],
                 '--name',run_name,'--device',args.device,'--imgsz',args.imgsz,'--lr',args.lr,'--freeze',args.freeze],
                run_name,run/'run_metadata.json')
        val_name=run_name+'_val';val=ROOT/'runs'/val_name
        execute([ROOT/'evaluate_detector.py',run/'weights/best.pt','--name',val_name,
                 '--split','val','--device',args.device,'--imgsz',args.imgsz],
                val_name,val/'metrics.json')
        results[name]=json.loads((val/'metrics.json').read_text(encoding='utf-8'))
        results[name]['training_epochs']=epochs[name]
        results[name]['optimizer_updates']=epochs[name]*(aug_n if name=='augmented' else base_n)//5
    # Tie-break chosen in advance: prefer the augmented run. Never select by test metrics.
    selected=max(results,key=lambda n:(results[n]['map50_95'],n=='augmented'))
    run=ROOT/'runs'/(args.prefix+'_'+selected)
    test_name=args.prefix+'_selected_test';test=ROOT/'runs'/test_name
    execute([ROOT/'evaluate_detector.py',run/'weights/best.pt','--name',test_name,
             '--split','test','--device',args.device,'--imgsz',args.imgsz],test_name,test/'metrics.json')
    test_results=json.loads((test/'metrics.json').read_text(encoding='utf-8'))
    destination=ROOT/'models/cash_detector';destination.mkdir(parents=True,exist_ok=True)
    for file in ['best.pt','last.pt']:
        shutil.copyfile(run/'weights'/file,destination/file)
    shutil.copyfile(run/'args.yaml',destination/'training_args.yaml')
    shutil.copyfile((augmented if selected=='augmented' else source)/'ATTRIBUTION.md',destination/'DATA_ATTRIBUTION.md')
    card=dict(architecture='YOLO11n',classes=src['classes'],selected_run=selected,
              selection_rule='Highest original-val mAP50-95; augmented on ties; test not used for selection',
              weights_sha256=hashlib.sha256((destination/'best.pt').read_bytes()).hexdigest(),
              source_run=str(run),source_roi_xyxy=[0,300,464,610],imgsz=args.imgsz,
              model_license='Ultralytics AGPL-3.0; https://www.ultralytics.com/license',
              validation=results[selected],test=test_results,
              limitations=['Codex-reviewed labels, not expert adjudication','Only 10 val and 6 test images',
                           'Same camera in all native splits','Detects objects, not violations'])
    (destination/'model_card.json').write_text(json.dumps(card,indent=2),encoding='utf-8')
    report=dict(validation_comparison=results,selected=selected,test=test_results,
                augmented_minus_control_map50_95=results['augmented']['map50_95']-results['control']['map50_95'],
                limitations=['One seed only','Same optimizer update count, different validation frequency',
                             'Synthetic views are not additional independent scenes'])
    (ROOT/'runs/detector_comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    plot_comparison(results,args.prefix,dict(augmented=aug_n,control=base_n))
    print(json.dumps(dict(selected=selected,weights=str(destination/'best.pt'),
                          val_map50_95=results[selected]['map50_95'],test_map50_95=test_results['map50_95']),indent=2),flush=True)


if __name__=='__main__':
    main()
