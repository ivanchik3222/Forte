import json,collections,hashlib
from PIL import Image,ImageDraw
from pipeline import ROOT,save_json

def main():
    root=ROOT/'external/cash_counter_theft_v2';records=[]
    for p in sorted(root.rglob('_annotations.coco.json')):
        d=json.loads(p.read_text());cats={c['id']:c['name'] for c in d['categories']};by=collections.defaultdict(list)
        for a in d['annotations']:by[a['image_id']].append(dict(label=cats[a['category_id']],bbox=a['bbox']))
        for im in d['images']:
            path=p.parent/im['file_name'];boxes=by[im['id']]
            cash=[b for b in boxes if b['label']=='Cash'];hands=[b for b in boxes if b['label']=='Hand']
            if cash and hands:
                records.append(dict(path=str(path.resolve()),file_name=im['file_name'],width=im['width'],height=im['height'],
                                    original_split=p.parent.name,boxes=boxes,rank=max(b['bbox'][2]*b['bbox'][3] for b in cash)))
    records.sort(key=lambda r:-r['rank'])
    # All source splits are auxiliary train only; final evaluation is ForteBank only.
    seen=set();chosen=[]
    for r in records:
        image=Image.open(r['path']).convert('RGB');small=image.resize((16,16)).convert('L')
        pixels=list(small.getdata());bits=''.join('1' if v>sum(pixels)/len(pixels) else '0' for v in pixels)
        if bits in seen:continue
        seen.add(bits);chosen.append(r)
        if len(chosen)>=36:break
    dest=ROOT/'annotations/corrected';save_json(dest/'external_candidates.json',chosen)
    for offset in range(0,len(chosen),9):
        group=chosen[offset:offset+9];sheet=Image.new('RGB',(960,350*((len(group)+2)//3)),'white');dr=ImageDraw.Draw(sheet)
        for j,r in enumerate(group):
            im=Image.open(r['path']).convert('RGB');draw=ImageDraw.Draw(im)
            colors={'Cash':'lime','Hand':'red','Cashier':'cyan','Customer':'cyan'}
            for box in r['boxes']:
                if box['label'] not in colors:continue
                x,y,w,h=box['bbox'];draw.rectangle((x,y,x+w,y+h),outline=colors[box['label']],width=3)
                draw.text((x,max(0,y-12)),box['label'],fill=colors[box['label']])
            im.thumbnail((320,320));x=(j%3)*320;y=(j//3)*350
            sheet.paste(im,(x,y+25));dr.text((x+3,y+3),f'EXT {offset+j:02d}',fill='black')
        sheet.save(dest/f'external_sheet_{offset//9+1}.jpg',quality=95)
    print('cash+hand candidates',len(records),'selected',len(chosen),flush=True)

if __name__=='__main__':main()
