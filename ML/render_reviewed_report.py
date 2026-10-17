"""Create a self-contained local video/timeline review page. No network resources."""
import argparse
import html
import json
from pathlib import Path


def render_report(report, video, output):
    video = Path(video).resolve()
    payload = json.dumps(report, ensure_ascii=False).replace('<', '\\u003c')
    role = 'Обучающий ролик · проверка работы интерфейса' if report['source_seen_during_training'] else (
        'Отложенный тест · не участвовал в новом обучении' if report['reserved_test'] else 'Новая запись')
    document = TEMPLATE.replace('__PAYLOAD__', payload).replace('__VIDEO_URI__', html.escape(video.as_uri(), quote=True))
    document = document.replace('__VIDEO_NAME__', html.escape(video.name)).replace('__ROLE__', html.escape(role))
    Path(output).write_text(document, encoding='utf-8')


TEMPLATE = '''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src file:; connect-src 'none'; img-src 'none'">
<title>Forte Control · разбор записи</title><style>
*{box-sizing:border-box}body{margin:0;background:#f6f5f7;color:#27232b;font:16px/1.5 system-ui,sans-serif}
header,main{max-width:1240px;margin:auto;padding:24px}header{display:flex;align-items:center;justify-content:space-between;gap:16px}
.brand{font-size:28px;font-weight:750;color:#a51351}.brand span{font-weight:350;color:#655c66;margin-left:8px;font-size:20px}
.local{font-size:13px;color:#6d6570}h1{font-size:clamp(24px,4vw,36px);margin:4px 0 8px;overflow-wrap:anywhere}
p{margin:6px 0 20px}.muted{color:#756c78}.layout{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:24px}
.player,.episodes{min-width:0;background:white;border:1px solid #e6e0e7;border-radius:20px;overflow:hidden}
video{width:100%;height:min(58vh,530px);display:block;background:#171519;object-fit:contain}.under{padding:20px}
.row{display:flex;justify-content:space-between;gap:16px;align-items:center}h2{font-size:20px;margin:0}
.episodes h2{padding:22px 24px;border-bottom:1px solid #eee9ee}.event{width:100%;display:block;text-align:left;border:0;border-bottom:1px solid #eee9ee;background:white;padding:20px 24px;color:inherit;font:inherit;cursor:pointer;min-height:60px}
.event:hover,.event[aria-pressed=true]{background:#faf0f5}.event:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid #32b7d7;outline-offset:-3px}
.event strong{color:#a51351;font-variant-numeric:tabular-nums}.event small{display:block;color:#756c78;margin-top:5px;font-size:13px}
.tag{font-size:12px;border:1px solid #e3dce5;border-radius:30px;padding:3px 9px;white-space:nowrap}
#details{padding:24px}.suggestion{padding:12px 0;border-bottom:1px solid #eee9ee}.suggestion:last-child{border:0}.suggestion small{display:block;color:#756c78;margin-top:3px}
.timeline{position:relative;height:38px;margin:20px 0 6px;background:#f0eaf0;border-radius:8px;overflow:hidden}
.mark{position:absolute;top:0;bottom:0;background:#ba2762;opacity:.6;min-width:2px;pointer-events:none}
input[type=range]{width:100%;accent-color:#a51351;min-height:32px;cursor:pointer}.notes{padding:20px 0;color:#756c78;font-size:13px;max-width:900px}
.empty{padding:24px;color:#756c78}.secondary{border:1px solid #ded5df;background:white;border-radius:10px;min-height:44px;padding:8px 14px;font:inherit;cursor:pointer}
#status{color:#8f4e22;font-size:14px}footer{margin-top:24px;border-top:1px solid #e3dce5;padding-top:16px;color:#756c78;font-size:12px}
@media(max-width:760px){header,main{padding:18px}.layout{grid-template-columns:1fr;gap:16px}.brand{font-size:24px}.local{font-size:11px}video{height:48vh}.under,#details{padding:18px}.event{padding:18px}.row{align-items:flex-start}.tag{white-space:normal}}
</style></head><body><header><div class="brand">forte<span>control</span></div><div class="local">Локальный исследовательский просмотр</div></header>
<main><div class="muted">__ROLE__</div><h1>__VIDEO_NAME__</h1>
<p class="muted">Эпизоды для проверки. Окончательное решение принимает специалист.</p>
<div class="layout"><section class="player" aria-label="Видеозапись">
<video id="video" src="__VIDEO_URI__" controls preload="metadata"></video><div class="under">
<div class="row"><span id="position">00:00</span><span class="muted" id="duration"></span></div>
<div class="timeline" id="timeline" aria-hidden="true"></div><label for="seek" class="muted">Перейти к моменту записи</label><input id="seek" type="range" min="0" step="0.1" value="0">
<div class="row"><button class="secondary" id="before">На 5 секунд назад</button><button class="secondary" id="after">На 5 секунд вперёд</button></div><p id="status" role="status"></p>
</div></section><section class="episodes"><h2 id="heading">Эпизоды</h2><div id="events"></div><div id="details" aria-live="polite"></div></section></div>
<div class="notes">Цветные участки — кандидаты модели, а не подтверждённые нарушения. Оценки действий показывают их относительный порядок среди известных типов; они не измеряют вероятность нарушения. Отсутствие отметки не доказывает отсутствие события.</div>
<footer id="footer"></footer></main><script>
const report=__PAYLOAD__;
const names={cash_handling:'Работа с купюрами',cash_on_work_surface:'Купюры на рабочей поверхности',object_handover:'Передача предмета',object_moved_toward_clothing:'Перемещение предмета к одежде',object_moved_into_bag:'Перемещение предмета в сумку',cabinet_door_opening:'Открытие дверцы шкафа',cabinet_door_closing:'Закрытие дверцы шкафа',person_leaves_work_area:'Уход из рабочей зоны',document_presented:'Предъявление документа'};
const video=document.getElementById('video'), seek=document.getElementById('seek');
const stamp=s=>{s=Math.max(0,Math.floor(s));return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')};
const node=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n};
const duration=Math.max(.1,report.duration_sec);seek.max=duration;document.getElementById('duration').textContent=stamp(duration);
const jump=sec=>{video.currentTime=Math.max(0,Math.min(duration,sec));seek.value=video.currentTime};
document.getElementById('heading').textContent='Кандидаты на проверку · '+report.events.length;
report.events.forEach((event,i)=>{
 const mark=node('span','','mark');mark.style.left=100*event.start_sec/duration+'%';mark.style.width=100*Math.max(.3,event.end_sec-event.start_sec)/duration+'%';document.getElementById('timeline').append(mark);
 const button=node('button','','event');button.type='button';button.setAttribute('aria-pressed','false');
 const row=node('div','','row');row.append(node('strong',stamp(event.timecode_sec)),node('span','Нужно проверить','tag'));button.append(row,node('small','Фрагмент '+stamp(event.start_sec)+' — '+stamp(event.end_sec)+' · оценка кандидата '+event.score.toFixed(2)));
 button.onclick=()=>{
  document.querySelectorAll('.event').forEach(b=>b.setAttribute('aria-pressed','false'));button.setAttribute('aria-pressed','true');jump(event.timecode_sec-4);
  const details=document.getElementById('details');details.replaceChildren(node('h2','Подсказки по действию'),node('p','Проверьте действие и контекст по видео.','muted'));
  (event.action_suggestions||[]).forEach((s,j)=>{const item=node('div',(j+1)+'. '+(names[s.kind]||s.kind),'suggestion');item.append(node('small','Относительная оценка '+s.relative_score.toFixed(2)+' · примеров: '+s.training_source_videos+' видео'));details.append(item)});
 };document.getElementById('events').append(button);
});
if(!report.events.length)document.getElementById('events').append(node('div','Кандидатов выше заданного порога нет. Запись всё равно можно проверить вручную.','empty'));
seek.oninput=()=>jump(Number(seek.value));video.ontimeupdate=()=>{seek.value=video.currentTime;document.getElementById('position').textContent=stamp(video.currentTime)};
video.onerror=()=>document.getElementById('status').textContent='Браузер не открыл исходное видео. Проверьте, что файл не перемещён, и откройте эту HTML-страницу локально.';
document.getElementById('before').onclick=()=>jump(video.currentTime-5);document.getElementById('after').onclick=()=>jump(video.currentTime+5);
document.getElementById('footer').textContent='Модель кандидатов: '+report.candidate_variant+' · модель действий: '+report.action_variant+' · локальная обработка '+report.elapsed_sec.toFixed(1)+' с.'+(report.reserved_test?' Ранее этот ролик встречался в исторических экспериментах; текущие модели на нём не обучались.':'');
</script></body></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prediction', type=Path); parser.add_argument('video', type=Path)
    args = parser.parse_args()
    render_report(json.loads(args.prediction.read_text()), args.video, args.prediction.with_suffix('.html'))
