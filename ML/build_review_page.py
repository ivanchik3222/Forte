"""Build a self-contained local annotation page. No server, uploads or external scripts."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PAGE = r'''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Forte · Проверка разметки</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f7f5f7;color:#29232a;font:15px/1.5 system-ui,sans-serif}
header{padding:20px 28px;background:white;border-bottom:1px solid #e9e2e7;display:flex;align-items:center;gap:24px;flex-wrap:wrap}
header strong{font-size:24px;color:#a80d50}button,select,input,textarea{font:inherit}button{cursor:pointer;border:1px solid #d6cbd2;border-radius:10px;padding:10px 14px;background:white;color:#333}button.primary{background:#a80d50;color:white;border-color:#a80d50}
main{display:grid;grid-template-columns:250px minmax(0,1fr);max-width:1550px;margin:auto}nav{padding:16px;max-height:calc(100vh - 100px);overflow:auto;position:sticky;top:0}
nav button{display:block;width:100%;margin:0 0 8px;text-align:left}nav button.active{border:2px solid #a80d50;background:#fbeaf2}
article{padding:24px;min-width:0}.columns{display:grid;grid-template-columns:minmax(240px,1fr) minmax(300px,1fr);gap:24px}.card{background:white;border:1px solid #e4dce1;border-radius:16px;padding:20px;margin:0 0 20px}
video{width:100%;max-height:570px;background:#171317;border-radius:10px}.frames{display:flex;gap:8px;overflow:auto;margin-top:12px}.frames figure{margin:0;flex:0 0 100px}.frames img{width:100px;border-radius:6px}.frames figcaption{font-size:12px;text-align:center}
h1{font-size:25px;margin:0 0 8px}h2{font-size:18px;margin-top:0}.muted{color:#756a72}.notice{padding:12px;background:#fff6e8;border-radius:9px;font-size:13px}.field{display:block;margin:12px 0}input,select,textarea{width:100%;border:1px solid #d8cfd5;border-radius:8px;padding:10px}textarea{min-height:85px}.times{display:flex;gap:12px}.times label{flex:1}.proposal{border-top:1px solid #eee;padding:12px 0}.actions{display:flex;gap:8px;flex-wrap:wrap}.check{display:flex;gap:10px;align-items:center}.check input{width:auto}
@media(max-width:850px){main{display:block}nav{display:flex;overflow:auto;position:static;max-height:110px}nav button{min-width:170px;margin-right:8px}.columns{display:block}article{padding:14px}header{padding:16px}}
</style><header><strong>forte · разметка</strong><span id="progress"></span><button id="export" class="primary">Экспорт проверенной разметки</button></header>
<main><nav id="nav"></nav><article><h1 id="heading"></h1><p id="source" class="muted"></p><p class="notice">Предложения локальной модели требуют просмотра видео. Они не используются как подтверждённые метки. Видимое действие само по себе не устанавливает нарушение правила.</p>
<div class="columns"><section><div class="card"><video id="video" controls preload="metadata"></video><div class="actions"><button id="jump">К отмеченному моменту</button></div><div class="frames" id="frames"></div></div><div class="card"><h2>Предложения модели</h2><div id="proposals"></div></div></section>
<section><div class="card"><h2>Наблюдаемое действие</h2><label class="field">Тип<select id="kind"></select></label><div class="times"><label>Начало, с<input id="start" type="number" min="0" step="0.1"></label><label>Конец, с<input id="end" type="number" min="0" step="0.1"></label></div><label class="field">Что видно<textarea id="description" placeholder="Только наблюдаемое действие и ограничения видимости"></textarea></label><button id="add" class="primary">Сохранить наблюдение</button><p id="error" role="alert"></p></div>
<div class="card"><h2>Проверенные наблюдения</h2><div id="confirmed"></div><label class="check"><input id="reviewed" type="checkbox">Я просмотрел(а) фрагмент и проверил(а) разметку</label><p class="muted">Пустой список допустим, если наблюдение не подтверждается. Исходная метка банка сохраняется отдельно.</p></div></section></div></article></main>
<script id="data" type="application/json">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent), tasks=data.tasks;
const $=id=>document.getElementById(id), key='forte-local-annotations-v1';
let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch{}let current=0;
const persist=()=>{try{localStorage.setItem(key,JSON.stringify(saved))}catch{$('error').textContent='Не удалось сохранить в браузере. Скачайте JSON.'}renderNav()};
function state(){const id=tasks[current].id;return saved[id]||(saved[id]={reviewed:false,observations:[]})}
function renderNav(){ $('nav').replaceChildren();let reviewed=0;tasks.forEach((t,i)=>{const b=document.createElement('button');const done=saved[t.id]?.reviewed;if(done)reviewed++;b.textContent=(done?'✓ ':'')+'Видео '+t.video_ids.join('/')+' · '+t.center_sec.toFixed(1)+' с';b.className=i===current?'active':'';b.onclick=()=>{current=i;render()};$('nav').append(b)});$('progress').textContent=reviewed+' / '+tasks.length+' фрагментов проверено'}
function fill(o){$('kind').value=o.kind;$('start').value=o.start_sec.toFixed(2);$('end').value=o.end_sec.toFixed(2);$('description').value=o.description;$('reviewed').checked=false}
function renderConfirmed(){const container=$('confirmed');container.replaceChildren();state().observations.forEach((o,i)=>{const div=document.createElement('div');div.className='proposal';const p=document.createElement('p');p.textContent=o.kind+' · '+o.start_sec+'–'+o.end_sec+' с: '+o.description;const b=document.createElement('button');b.textContent='Удалить';b.onclick=()=>{state().observations.splice(i,1);state().reviewed=false;persist();renderConfirmed();$('reviewed').checked=false};div.append(p,b);container.append(div)});$('reviewed').checked=state().reviewed}
function render(){const t=tasks[current];renderNav();$('heading').textContent='Видео '+t.video_ids.join(' / ');$('source').textContent='Метка банка: '+(t.source_label?'нарушение':'без нарушения')+' · '+(t.reason==='original_bank_point'?'исходный таймкод':'пик модели на отложенном корректном видео');$('video').src=t.video_uri;$('video').onloadedmetadata=()=>{$('video').currentTime=Math.max(0,t.center_sec-4)};$('frames').replaceChildren();t.frame_samples.forEach(f=>{const figure=document.createElement('figure'),img=document.createElement('img'),caption=document.createElement('figcaption');img.src=f.image_uri;img.alt='Кадр '+f.timestamp_sec.toFixed(2)+' с';caption.textContent=f.timestamp_sec.toFixed(2)+' с';figure.append(img,caption);$('frames').append(figure)});$('proposals').replaceChildren();const proposal=t.machine_annotations?.proposal;if(proposal){proposal.observations.forEach(o=>{const div=document.createElement('div');div.className='proposal';const p=document.createElement('p');p.textContent=o.kind+': '+o.description;const b=document.createElement('button');b.textContent='Внести в форму для проверки';b.onclick=()=>fill(o);div.append(p,b);$('proposals').append(div)});const p=document.createElement('p');p.className='muted';p.textContent=proposal.uncertainties.join(' · ');$('proposals').append(p)}else{$('proposals').textContent='Предварительная разметка пока отсутствует или ответ модели не прошёл проверку.'}fill({kind:data.allowed_kinds[0],start_sec:t.center_sec,end_sec:t.center_sec,description:''});$('error').textContent='';renderConfirmed()}
data.allowed_kinds.forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=k;$('kind').append(o)});
$('jump').onclick=()=>{$('video').currentTime=Math.max(0,tasks[current].center_sec-2);$('video').play().catch(()=>{})};
$('add').onclick=()=>{const start=Number($('start').value),end=Number($('end').value),description=$('description').value.trim();if(!description||!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<start||(Number.isFinite($('video').duration)&&end>$('video').duration)){$('error').textContent='Проверьте описание и границы интервала.';return}state().observations.push({kind:$('kind').value,start_sec:start,end_sec:end,description,review_status:'human_reviewed',legal_rule_id:null});state().reviewed=false;state().updated_at=new Date().toISOString();persist();renderConfirmed();$('error').textContent='Сохранено в этом браузере. Экспортируйте JSON для переноса.'};
$('reviewed').onchange=()=>{state().reviewed=$('reviewed').checked;state().updated_at=new Date().toISOString();persist()};
$('export').onclick=()=>{const rows=tasks.filter(t=>saved[t.id]?.reviewed).map(t=>({task_id:t.id,source_sha256:t.source_sha256,video_ids:t.video_ids,source_label:t.source_label,original_points_sec:t.original_points_sec,...saved[t.id]}));const blob=new Blob([JSON.stringify({version:1,exported_at:new Date().toISOString(),review_source:'explicit_user_review',tasks:rows},null,2)],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='forte-reviewed-annotations.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)};
if(tasks.length)render();
</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue', type=Path, default=ROOT / 'annotations/local_review/queue.json')
    args = parser.parse_args()
    data = json.loads(args.queue.read_text())
    for task in data['tasks']:
        task['video_uri'] = Path(task['source_path']).as_uri()
        for frame in task['frame_samples']:
            frame['image_uri'] = Path(frame['image']).as_uri()
        path = args.queue.parent / 'proposals' / (task['id'] + '.json')
        if path.is_file():
            task['machine_annotations'] = json.loads(path.read_text())
    content = PAGE.replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c'))
    path = args.queue.parent / 'index.html'
    path.write_text(content, encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
