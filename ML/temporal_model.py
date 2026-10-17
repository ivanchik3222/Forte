"""Local temporal candidate model. Binary point labels do not define legal offences."""
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from torchvision.models.video import r3d_18

ROOT = Path(__file__).resolve().parent
WEIGHTS = ROOT / 'models/r3d_18-b3b3357e.pth'
WEIGHTS_SHA256 = 'b3b3357ead25631ec9c57362ff2128a92d0427e01e2cd184951a44380c3f2e9d'
CONFIG = dict(version=1, backbone='r3d_18_kinetics400_v1', sample_fps=4.,
              clip_frames=16, stride_sec=1., image_size=112,
              camera_profile='forte_open', roi_xyxy=[0, 300, 464, 661],
              resize='aspect_preserving_letterbox', point_radius_sec=1.,
              threshold=.5, logistic_c=.01)
MEAN = np.asarray([.43216, .394666, .37645], dtype=np.float32)
STD = np.asarray([.22803, .22145, .216989], dtype=np.float32)


def device_name(requested='auto'):
    if requested != 'auto':
        return requested
    if torch.cuda.is_available():
        return 'cuda'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


def load_encoder(device='auto', weights=WEIGHTS):
    weights = Path(weights)
    if not weights.is_file():
        raise FileNotFoundError('Run download_models.py --r3d first; inference never downloads weights.')
    if hashlib.sha256(weights.read_bytes()).hexdigest() != WEIGHTS_SHA256:
        raise ValueError('Unexpected R3D18 weight checksum')
    torch.set_num_threads(4)
    model = r3d_18(weights=None)
    model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True))
    model.fc = torch.nn.Identity()
    device = device_name(device)
    return model.eval().to(device), device


