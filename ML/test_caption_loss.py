"""Optional MLX tests: assistant-only loss must ignore prompt/image token errors."""
import importlib.util
import unittest
from types import SimpleNamespace


@unittest.skipUnless(importlib.util.find_spec('mlx'), 'Run in ML/.venv-review on Apple Silicon')
class CaptionLossTests(unittest.TestCase):
    def test_prompt_errors_do_not_affect_completion_loss(self):
        import mlx.core as mx
        from train_caption_lora import caption_loss
        ids=mx.array([[1,2,3,4,5,6,2,3]])
        batch=dict(input_ids=ids,pixel_values=mx.zeros((1,1)),attention_mask=mx.ones_like(ids),completion_start=6)
        class FakeModel:
            def __init__(self,bad_response=False):self.bad_response=bad_response
            def __call__(self,*args,**kwargs):
                logits=mx.zeros((1,7,8))
                # Every prompt prediction is deliberately wrong, with high certainty.
                logits=logits.at[0,:5,0].add(12.)
                logits=logits.at[0,5,0 if self.bad_response else 2].add(12.)
                logits=logits.at[0,6,3].add(12.)
                return SimpleNamespace(logits=logits)
        good=float(caption_loss(FakeModel(),batch))
        bad=float(caption_loss(FakeModel(True),batch))
        self.assertLess(good,.001)
        self.assertGreater(bad,5.)

    def test_response_length_mismatch_is_not_silently_padded(self):
        import mlx.core as mx
        from train_caption_lora import caption_loss
        batch=dict(input_ids=mx.array([[1,2,3,4]]),pixel_values=mx.zeros((1,1)),
            attention_mask=mx.ones((1,4)),completion_start=2)
        def bad_model(*args,**kwargs):return SimpleNamespace(logits=mx.zeros((1,2,8)))
        with self.assertRaises(ValueError):caption_loss(bad_model,batch)


if __name__=='__main__':unittest.main()
