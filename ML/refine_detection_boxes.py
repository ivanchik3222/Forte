"""Apply explicitly inspected pixel corrections, not model predictions."""
import json
from pipeline import ROOT,save_json

def main():
    root=ROOT/'annotations/corrected';path=root/'manual_boxes.json'
    original=json.loads(path.read_text(encoding='utf-8'));corrections=json.loads((root/'roi_refinements.json').read_text())
    if not (root/'manual_boxes_draft.json').exists():save_json(root/'manual_boxes_draft.json',original)
    for name,classes in corrections.items():
        if name not in original:raise ValueError(name)
        for label,boxes in classes.items():
            original[name][label]=[[x1,y1+300,x2,y2+300] for x1,y1,x2,y2 in boxes]
    save_json(path,original);print('Applied visual refinements',len(corrections))

if __name__=='__main__':main()
