"""Frozen R3D-18 clips plus a learned binary head; no invented rule labels."""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from PIL import Image
import torch
from torchvision.models.video import r3d_18

from predict_objects import frames

ROOT=Path(__file__).resolve().parent
CONFIG=dict(sample_fps=4.,clip_frames=16,output_stride=2,roi=[0,300,464,610],size=[168,112],
    expected_dimensions=[464,848],mean=[.43216,.394666,.37645],std=[.22803,.22145,.216989])
VARIANTS=('original','mirror','grayscale','dark','scale_down')


def clip_indices(times,centers,frame_count=16,fps=4.):
    times=np.asarray(times,dtype=float)
    if not len(times) or np.any(np.diff(times)<=0): raise ValueError('Strictly increasing PTS required')
    desired=np.asarray(centers)[:,None]+(np.arange(frame_count)-(frame_count-1)/2)[None,:]/fps
    right=np.searchsorted(times,desired).clip(0,len(times)-1)
    left=(right-1).clip(0,len(times)-1)
    return np.where(np.abs(times[left]-desired)<=np.abs(times[right]-desired),left,right)


def preprocess(rgb,variant='original'):
    if tuple(rgb.shape[:2])!=(848,464): raise ValueError('Binary classifier supports the native 464 x 848 camera only')
    a,b,c,d=CONFIG['roi'];image=Image.fromarray(rgb[b:d,a:c])
    if variant=='mirror': image=image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif variant=='grayscale': image=image.convert('L').convert('RGB')
    elif variant=='dark': image=Image.fromarray((np.asarray(image,dtype=np.float32)*.8).astype(np.uint8))
    elif variant=='scale_down':
        width,height=image.size
        scaled=image.resize((round(width*.9),round(height*.9)),Image.Resampling.BILINEAR)
        canvas=Image.new('RGB',(width,height),(114,114,114))
        canvas.paste(scaled,((width-scaled.width)//2,(height-scaled.height)//2));image=canvas
    elif variant!='original': raise ValueError('Unknown augmentation')
    return np.asarray(image.resize(tuple(CONFIG['size']),Image.Resampling.BILINEAR)).copy()


class R3DEncoder:
    def __init__(self,weights=ROOT/'models/r3d_18-b3b3357e.pth',device=None):
        weights=Path(weights)
        if not weights.is_file(): raise FileNotFoundError('Download official R3D-18 weights first; no automatic network access')
        self.sha256=hashlib.sha256(weights.read_bytes()).hexdigest()
        if not self.sha256.startswith('b3b3357e'): raise ValueError('Unexpected pretrained weights hash')
        torch.set_num_threads(4)
        self.device=device or ('cuda' if torch.cuda.is_available() else 'cpu')
        model=r3d_18(weights=None)
        model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True))
        model.fc=torch.nn.Identity()
        self.model=model.eval().to(self.device)
        self.mean=torch.tensor(CONFIG['mean'],device=self.device).view(1,3,1,1,1)
        self.std=torch.tensor(CONFIG['std'],device=self.device).view(1,3,1,1,1)

    def encode(self,source,variant='original',selected_centers=None,batch_size=4):
        times=[];pictures=[]
        for sec,rgb in frames(Path(source),CONFIG['sample_fps']):
            times.append(sec);pictures.append(preprocess(rgb,variant))
        times=np.asarray(times,dtype=np.float64)
        if not len(times): raise ValueError('No frames')
        pictures=np.stack(pictures)
        centers=times[::CONFIG['output_stride']] if selected_centers is None else np.asarray(selected_centers,dtype=np.float64)
        indices=clip_indices(times,centers)
        vectors=[]
        with torch.inference_mode():
            for start in range(0,len(centers),batch_size):
                clip=pictures[indices[start:start+batch_size]]
                tensor=torch.from_numpy(clip).permute(0,4,1,2,3).to(self.device,dtype=torch.float32)/255.
                tensor=(tensor-self.mean)/self.std
                with torch.autocast('cuda',enabled=self.device!='cpu'):
                    result=self.model(tensor)
                vectors.append(result.float().cpu().numpy())
        features=np.concatenate(vectors).astype(np.float32)
        if features.shape!=(len(centers),512) or not np.all(np.isfinite(features)):
            raise ValueError('Invalid R3D embeddings')
        return centers,features


def positive_mask(times,points,radius=.500001):
    times=np.asarray(times)
    mask=np.zeros(len(times),dtype=bool)
    for point in points:
        near=np.abs(times-point)<=radius
        if not np.any(near): near[np.argmin(np.abs(times-point))]=True
        mask|=near
    if not np.any(mask): raise ValueError('Positive source requires annotated event points')
    return mask


def scores(head,features):
    if head['kind']=='logistic': return head['model'].predict_proba(features)[:,1]
    if head['kind']!='point_mil_linear': raise ValueError('Unknown binary head')
    values=(features-head['mean'])/head['std']
    logits=values@head['weight']+head['bias']
    return 1/(1+np.exp(-np.clip(logits,-60,60)))


class BinaryVideoClassifier:
    def __init__(self,head_path,weights=ROOT/'models/r3d_18-b3b3357e.pth',device=None):
        self.head_path=Path(head_path)
        self.head=joblib.load(self.head_path)
        if self.head.get('config')!=CONFIG: raise ValueError('Classifier preprocessing mismatch')
        self.encoder=R3DEncoder(weights,device)
        if self.head['encoder_sha256']!=self.encoder.sha256: raise ValueError('Encoder mismatch')
        self.head_sha256=hashlib.sha256(self.head_path.read_bytes()).hexdigest()

    def predict(self,source,output):
        # No annotation lookup occurs here; evidence is selected solely by model scores.
        times,features=self.encoder.encode(source)
        probabilities=scores(self.head,features)
        peak=int(np.argmax(probabilities));threshold=self.head['threshold']
        output=Path(output);output.mkdir(parents=True,exist_ok=True)
        target=float(times[peak])
        from validate_open_jury import reference_frame
        actual=reference_frame(Path(source),target,output/'binary_peak.jpg')
        result=dict(task='Experimental source binary video-label classification',
            verdict='violation' if probabilities[peak]>=threshold else 'no_violation',
            score=float(probabilities[peak]),threshold=threshold,timecode_sec=actual,
            model_sha256=self.head_sha256,encoder_sha256=self.encoder.sha256,
            evidence_frames=[dict(timestamp_sec=actual,image_file='binary_peak.jpg')],
            event_type=None,reason=None,rule=None,
            grounding_status='unavailable_in_source_annotations',
            case_ready=False,
            note='A binary prediction and model-selected frame; no verified action type or normative cause',
            window_scores=[dict(timestamp_sec=float(t),score=float(p)) for t,p in zip(times,probabilities)])
        (output/'binary_assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
