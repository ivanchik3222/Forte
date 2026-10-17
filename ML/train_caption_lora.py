"""Offline, completion-only QLoRA for factual captions on an Apple Silicon Mac.

The base model stays frozen. Only q/v projections in the last decoder layers are
trained. Validation NLL measures caption fit, not factual accuracy or violation F1.
"""
import argparse
import hashlib
import json
import math
import os
import random
import time
from pathlib import Path

os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
    HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1')

ROOT=Path(__file__).resolve().parent


def attach_lora(model,layers=4,rank=8,alpha=1.,dropout=0.):
    from mlx_vlm.trainer.lora import LoRaLayer
    model.freeze()
    if not 1<=layers<=len(model.layers): raise ValueError('Invalid adapter layer count')
    for block in model.layers[-layers:]:
        for name in ('q_proj','v_proj'):
            setattr(block.self_attn,name,LoRaLayer(getattr(block.self_attn,name),rank,alpha,dropout))
    return model


def prepare_example(model,processor,row,augment=False,rng=None):
    import mlx.core as mx
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import prepare_inputs
    from PIL import Image,ImageEnhance
    prompt=apply_chat_template(processor,model.config,row['prompt'],num_images=len(row['frames']))
    # The generation prefix ends at the assistant header. Append ONLY the response
    # and end token, with no additional user/image message or supervision on prompt.
    full=prompt+row['response']+processor.tokenizer.eos_token
    images=[Image.open(f['path']).convert('RGB') for f in row['frames']]
    if augment:
        factor=rng.uniform(.9,1.1)
        images=[ImageEnhance.Brightness(image).enhance(factor) for image in images]
    batch=prepare_inputs(processor,images=images,prompts=full)
    marker=processor.tokenizer.encode('<|im_start|>assistant\n',add_special_tokens=False)
    ids=batch['input_ids'][0].tolist()
    matches=[i+len(marker) for i in range(len(ids)-len(marker)+1) if ids[i:i+len(marker)]==marker]
    if len(matches)!=1: raise ValueError('Ambiguous completion boundary')
    batch['completion_start']=matches[0]
    if len(ids)>1800: raise ValueError('Caption exceeds safe training context; refusing truncation')
    if batch['completion_start']>=len(ids): raise ValueError('Empty supervised response')
    mx.eval({k:v for k,v in batch.items() if isinstance(v,mx.array)})
    return batch


def caption_loss(model,batch):
    import mlx.core as mx
    import mlx.nn as nn
    ids=batch['input_ids']; start=batch['completion_start']
    extra={k:v for k,v in batch.items() if k not in ('input_ids','pixel_values','attention_mask','completion_start')}
    outputs=model(ids[:,:-1],batch['pixel_values'],batch['attention_mask'][:,:-1],**extra)
    # Normalize by supervised tokens, not image/prompt length. Slice before casting.
    logits=outputs.logits[:,start-1:,:].astype(mx.float32)
    labels=ids[:,start:]
    if logits.shape[:2]!=labels.shape: raise ValueError('Completion alignment mismatch')
    return nn.losses.cross_entropy(logits,labels,reduction='mean')


