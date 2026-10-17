"""Extract one keyframe per source plus both independently labelled duplicate-event points."""
from pathlib import Path
import json
import cv2
from PIL import Image,ImageDraw
from pipeline import ROOT,manifest,save_json

def main():
    dest=ROOT/'annotations/corrected';(dest/'images').mkdir(parents=True,exist_ok=True)
    records=[]
    for r in manifest(ROOT/'open/open'):
        cap=cv2.VideoCapture(r['path']);duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/cap.get(cv2.CAP_PROP_FPS)
        for t in r['timestamps_sec'] or [round(duration*.5,1)]:
            cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,f=cap.read()
            if not ok:raise ValueError(r['path'])
            actual=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            name=f'forte_{r["video_ids"][0]:02d}_{t:05.1f}'.replace('.','p')+'.jpg'
            image=Image.fromarray(cv2.cvtColor(f,cv2.COLOR_BGR2RGB)).crop((0,0,464,661))
            image.save(dest/'images'/name,quality=95)
            records.append(dict(file_name=name,video_ids=r['video_ids'],source_sha256=r['sha256'],timestamp_sec=actual,
                                crop_xyxy=[0,0,464,661],width=464,height=661,source='forte',review_status='pending',boxes=[],ignore_regions=[]))
        cap.release()
    save_json(dest/'frames.json',records)
    # Two native-resolution frames per row, three rows per sheet.
    for i in range(0,len(records),6):
        group=records[i:i+6];sheet=Image.new('RGB',(928,691*((len(group)+1)//2)),'white');d=ImageDraw.Draw(sheet)
        for j,r in enumerate(group):
            x=(j%2)*464;y=(j//2)*691
            sheet.paste(Image.open(dest/'images'/r['file_name']),(x,y+30));d.text((x+5,y+5),r['file_name'],fill='black')
        sheet.save(dest/f'sheet_{i//6+1:02d}.jpg',quality=95)
    print('frames',len(records),flush=True)

if __name__=='__main__':main()
