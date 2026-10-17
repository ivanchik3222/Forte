"""Mild, deterministic training views. All frames share one photometric transform."""
import cv2
import numpy as np


def parameters(source_sha256):
    rng = np.random.default_rng(int(source_sha256[:16], 16) ^ 20261017)
    return dict(brightness=float(rng.uniform(.88, 1.12)), contrast=float(rng.uniform(.92, 1.08)),
                gamma=float(rng.uniform(.92, 1.08)), blur_sigma=.35 if rng.random() < .5 else 0.,
                speed=float(rng.uniform(.9, 1.1)))


def augment_frames(frames, params):
    # No crops, flips, erasing, frame reversal, jitter or invented objects.
    # LUT + fixed blur avoids independent-frame flicker and preserves geometry.
    values = (np.arange(256, dtype=np.float32) / 255.) ** params['gamma']
    values = ((values - .5) * params['contrast'] + .5) * params['brightness']
    lut = np.rint(np.clip(values * 255., 0, 255)).astype(np.uint8)
    result = lut[frames]
    if params['blur_sigma']:
        result = np.stack([cv2.GaussianBlur(f, (3, 3), params['blur_sigma']) for f in result])
    return result
