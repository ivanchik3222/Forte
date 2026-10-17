"""Collect saved development scores and plot augmentation runs without new evaluation."""
import csv
import json

from train_detector import ROOT


def object_scores(metrics):
    fixed=metrics['fixed_threshold'];tp,fp,fn=(fixed[k] for k in ('tp','fp','fn'))
    return dict(map50=metrics['map50'],map50_95=metrics['map50_95'],
                precision=fixed['precision'],recall=fixed['recall'],f1=2*tp/(2*tp+fp+fn),
                tp=tp,fp=fp,fn=fn,hand_ap=metrics['per_class_ap']['hand']['map50_95'],
                cash_ap=metrics['per_class_ap']['cash']['map50_95'],
                cash_tp=fixed['per_class']['cash']['tp'],hand_tp=fixed['per_class']['hand']['tp'])


if __name__=='__main__':
    main=json.loads((ROOT/'runs/cash_yolo11n_augmented_val/metrics.json').read_text(encoding='utf-8'))
    compared=json.loads((ROOT/'runs/cash_aug_v2_comparison.json').read_text(encoding='utf-8'))
    focused=json.loads((ROOT/'runs/cash_aug_v2_focused_comparison.json').read_text(encoding='utf-8'))
    video=json.loads((ROOT/'runs/native_video_aug_v2/metrics.json').read_text(encoding='utf-8'))
    scores={'current_v1':object_scores(main),'matched_v1':object_scores(compared['results']['control']),
            'full_v2':object_scores(compared['results']['expanded']),'focused_v2':object_scores(focused['metrics'])}
    report=dict(object_validation=scores,object_confidence=.25,object_matching_iou=.5,object_nms_iou=.7,
                object_val_frames=10,video_validation={k:r['metrics'] for k,r in video['results'].items()},
                best_object_map=max(scores,key=lambda k:scores[k]['map50_95']),
                best_object_fixed_f1=max(scores,key=lambda k:scores[k]['f1']),
                source_update_budgets=dict(current_v1=900,matched_v1=1980,full_v2=1980,focused_v2=1998),
                main_model_replaced=False,
                limitations=['Development VAL only; one seed and small shared-camera holdout',
                             'Focused run selected after seeing full-package recall loss',
                             'Object AP and video binary F1 evaluate different tasks',
                             'No new test evaluation and no guaranteed improvement on new scenes'])
    (ROOT/'runs/augmentation_v2_summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig,axes=plt.subplots(2,2,figsize=(14,8.5),layout='constrained')
    labels=['Current v1','Matched v1','Full v2','Focused v2'];colors=['#64748b','#d28b32','#307cc1','#169783']
    runs=[('cash_yolo11n_augmented',45),('cash_aug_v2_control',45),('cash_aug_v2_expanded',99),('cash_aug_v2_focused',54)]
    for (run,batches),label,color in zip(runs,labels,colors):
        with (ROOT/'runs'/run/'results.csv').open(encoding='utf-8') as handle:rows=list(csv.DictReader(handle))
        axes[0,0].plot([int(r['epoch'])*batches for r in rows],[float(r['metrics/mAP50-95(B)']) for r in rows],label=label,color=color)
    axes[0,0].set(title='Object VAL: training history',xlabel='Optimizer updates',ylabel='mAP50-95',ylim=(0,.4))
    axes[0,0].legend(fontsize=9)
    x=np.arange(2)
    for i,(key,color,label) in enumerate(zip(scores,colors,labels)):
        axes[0,1].bar(x+(i-1.5)*.18,[scores[key]['hand_ap'],scores[key]['cash_ap']],width=.18,color=color,label=label)
    axes[0,1].set(xticks=x,xticklabels=['Hand','Cash'],title='Object VAL: critical-class AP50-95',ylim=(0,.35))
    axes[0,1].legend(fontsize=9)
    x=np.arange(3)
    for i,(key,color,label) in enumerate(zip(scores,colors,labels)):
        axes[1,0].bar(x+(i-1.5)*.18,[scores[key][m] for m in ('precision','recall','f1')],width=.18,color=color,label=label)
    axes[1,0].set(xticks=x,xticklabels=['Precision','Recall','Micro F1'],title='Object VAL: fixed conf=0.25',ylim=(0,1))
    values=[video['results'][k]['metrics']['f1'] for k in ('control','augmented')]
    axes[1,1].bar(['Original clips','Augmented FPS clips'],values,color=['#64748b','#307cc1'])
    axes[1,1].set(title='Separate weak video-label task: VAL F1',ylim=(0,1))
    for i,value in enumerate(values):axes[1,1].text(i,value+.025,f'{value:.3f}',ha='center')
    for ax in axes.flat:ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('Development only: 10 object frames / 10 video recordings; no fresh test',fontsize=12)
    fig.savefig(ROOT/'runs/augmentation_v2_comparison.png',dpi=150)
    print(json.dumps(report,indent=2),flush=True)
