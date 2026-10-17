"""Blinded conditional action naming on development captions, before/after LoRA.

The known interval is supplied, but neither its label nor human description is.
Exact kind agreement is NOT detection recall or factual caption correctness.
"""
import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from pathlib import Path

os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1')
ROOT=Path(__file__).resolve().parent


def summarize(rows):
    per_source=defaultdict(list); valid=0; specific=[]
    for row in rows:
        valid+=row['schema_valid']
        per_source[row['source_sha256']].append(row['kind_match'])
        if row['expected_kind'] not in ('other_visible_action','visibility_insufficient'): specific.append(row['kind_match'])
    return dict(examples=len(rows),schema_valid=valid,kind_correct=sum(r['kind_match'] for r in rows),
        source_balanced_kind_accuracy=sum(sum(v)/len(v) for v in per_source.values())/len(per_source),
        specific_kind_correct=sum(specific),specific_examples=len(specific),
        mean_reported_actions=sum(len(r.get('predicted_kinds',[])) for r in rows)/len(rows),
        mean_latency_sec=sum(r['elapsed_sec'] for r in rows)/len(rows))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter',type=Path)
    p.add_argument('--base-only',action='store_true')
    p.add_argument('--model-size',choices=['4b','8b'],default='4b')
    p.add_argument('--output',type=Path,default=ROOT/'runs/caption_evaluation_v1')
    p.add_argument('--data',type=Path,default=ROOT/'annotations/caption_training')
    p.add_argument('--limit',type=int,default=0)
    p.add_argument('--native-video',action='store_true',help='Exploratory native temporal-token input comparison')
    p.add_argument('--multi-action',action='store_true',help='Recall of partial annotations among at most four observations; NOT precision')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if not a.base_only and not a.adapter:p.error('--adapter is required unless --base-only is selected')
    if a.model_size!='4b' and a.adapter:p.error('Current trained adapters belong to the 4B base')
    from training_split import read_split
    from prepare_local_review import KINDS
    from prepare_caption_training import EXTERNAL
    from train_caption_lora import load_local_model,attach_lora
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template
    import mlx.core as mx
    mx.set_memory_limit(10*1024**3);mx.set_cache_limit(256*1024**2)
    config=json.loads((a.adapter/'adapter_config.json').read_text()) if a.adapter else None
    if config and config.get('runtime_fix')!=__import__('qwen_mlx_compat').PATCH_VERSION:
        raise ValueError('Adapter predates the DeepStack runtime fix; do not mix evaluation runtimes')
    weights=a.adapter/'adapters.safetensors' if a.adapter else None
    if config and hashlib.sha256(weights.read_bytes()).hexdigest()!=config['adapter_sha256']:raise ValueError('Adapter checksum mismatch')
    rows=[json.loads(line) for line in (a.data/'validation.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['source']=='bank_human_review']
    if a.limit:rows=rows[:a.limit]
    if not rows:raise ValueError('No bank development captions to evaluate')
    forbidden=set(config['train_source_hashes'] if config else [])|set(read_split()['holdout_source_hashes'])
    if {r['source_sha256'] for r in rows}&forbidden:raise ValueError('Evaluation source leakage')
    kinds=KINDS+sorted({v[0] for v in EXTERNAL.values()})
    model,processor=load_local_model(ROOT/f'models/qwen3_vl_{a.model_size}_mlx',a.model_size);model.eval()
    summaries={}
    for variant in (('base',) if a.base_only else ('base','adapted')):
        if variant=='adapted':
            attach_lora(model,config['layers'],config['rank'],config['alpha'],config['dropout'])
            model.load_weights(str(weights),strict=False);model.eval()
        predictions=[]
        for index,row in enumerate(rows):
            prompt=row['prompt']+f' Choose kind from this exact list: {kinds}. Do not return a list, return one JSON object.'
            if a.multi_action:
                prompt=prompt.replace('Describe one directly visible action or state supported by these frames.',
                    'Describe the distinct directly visible actions or states supported by the video.')
                prompt=prompt.replace('Return only JSON with kind and description.',
                    'Return only JSON with an observations array, at most four objects with kind and description. '
                    'Each description must be under twenty words. Do not list actions that are not directly visible.')
                prompt+=' Exact shape: {"observations":[{"kind":"one_allowed_kind","description":"short visible action"}]}. Every array item must be an object, never a string.'
            tick=time.monotonic()
            if a.native_video:
                from native_video_inputs import prepare_video_prompt
                prompt=prompt.replace('These are three chronological frames from one short video interval.',
                    f'This is a short video with context. Focus on a visible action in {row["start_sec"]:.2f}–{row["end_sec"]:.2f} seconds.')
                formatted,batch,timestamps=prepare_video_prompt(processor,row['source_path'],row['start_sec'],row['end_sec'],prompt)
                result=generate(model,processor,formatted,max_tokens=350 if a.multi_action else 220,temperature=0.,verbose=False,**batch)
                del batch
            else:
                formatted=apply_chat_template(processor,model.config,prompt,num_images=len(row['frames']))
                result=generate(model,processor,formatted,image=[f['path'] for f in row['frames']],max_tokens=350 if a.multi_action else 220,temperature=0.,verbose=False)
            try:
                obj=json.loads(result.text[result.text.find('{'):result.text.rfind('}')+1])
                if not isinstance(obj,dict):obj={}
                observations=obj.get('observations') if a.multi_action else [obj]
                valid=isinstance(observations,list) and (0 if a.multi_action else 1)<=len(observations)<=4 and all(
                    isinstance(o,dict) and o.get('kind') in kinds and isinstance(o.get('description'),str) and bool(o['description'].strip()) for o in observations)
                predicted=[o['kind'] for o in observations] if valid else []
            except (ValueError,TypeError):obj={};valid=False;predicted=[]
            prediction=dict(id=row['id'],source_sha256=row['source_sha256'],expected_kind=row['kind'],
                predicted_kind=obj.get('kind'),predicted_kinds=predicted,schema_valid=valid,kind_match=row['kind'] in predicted,
                raw_output=result.text,elapsed_sec=time.monotonic()-tick)
            predictions.append(prediction)
            # Descriptions and images never leave local files.
            (a.output/f'{variant}_predictions.json').write_text(json.dumps(predictions,ensure_ascii=False,indent=2))
            print(f'{variant} {index+1}/{len(rows)} schema={valid} latency={prediction["elapsed_sec"]:.1f}s',flush=True)
            mx.clear_cache()
        summaries[variant]=summarize(predictions)
    summary=dict(protocol='Blinded known-interval conditional kind agreement; shared taxonomy and prompts',
        data_protocol=str(a.data),
        native_video=a.native_video,
        multi_action=a.multi_action,
        metric='partial_annotation_type_recall' if a.multi_action else 'known_interval_single_kind_agreement',
        model_size=a.model_size,
        runtime_fix=__import__('qwen_mlx_compat').PATCH_VERSION,
        final_test_used=False,independent_final_test=False,adapter_sha256=config['adapter_sha256'] if config else None,results=summaries,
        limitations=['Only four annotated source videos in one development scene group',
                    'Partial annotations: another visible action may also be a valid answer',
                    'A matching kind does not validate every generated word',
                    'Known-interval task does not measure full-video event detection or legal verdict quality'])
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
