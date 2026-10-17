# X-CLIP pilot for annotation assistance

Pinned model: [`microsoft/xclip-base-patch32-16-frames`](https://huggingface.co/microsoft/xclip-base-patch32-16-frames), revision `663a1e6d4b3600f9604b7b1c140bc1cf4a97d2a7`, MIT. The checkpoint uses 16 frames at 224×224 and general Kinetics-400 training; it is not trained on ForteBank transactions. [Hugging Face describes the output as video-text similarity](https://huggingface.co/docs/transformers/model_doc/xclip#xclipmodel), not a rule probability.

The local safetensors file is 786,431,156 bytes; SHA-256: `f67aa8bc3f994af8685621a7fcd571a7b2495accf43455a2ee1da5e7c7038939`. It loaded on the RTX 4050 and produced finite video-text scores for a 16-frame pilot clip.

Two train-only ranking runs processed the same 24 unique train videos and 265 overlapping 6-second windows (3-second stride):

| Run | Input |
| --- | --- |
| `xclip_train_proposals.json` | Full frame |
| `xclip_train_proposals_counter_roi.json` | Existing cash-counter ROI `[0,300,464,610]` |

The top-ranked windows overlapped across different prompts. In the ROI run, all six prompt rankings placed the same X-8 interval (32.033–38.033 sec) first. A spot-check shows the model is mostly ranking a familiar teller-at-counter scene; it does not distinguish the absence-based rule conditions such as “no receipt”, “no bag inspection”, or “no controller”. The crop raises raw scores generally but does not make them calibrated or event-specific. No accuracy/F1 is reported because this queue has no reviewed event labels.

Use these JSONs, if at all, to jump to generic counter interactions. Do not copy proposals into event labels. The rule-specific video model should be trained only after interval review in `annotation_review.html`; validation and test remain unscored here. X-CLIP is not used for hand oscillation because 16 samples per 6-second window miss the fine motion and the customer’s hand may not be visible.
