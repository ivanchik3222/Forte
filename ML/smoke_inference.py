"""Offline real-weight smoke test using a synthetic video; suitable for CI."""
import hashlib
from pathlib import Path
import tempfile

import av
import numpy as np
from inference import Detector


def main():
    weights = Path(__file__).resolve().parent/'deployment/cash_detector.pt'
    assert hashlib.sha256(weights.read_bytes()).hexdigest() == 'be1ff4056ffd36fea226fca6c0beb3cbd5f84bfc2bff34a673934e406ba2ec4f'
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory)/'synthetic.mp4'
        with av.open(str(source), 'w') as output:
            stream = output.add_stream('libx264', rate=4)
            stream.width, stream.height, stream.pix_fmt = 64, 64, 'yuv420p'
            for i in range(8):
                rgb = np.full((64,64,3), 40+i, dtype=np.uint8)
                frame = av.VideoFrame.from_ndarray(rgb, format='rgb24')
                for packet in stream.encode(frame): output.mux(packet)
            for packet in stream.encode(): output.mux(packet)
        report = Detector(weights, 'cpu').analyze(source, Path(directory)/'out', 'full_frame')
        assert report['processed_frames'] == 4
        assert [r['timestamp_sec'] for r in report['frames']] == [0., .5, 1., 1.5]
        assert report['verdict'] == 'requires_review' and report['violations'] == []
        assert report['rule_evaluation'] == 'not_performed' and report['evidence_frames']
        print('Real-weight CPU inference, video PTS and evidence export: OK', flush=True)


if __name__ == '__main__': main()
