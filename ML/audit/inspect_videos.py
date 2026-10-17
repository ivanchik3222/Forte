from pathlib import Path
import json, re, hashlib
import cv2
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
out = root / 'audit'
labels = json.loads((out / 'labels_raw.json').read_text(encoding='utf-8-sig'))
key = lambda s: int(re.search(r'\d+', s).group())
indexed = {key(r['name']): r for r in labels}
results, tiles = [], []
for path in sorted((root / 'open/open/videos').glob('*'), key=lambda p:key(p.stem)):
    row = indexed.get(key(path.stem), {})
    nums = list(map(int, re.findall(r'\d+', row.get('timestamp') or '')))
    t = nums[0]*60+nums[1] if len(nums)>1 else nums[0] if nums else None
    cap = cv2.VideoCapture(str(path))
    fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = count/fps if fps else 0
    rec = dict(file=path.name, label=row.get('label'), timestamp_sec=t, duration_sec=round(duration,3), fps=fps, frames=int(count), width=int(cap.get(3)),height=int(cap.get(4)), bytes=path.stat().st_size,opened=cap.isOpened(),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    times = [max(0,t-3),t,min(duration-.1,t+3)] if t is not None else [duration*.2,duration*.5,duration*.8]
    strip=Image.new('RGB',(960,210),'white'); draw=ImageDraw.Draw(strip)
    for j, sec in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC,sec*1000)
        ok, frame=cap.read()
        if ok:
            im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)); im.thumbnail((320,180))
            strip.paste(im,(j*320,24))
        draw.text((j*320+5,5),f"X-{key(path.stem)}  {sec:.1f}s  {'VIOLATION' if t is not None else 'NORMAL'}",fill='black')
    strip.save(out / f'video_{key(path.stem):02d}.jpg')
    tiles.append(strip); results.append(rec);cap.release()
for start in range(0,len(tiles),7):
    sheet=Image.new('RGB',(960,210*len(tiles[start:start+7])),'white')
    for j,tile in enumerate(tiles[start:start+7]):sheet.paste(tile,(0,j*210))
    sheet.save(out/f'contact_{start//7+1}.jpg')
(out/'video_inventory.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
print('TOTAL',len(results),'SECONDS',sum(r['duration_sec'] for r in results))
print('MISSING VIDEOS', sorted(set(indexed)-{key(r['file']) for r in results}))
print('MISSING LABELS', [r['file'] for r in results if not r['label']])
print('INVALID TIMES', [r['file'] for r in results if r['timestamp_sec'] is not None and r['timestamp_sec']>=r['duration_sec']])
