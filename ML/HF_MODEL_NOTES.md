# Hugging Face model for annotation assistance

The selected optional annotator aid is [`microsoft/xclip-base-patch32-16-frames`](https://huggingface.co/microsoft/xclip-base-patch32-16-frames), pinned to revision `663a1e6d4b3600f9604b7b1c140bc1cf4a97d2a7` (MIT). It compares a short 16-frame video window with text descriptions. It was trained for general Kinetics-400 video recognition, not cash operations or banking rules. Similarity scores are uncalibrated ranking hints, not probabilities, labels, or evidence of a violation. Only the training split receives proposals; validation and test remain untouched.

The proposal script scores visible actions that may help locate relevant windows. For rules based on *absence* of an action, complete transaction visibility and human review remain essential. It does not propose hand oscillation: temporal sampling at 16 frames per clip is not adequate for that fine motion.

Weights are stored under ignored local `ML/cache/` and loaded in offline mode with `use_safetensors=True`. No case video is uploaded to Hugging Face. Compatible local Python packages are pinned in `requirements-hf-review.txt`.

After the snapshot contains `model.safetensors`, generate train-only proposals with:

```powershell
ML/.venv/Scripts/python.exe ML/propose_xclip_windows.py --model-dir ML/cache/huggingface_retry/models--microsoft--xclip-base-patch32-16-frames/snapshots/663a1e6d4b3600f9604b7b1c140bc1cf4a97d2a7
```

The full-frame run writes ignored `ML/annotations/action_review/xclip_train_proposals.json`. The ROI run writes `xclip_train_proposals_counter_roi.json`:

```powershell
ML/.venv/Scripts/python.exe ML/propose_xclip_windows.py --model-dir ML/cache/huggingface_retry/models--microsoft--xclip-base-patch32-16-frames/snapshots/663a1e6d4b3600f9604b7b1c140bc1cf4a97d2a7 --roi 0 300 464 610 --output ML/annotations/action_review/xclip_train_proposals_counter_roi.json
```

Either file can be loaded in `annotation_review.html`, but the pilot ranked the same scene across different prompts, so treat the windows as generic browsing aids only. Details: `HF_XCLIP_RESULTS.md`.
