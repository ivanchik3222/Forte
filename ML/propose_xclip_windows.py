"""Rank train-split clips by visible-action similarity for human review only."""

import argparse
import json
from pathlib import Path

import av
import numpy as np
import torch
# Transformers 5.10 imports an optional FP8 integration even for X-CLIP.
# Project PyTorch 2.6 has no e8m0 dtype; X-CLIP inference here runs in FP32
# and never uses this optional FP8 path.
if not hasattr(torch, "float8_e8m0fnu") and hasattr(torch, "float8_e4m3fn"):
    torch.float8_e8m0fnu = torch.float8_e4m3fn
from transformers import AutoModel, AutoProcessor


ROOT = Path(__file__).resolve().parent
REPO_ID = "microsoft/xclip-base-patch32-16-frames"
REVISION = "663a1e6d4b3600f9604b7b1c140bc1cf4a97d2a7"
PROMPTS = {
    "cash_count_without_customer": "A bank employee counts or sorts banknotes at a service counter.",
    "previous_cash_left_on_desk": "Banknotes remain on a service counter while another customer approaches.",
    "cash_handover_without_visible_receipt": "A bank employee hands a paper receipt or document to a customer across a counter.",
    "collection_bag_not_visibly_checked": "A bank employee examines a cash collection bag and its seal at a counter.",
    "counting_without_controller": "One bank employee counts, sorts, or bundles banknotes while another employee supervises.",
    "identity_document_presentation": "A customer presents an identity document or a phone to a cashier at a counter.",
}


def sample_frames(path, start_sec, end_sec, count, crop_xyxy=None):
    targets = np.linspace(start_sec, max(start_sec, end_sec - 1e-3), count)
    frames = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        seek_at = max(0.0, start_sec - 0.5)
        container.seek(int(seek_at / float(stream.time_base)), stream=stream, backward=True, any_frame=False)
        target_index = 0
        last = None
        for frame in container.decode(stream):
            timestamp = float(frame.time) if frame.time is not None else None
            if timestamp is None:
                continue
            last = frame.to_ndarray(format="rgb24")
            if crop_xyxy is not None:
                x1, y1, x2, y2 = crop_xyxy
                height, width = last.shape[:2]
                x1, x2 = max(0, x1), min(width, x2)
                y1, y2 = max(0, y1), min(height, y2)
                if x2 <= x1 or y2 <= y1:
                    raise ValueError(f"ROI {crop_xyxy} is outside video frame {width}x{height}: {path}")
                last = last[y1:y2, x1:x2]
            while target_index < count and timestamp >= targets[target_index]:
                frames.append(last)
                target_index += 1
            if timestamp > end_sec + 0.2 or target_index == count:
                break
        if not frames:
            raise RuntimeError(f"No decodable frames in {path} at {start_sec:.2f}s")
        while len(frames) < count:
            frames.append(frames[-1] if last is None else last)
    return np.stack(frames)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=ROOT / "annotations/action_review/rule_review_tasks.json")
    parser.add_argument("--model-dir", type=Path, required=True, help="Local snapshot directory; no network loading is used.")
    parser.add_argument("--videos-dir", type=Path, default=ROOT / "open/open/videos")
    parser.add_argument("--output", type=Path, default=ROOT / "annotations/action_review/xclip_train_proposals.json")
    parser.add_argument("--window-sec", type=float, default=6.0)
    parser.add_argument("--stride-sec", type=float, default=3.0)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--roi", nargs=4, type=int, default=None, metavar=("X1", "Y1", "X2", "Y2"),
                        help="Optional pixel crop [x1,y1,x2,y2], e.g. the documented cash-counter ROI.")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Will not overwrite existing proposal file: {args.output}")
    if not (args.model_dir / "model.safetensors").exists():
        raise FileNotFoundError(f"Expected safetensors weights in {args.model_dir}")

    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    processor = AutoProcessor.from_pretrained(args.model_dir, local_files_only=True)
    model = AutoModel.from_pretrained(
        args.model_dir, local_files_only=True, use_safetensors=True, trust_remote_code=False
    ).to(device).eval()
    all_windows = []
    with torch.inference_mode():
        for task in tasks:
            if task["split"] != "train":
                continue
            path = args.videos_dir / task["source_file"]
            if not path.is_file():
                raise FileNotFoundError(path)
            duration = float(task["duration_sec"])
            if duration <= 0:
                continue
            starts = list(np.arange(0, max(duration - args.window_sec, 0) + 1e-6, args.stride_sec))
            if not starts or starts[-1] + args.window_sec < duration:
                starts.append(max(0.0, duration - args.window_sec))
            for start in sorted(set(round(float(value), 3) for value in starts)):
                end = min(duration, start + args.window_sec)
                frames = sample_frames(path, start, end, count=16, crop_xyxy=args.roi)
                inputs = processor(
                    text=list(PROMPTS.values()), videos=list(frames), return_tensors="pt", padding=True
                )
                inputs = {key: value.to(device) for key, value in inputs.items()}
                logits = model(**inputs).logits_per_video[0].float().cpu().numpy()
                all_windows.append({
                    "video_ids": task["video_ids"],
                    "source_sha256": task["source_sha256"],
                    "source_file": task["source_file"],
                    "split": task["split"],
                    "start_sec": start,
                    "end_sec": round(end, 3),
                    "scores": {rule_id: float(logits[index]) for index, rule_id in enumerate(PROMPTS)},
                })
            print(f"Scored train video IDs {task['video_ids']} ({len(starts)} windows)", flush=True)

    top = {}
    by_video = {}
    videos = {row["source_sha256"]: row for row in all_windows}
    for rule_id in PROMPTS:
        ranked = sorted(all_windows, key=lambda row: row["scores"][rule_id], reverse=True)[:args.top_k]
        top[rule_id] = [
            {**row, "model_proposal": True, "review_status": "unreviewed", "score_rank": rank}
            for rank, row in enumerate(ranked, start=1)
        ]
        for sha256 in videos:
            video_rows = [row for row in all_windows if row["source_sha256"] == sha256]
            ranked_video = sorted(video_rows, key=lambda row: row["scores"][rule_id], reverse=True)[:args.top_k]
            by_video.setdefault(sha256, {})[rule_id] = [
                {**row, "model_proposal": True, "review_status": "unreviewed", "score_rank": rank}
                for rank, row in enumerate(ranked_video, start=1)
            ]
    payload = {
        "model_id": REPO_ID,
        "revision": REVISION,
        "license": "MIT",
        "score_type": "raw video-text similarity logits; not probabilities",
        "purpose": "human review shortlist only; not ground truth or a rule decision",
        "training_split_only": True,
        "videos_scored": len({row["source_sha256"] for row in all_windows}),
        "windows_scored": len(all_windows),
        "frame_crop_xyxy": args.roi,
        "prompts": PROMPTS,
        "top_windows_by_observable_action": top,
        "top_windows_by_video_sha256": by_video,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"videos_scored": payload["videos_scored"], "windows_scored": payload["windows_scored"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
