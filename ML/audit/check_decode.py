from pathlib import Path
import json, statistics
import av,cv2
from PIL import Image,ImageDraw
out=Path(__file__).resolve().parent
root=out.parent/'open/open/videos'
rows=json.loads((out/'video_inventory.json').read_text(encoding='utf-8'))
checks=[]; strips=[]
for row in rows:
    count=0;first=last=None;error=None
    try:
        with av.open(str(root/row['file'])) as c:
            audio=len(c.streams.audio)
            stream=c.streams.video[0]
            codec=stream.codec_context.name
            for frame in c.decode(video=0):
                count+=1
                if frame.time is not None:
                    if first is None:first=frame.time
                    last=frame.time
    except Exception as e:error=str(e)
    checks.append(dict(file=row['file'],decoded_frames=count,first_pts_sec=first,last_pts_sec=last,audio_streams=audio,codec=codec,error=error))
    if row['timestamp_sec'] is not None:
        t=row['timestamp_sec'];cap=cv2.VideoCapture(str(root/row['file']))
        strip=Image.new('RGB',(1160,350),'white');d=ImageDraw.Draw(strip)
        for j,offset in enumerate([-4,-2,0,2,4]):
            sec=min(row['duration_sec']-.1,max(0,t+offset));cap.set(cv2.CAP_PROP_POS_MSEC,sec*1000);ok,f=cap.read()
            d.text((232*j+4,3),f"X-{int(''.join(filter(str.isdigit,row['file'])))} {sec:.1f}s",fill='black')
            if ok:
                im=Image.fromarray(cv2.cvtColor(f,cv2.COLOR_BGR2RGB)).crop((0,0,464,650));im.thumbnail((232,325));strip.paste(im,(232*j,22))
        cap.release();strips.append(strip)
for i in range(0,len(strips),4):
    sheet=Image.new('RGB',(1160,350*len(strips[i:i+4])),'white')
    for j,strip in enumerate(strips[i:i+4]):sheet.paste(strip,(0,j*350))
    sheet.save(out/f'events_{i//4+1}.jpg')
(out/'decode_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print('decode_errors', [r for r in checks if r['error']])
print('frame_count_mismatches',[r['file'] for r,v in zip(checks,rows) if r['decoded_frames']!=v['frames']])
print('audio_stream_counts', sorted(set(r['audio_streams'] for r in checks)))
print('codecs',sorted(set(r['codec'] for r in checks)))
print('total_bytes',sum(r['bytes'] for r in rows))
for positive in [True,False]:
    ds=[r['duration_sec'] for r in rows if (r['timestamp_sec'] is not None)==positive]
    print('positive',positive,'count',len(ds),'mean_sec',statistics.mean(ds),'median_sec',statistics.median(ds))