def letterbox(rgb, size):
    h, w = rgb.shape[:2]
    scale = size / max(h, w)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.empty((size, size, 3), dtype=np.uint8)
    canvas[:] = np.rint(MEAN * 255).astype(np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas


def decode_video(path, config, timeout=300.):
    """Decode sequentially using actual PTS; retain only small, sampled RGB frames."""
    import av
    started = time.monotonic()
    frames, times = [], []
    shape = None
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError('File has no video stream')
        stream = container.streams.video[0]
        origin = float(stream.start_time * stream.time_base) if stream.start_time is not None else None
        next_sample, previous = 0., -float('inf')
        for frame in container.decode(stream):
            if time.monotonic() - started > timeout:
                raise TimeoutError('Video decoding exceeded time limit')
            if frame.time is None:
                raise ValueError('Video frame has no PTS')
            if origin is None:
                origin = float(frame.time)
            sec = float(frame.time) - origin
            if sec < -1e-5 or sec <= previous:
                raise ValueError('Non-increasing or negative video PTS')
            previous = sec
            if sec + 1e-6 < next_sample:
                continue
            rgb = frame.to_ndarray(format='rgb24')
            h, w = rgb.shape[:2]
            if shape is not None and shape != (w, h):
                raise ValueError('Video dimensions changed during decoding')
            shape = (w, h)
            if config['camera_profile'] == 'forte_open':
                if shape != (464, 848):
                    raise ValueError('forte_open needs 464 x 848 video; another camera requires a validated ROI/model')
                x1, y1, x2, y2 = config['roi_xyxy']
                if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
                    raise ValueError('ROI is outside the video')
                rgb = rgb[y1:y2, x1:x2]
            elif config['camera_profile'] != 'full_frame':
                raise ValueError('Unknown camera profile')
            frames.append(letterbox(rgb, config['image_size']))
            times.append(sec)
            next_sample = (int(sec * config['sample_fps'] + 1e-6) + 1) / config['sample_fps']
    if not frames:
        raise ValueError('Video has no decodable frames')
    return np.asarray(times, dtype=np.float64), np.stack(frames), previous


def nearest_indices(times, targets):
    right = np.searchsorted(times, targets).clip(0, len(times) - 1)
    left = np.maximum(right - 1, 0)
    return np.where(np.abs(times[left] - targets) <= np.abs(times[right] - targets), left, right)


def scan_centers(times, stride):
    """Same grid for training/evaluation/inference, independent of annotated points."""
    targets = np.arange(times[0], times[-1] + 1e-6, stride)
    indices = np.unique(np.r_[nearest_indices(times, targets), len(times) - 1])
    return times[indices]


def extract(path, encoder, device, config=CONFIG, batch_size=2, timeout=300.):
    started = time.monotonic()
    times, frames, duration = decode_video(path, config, timeout)
    centers = scan_centers(times, config['stride_sec'])
    # Symmetric context, repeated edge frames at boundaries. This is offline, not causal.
    offsets = (np.arange(config['clip_frames']) - (config['clip_frames'] - 1) / 2) / config['sample_fps']
    if config.get('augmentation'):
        if config['augmentation'] != 'mild_video_v1':
            raise ValueError('Unknown augmentation recipe')
        from video_training_augmentation import augment_frames, parameters
        params = parameters(hashlib.sha256(Path(path).read_bytes()).hexdigest())
        frames = augment_frames(frames, params)
        offsets = offsets * params['speed']
    features = []
    for start in range(0, len(centers), batch_size):
        if time.monotonic() - started > timeout:
            raise TimeoutError('Temporal feature extraction exceeded time limit')
        selected = nearest_indices(times, centers[start:start + batch_size, None] + offsets)
        clips = (frames[selected].astype(np.float32) / 255. - MEAN) / STD
        tensor = torch.from_numpy(clips.transpose(0, 4, 1, 2, 3).copy()).to(device)
        with torch.inference_mode():
            features.append(encoder(tensor).cpu().numpy())
    features = np.concatenate(features).astype(np.float32)
    if not np.isfinite(features).all():
        raise ValueError('Non-finite encoder features')
    return centers, features, float(duration)


def training_samples(records, cache, radius=1., return_groups=False):
    xs, ys, ws, groups = [], [], [], []
    for record in records:
        times, features = cache[record['sha256']]
        if record['label']:
            # Only windows around supplied points are positive. Unmarked positive
            # footage is UNKNOWN, not negative training material.
            distance = np.min(np.abs(times[:, None] - np.asarray(record['timestamps_sec'])[None, :]), axis=1)
            indices = np.flatnonzero(distance <= radius)
            if not len(indices):
                raise ValueError(f'No training window near annotation: {record["video_ids"]}')
        else:
            indices = np.arange(len(times))
        xs.append(features[indices])
        ys.extend([record['label']] * len(indices))
        ws.extend([1. / len(indices)] * len(indices))
        groups.extend([record['sha256']] * len(indices))
    x, y, weights = np.concatenate(xs), np.asarray(ys), np.asarray(ws)
    if set(y.tolist()) != {0, 1}:
        raise ValueError('Training requires both classes')
    for label in (0, 1):
        weights[y == label] /= weights[y == label].sum()
    # Fixed effective sample size, unaffected by frame duplication or clip length.
    weights *= len(records) / 2
    if return_groups:
        return x, y, weights, np.asarray(groups)
    return x, y, weights


def fit_head(records, cache, config=CONFIG):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    x, y, weights = training_samples(records, cache, config['point_radius_sec'])
    head = make_pipeline(StandardScaler(), LogisticRegression(
        C=config['logistic_c'], max_iter=2000, random_state=42, solver='lbfgs'))
    head.fit(x, y, standardscaler__sample_weight=weights,
             logisticregression__sample_weight=weights)
    return head


def export_head(head, path, metadata):
    """Plain numerical arrays + JSON, no executable pickle in inference artifacts."""
    scaler, classifier = head.steps[0][1], head.steps[1][1]
    np.savez_compressed(path, mean=scaler.mean_, scale=scaler.scale_,
                        coef=classifier.coef_[0], intercept=classifier.intercept_,
                        metadata=np.asarray(json.dumps(metadata, ensure_ascii=False)))


def load_head(path):
    with np.load(path, allow_pickle=False) as data:
        metadata = json.loads(str(data['metadata']))
        keys = ('projection_weight', 'projection_bias', 'output_weight', 'output_bias') if metadata.get('format_version') == 2 else ('mean', 'scale', 'coef', 'intercept')
        head = {key: data[key].copy() for key in keys}
    if metadata.get('format_version') not in (1, 2) or metadata.get('backbone_sha256') != WEIGHTS_SHA256:
        raise ValueError('Unsupported temporal model format/backbone')
    if metadata['format_version'] == 2:
        shapes = dict(projection_weight=(64, 512), projection_bias=(64,), output_weight=(64,), output_bias=(1,))
        if metadata.get('head_type') != 'mil_mlp64' or any(head[k].shape != v for k, v in shapes.items()):
            raise ValueError('Unsupported adapter dimensions/type')
        if any(not np.isfinite(v).all() for v in head.values()):
            raise ValueError('Non-finite adapter parameters')
        return head, metadata
    if any(head[key].shape != (512,) for key in ('mean', 'scale', 'coef')) or head['intercept'].shape != (1,):
        raise ValueError('Unexpected temporal head dimensions')
    if any(not np.isfinite(v).all() for v in head.values()) or np.any(head['scale'] <= 0):
        raise ValueError('Invalid temporal head parameters')
    return head, metadata


def score_head(head, features):
    from scipy.special import expit
    if 'projection_weight' in head:
        features = np.asarray(features, dtype=np.float32)
        x = features * (np.float32(np.sqrt(512.)) / np.maximum(np.linalg.norm(features, axis=1, keepdims=True), np.float32(1e-8)))
        hidden = np.maximum(x @ head['projection_weight'].T + head['projection_bias'], 0.)
        return expit(hidden @ head['output_weight'] + head['output_bias'][0])
    return expit(((features - head['mean']) / head['scale']) @ head['coef'] + head['intercept'][0])


def candidate_events(times, scores, threshold=.5, gap_sec=1.5):
    groups = []
    for index in np.flatnonzero(scores >= threshold):
        if not groups or times[index] - times[groups[-1][-1]] > gap_sec:
            groups.append([])
        groups[-1].append(int(index))
    events = []
    for group in groups:
        peak = max(group, key=lambda i: scores[i])
        events.append(dict(timecode_sec=float(times[peak]), start_sec=float(times[group[0]]),
                           end_sec=float(times[group[-1]]), score=float(scores[peak]),
                           type=None, rule_id=None, requires_review=True))
    return events


def scene_group(record):
    """Existing manually reviewed scene grouping from build_detection_dataset.py."""
    vid = record['video_ids'][0]
    for name, ids in (
        ('green_bag', {16, 17}), ('intrusion_pink', {30, 31, 32}),
        ('transactions_white', {34, 35, 37, 38, 39}), ('solo_white', {40, 43, 44, 45, 46}),
        ('entry_white', {33}), ('transactions_pink', {1, 2, 3, 4, 5, 18, 19})):
        if vid in ids:
            return name
    return 'solo_pink'