def load_local_model(path,size='4b'):
    from download_review_model import MODEL_SPECS
    from mlx_vlm import load
    for name,expected in MODEL_SPECS[size]['files'].items():
        digest=hashlib.sha256()
        with (path/name).open('rb') as file:
            while chunk:=file.read(8*1024*1024): digest.update(chunk)
        if digest.hexdigest()!=expected: raise ValueError('Base model checksum mismatch')
    model,processor=load(str(path.resolve()),trust_remote_code=False)
    from qwen_mlx_compat import install_deepstack_fix
    install_deepstack_fix(model)
    return model,processor


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=ROOT/'annotations/caption_training')
    p.add_argument('--model',type=Path,default=ROOT/'models/qwen3_vl_4b_mlx')
    p.add_argument('--output',type=Path,default=ROOT/'runs/caption_lora_v1')
    p.add_argument('--steps',type=int,default=100)
    p.add_argument('--stage',choices=['external','bank','mixed'],default='mixed')
    p.add_argument('--resume',type=Path)
    p.add_argument('--layers',type=int,default=4)
    p.add_argument('--rank',type=int,default=8)
    p.add_argument('--learning-rate',type=float,default=2e-5)
    p.add_argument('--eval-every',type=int,default=25)
    p.add_argument('--eval-limit',type=int,default=0,help='0 means all validation captions')
    p.add_argument('--skip-eval',action='store_true',help='Resource pilot only; never qualifies a model')
    p.add_argument('--augment',action='store_true')
    args=p.parse_args()
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx.utils import tree_flatten
    from training_split import read_split,assert_training_sources
    mx.set_memory_limit(10*1024**3);mx.set_cache_limit(256*1024**2);mx.random.seed(42)
    rng=random.Random(42);args.output.mkdir(parents=True,exist_ok=True)
    rows=[json.loads(line) for line in (args.data/'train.jsonl').read_text().splitlines()]
    val=[json.loads(line) for line in (args.data/'validation.jsonl').read_text().splitlines()]
    split=read_split()
    assert_training_sources([r['source_sha256'] for r in rows+val if r['source']=='bank_human_review'],split)
    if {r['source_sha256'] for r in rows}&{r['source_sha256'] for r in val}: raise ValueError('Train/validation source overlap')
    if args.stage!='mixed': rows=[r for r in rows if (r['source']=='bank_human_review')==(args.stage=='bank')]
    if not rows: raise ValueError('Empty training data')
    if args.eval_limit:
        # Round-robin source partitions prevents accidentally omitting bank validation.
        groups=[[r for r in val if r['source']==s] for s in sorted({r['source'] for r in val})]
        val=[r for pair in __import__('itertools').zip_longest(*groups) for r in pair if r][:args.eval_limit]
    model,processor=load_local_model(args.model)
    attach_lora(model,args.layers,args.rank)
    inherited_sources=set()
    if args.resume:
        previous=json.loads((args.resume/'adapter_config.json').read_text())
        if previous.get('runtime_fix')!=__import__('qwen_mlx_compat').PATCH_VERSION:
            raise ValueError('Prior adapter used an incompatible vision runtime; restart from the verified base')
        if previous['layers']!=args.layers or previous['rank']!=args.rank: raise ValueError('Adapter configuration mismatch')
        if hashlib.sha256((args.resume/'adapters.safetensors').read_bytes()).hexdigest()!=previous['adapter_sha256']:
            raise ValueError('Prior adapter checksum mismatch')
        inherited_sources=set(previous['train_source_hashes'])
        if inherited_sources & (set(split['holdout_source_hashes']) | {r['source_sha256'] for r in val}):
            raise ValueError('Prior adapter saw a reserved or current validation source')
        model.load_weights(str(args.resume/'adapters.safetensors'),strict=False)
    trainable=tree_flatten(model.trainable_parameters())
    if not trainable or any(not name.endswith(('.A','.B')) for name,_ in trainable): raise ValueError('Base parameters must remain frozen')
    config=dict(layers=args.layers,rank=args.rank,alpha=1.,dropout=0.,base_model_sha256=__import__('review_with_local_vlm').MODEL_SHA256,
        runtime_fix=__import__('qwen_mlx_compat').PATCH_VERSION,
        stage=args.stage,steps=args.steps,learning_rate=args.learning_rate,augmentation=args.augment,seed=42,
        train_source_hashes=sorted({r['source_sha256'] for r in rows}|inherited_sources),validation_source_hashes=sorted({r['source_sha256'] for r in val}),
        prior_adapter=str(args.resume) if args.resume else None,final_test_used=False,
        trainable_parameters=sum(v.size for _,v in trainable),validation_claim='Teacher-forced caption NLL only; not factual accuracy',
        production_approved=False)
    (args.output/'adapter_config.json').write_text(json.dumps(config,indent=2))
    print(f'Train={len(rows)} validation={len(val)} parameters={config["trainable_parameters"]}',flush=True)
    optimizer=optim.AdamW(learning_rate=args.learning_rate,weight_decay=.01)
    value_grad=nn.value_and_grad(model,caption_loss)
    history=[]

    def evaluate(step):
        model.eval(); losses={}; started=time.monotonic()
        for row in val:
            batch=prepare_example(model,processor,row)
            loss=caption_loss(model,batch);mx.eval(loss)
            losses.setdefault(row['source'],[]).append(float(loss))
            del batch,loss;mx.clear_cache()
        means={s:sum(values)/len(values) for s,values in losses.items()}
        history.append(dict(step=step,validation_nll=means,elapsed_sec=time.monotonic()-started))
        (args.output/'validation.json').write_text(json.dumps(history,indent=2))
        print(f'Validation step={step}: {means}',flush=True)
        return means.get('bank_human_review',float('inf'))

    best=evaluate(0) if not args.skip_eval else float('inf')
    order=[]; started=time.monotonic(); losses=[]
    for step in range(1,args.steps+1):
        if not order: order=list(range(len(rows)));rng.shuffle(order)
        row=rows[order.pop()];model.train()
        batch=prepare_example(model,processor,row,args.augment,rng)
        loss,grad=value_grad(model,batch)
        grad,norm=optim.clip_grad_norm(grad,max_norm=1.)
        optimizer.update(model,grad);mx.eval(model.trainable_parameters(),optimizer.state,loss,norm)
        if not math.isfinite(float(loss)) or not math.isfinite(float(norm)):
            raise ValueError('Nonfinite training loss/gradient; refusing to save this checkpoint')
        losses.append(float(loss))
        if step==1 or step%5==0 or step==args.steps:
            print(f'Step {step}/{args.steps} nll={sum(losses[-5:])/len(losses[-5:]):.4f} '
                  f'sec/step={(time.monotonic()-started)/step:.2f} peak_gb={mx.get_peak_memory()/1024**3:.2f}',flush=True)
        del batch,loss,grad,norm;mx.clear_cache()
        if step%args.eval_every==0 or step==args.steps:
            weights=dict(tree_flatten(model.trainable_parameters()))
            mx.save_safetensors(str(args.output/'last.safetensors'),weights)
            score=evaluate(step) if not args.skip_eval else float('inf')
            if score<best:
                best=score;mx.save_safetensors(str(args.output/'adapters.safetensors'),weights)
                config['best_step']=step;config['best_bank_validation_nll']=score
            # A non-improving adapter is still preserved for comparison, never promoted.
            if not (args.output/'adapters.safetensors').exists():
                mx.save_safetensors(str(args.output/'adapters.safetensors'),weights)
                config['best_step']=None
            config['improved_bank_validation_nll']=config.get('best_step') is not None
            config['adapter_sha256']=hashlib.sha256((args.output/'adapters.safetensors').read_bytes()).hexdigest()
            (args.output/'adapter_config.json').write_text(json.dumps(config,indent=2))
    (args.output/'training.json').write_text(json.dumps(dict(losses=losses,elapsed_sec=time.monotonic()-started),indent=2))


if __name__=='__main__': main()
