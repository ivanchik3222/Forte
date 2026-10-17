"""Follow-up: preserve small-object detail after the full package reduced VAL recall."""
import hashlib
import json
import shutil

from augment_detection_v2 import export
from run_augmentation_v2 import execute
from train_detector import ROOT


if __name__=='__main__':
    data=ROOT/'datasets/cash_objects_aug_focused_v2'
    out=ROOT/'models/cash_detector_aug_focused_v2'
    name='cash_aug_v2_focused'
    if out.exists() or (ROOT/'runs'/name).exists():raise FileExistsError('Preserve previous run')
    export(ROOT/'datasets/cash_objects_v1',data,42,('mirror','grayscale','scale_up','dark','bright'))
    execute([str(ROOT/'train_detector.py'),'--data',str(data/'data.yaml'),'--name',name,
             '--epochs','37','--batch','5','--imgsz','640','--device','0','--lr','0.0005','--freeze','10'],
            ROOT/'runs'/(name+'.log'))
    weights=ROOT/'runs'/name/'weights/best.pt'
    execute([str(ROOT/'evaluate_detector.py'),str(weights),'--data',str(ROOT/'datasets/cash_objects_v1'),
             '--split','val','--name',name+'_val','--device','0'],ROOT/'runs'/(name+'_val.log'))
    metrics=json.loads((ROOT/'runs'/(name+'_val')/'metrics.json').read_text(encoding='utf-8'))
    out.mkdir(parents=True)
    for f in ('best.pt','last.pt'):shutil.copyfile(ROOT/'runs'/name/'weights'/f,out/f)
    shutil.copyfile(ROOT/'runs'/name/'args.yaml',out/'training_args.yaml')
    shutil.copyfile(data/'ATTRIBUTION.md',out/'DATA_ATTRIBUTION.md')
    card=dict(task='Small-object focused augmentation follow-up',epochs=37,train_images=270,
              optimizer_updates=1998,control_updates=1980,update_budget_difference_percent=100*(1998/1980-1),
              weights_sha256=hashlib.sha256((out/'best.pt').read_bytes()).hexdigest(),metrics=metrics,
              production_model_replaced=False,
              limitations=['Development follow-up after full augmentation VAL recall declined',
                           'Single seed and same 10 VAL frames; no new independent test',
                           '0.91% more optimizer updates; best checkpoint selection frequency differs',
                           'No isolated attribution of gain/loss to one augmentation'])
    (out/'model_card.json').write_text(json.dumps(card,indent=2),encoding='utf-8')
    (ROOT/'runs'/(name+'_comparison.json')).write_text(json.dumps(card,indent=2),encoding='utf-8')
    print(json.dumps(card,indent=2),flush=True)
