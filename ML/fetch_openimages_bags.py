"""Small bag-only candidate supplement with per-image author/license provenance."""
import csv,json,urllib.request,collections
from pathlib import Path
from PIL import Image,ImageDraw
from pipeline import ROOT,save_json

DEST=ROOT/'external/openimages_bags'

def get(url,path):
    if not path.exists():
        with urllib.request.urlopen(url,timeout=60) as r,path.open('wb') as f:
            while chunk:=r.read(1024*1024):f.write(chunk)

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    get('https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions-boxable.csv',DEST/'classes.csv')
    get('https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv',DEST/'boxes.csv')
    get('https://storage.googleapis.com/openimages/2018_04/validation/validation-images-with-rotation.csv',DEST/'images.csv')
    classes=dict(csv.reader((DEST/'classes.csv').open(encoding='utf-8')))
    bags={k for k,v in classes.items() if v.lower()=='handbag'}
    humans={k for k,v in classes.items() if v.lower() in ['person','man','woman','boy','girl','human hand']}
    by=collections.defaultdict(list)
    for r in csv.DictReader((DEST/'boxes.csv').open()):by[r['ImageID']].append(r)
    metadata={r['ImageID']:r for r in csv.DictReader((DEST/'images.csv').open(encoding='utf-8'))}
    candidates=[]
    for iid,boxes in by.items():
        targets=[b for b in boxes if b['LabelName'] in bags and b['IsGroupOf']=='0' and b['IsDepiction']=='0']
        if not targets or any(b['LabelName'] in humans for b in boxes):continue
        if 'creativecommons.org/licenses/by/' not in metadata.get(iid,{}).get('License',''):continue
        target=max(targets,key=lambda b:(float(b['XMax'])-float(b['XMin']))*(float(b['YMax'])-float(b['YMin'])))
        area=(float(target['XMax'])-float(target['XMin']))*(float(target['YMax'])-float(target['YMin']))
        if area<.08:continue
        candidates.append((iid,targets,area))
    candidates.sort(key=lambda r:-r[2]);result=[]
    for iid,boxes,area in candidates[:16]:
        path=DEST/(iid+'.jpg');get(f'https://open-images-dataset.s3.amazonaws.com/validation/{iid}.jpg',path)
        im=Image.open(path);w,h=im.size
        bboxes=[[round(float(b['XMin'])*w),round(float(b['YMin'])*h),round(float(b['XMax'])*w),round(float(b['YMax'])*h)] for b in boxes]
        result.append(dict(image_id=iid,path=str(path.resolve()),width=w,height=h,bag_boxes=bboxes,
                           metadata=metadata[iid],review_status='pending'))
        print('bag candidate',len(result),iid,flush=True)
    save_json(DEST/'candidates.json',result)
    for start in range(0,len(result),8):
        sheet=Image.new('RGB',(1280,350*((min(8,len(result)-start)+3)//4)),'white');d=ImageDraw.Draw(sheet)
        for j,r in enumerate(result[start:start+8]):
            im=Image.open(r['path']).convert('RGB');dr=ImageDraw.Draw(im)
            for b in r['bag_boxes']:dr.rectangle(b,outline='red',width=3)
            im.thumbnail((320,320));x=(j%4)*320;y=(j//4)*350;sheet.paste(im,(x,y+25));d.text((x+3,y+3),f'BAG {start+j:02d} '+r['image_id'],fill='black')
        sheet.save(DEST/f'sheet_{start//8+1}.jpg',quality=95)
    print('candidate count',len(result),flush=True)

if __name__=='__main__':main()
