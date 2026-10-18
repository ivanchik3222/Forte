"""Fail the Linux image build if reviewed inference assets/imports are missing."""
import hashlib
import json
from pathlib import Path


def main():
    import av
    import cv2
    import scipy
    from reviewed_model import load_model
    from reviewed_pipeline import ReviewedPipeline
    from caption_worker import DeferredCaptionAnalyzer
    from rule_assessment import load_rules
    from temporal_model import load_encoder

    root = Path(__file__).resolve().parent
    bundle_path = root / 'deployment/reviewed/model_bundle.json'
    bundle = json.loads(bundle_path.read_text())
    candidate = bundle_path.parent / bundle['candidate']['file']
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == bundle['candidate']['sha256']
    load_model(candidate)
    backbone = root / 'models/r3d_18-b3b3357e.pth'
    assert hashlib.sha256(backbone.read_bytes()).hexdigest() == bundle['backbone_sha256']
    load_encoder('cpu', backbone)
    load_rules()
    assert not list((root / 'models').glob('*qwen*')), 'Qwen belongs on its separate server'
    print('Reviewed runtime verified: R3D backbone, bank head, rule registry and Python dependencies; no Qwen weights.')


if __name__ == '__main__':
    main()
