"""Regression for auxiliary visual features being discarded by mlx.eval()."""
import importlib.util
import unittest
from types import SimpleNamespace


@unittest.skipUnless(importlib.util.find_spec('mlx'), 'Requires the local MLX environment')
class DeepStackRegressionTests(unittest.TestCase):
    def test_all_auxiliary_visual_levels_reach_language_model(self):
        import mlx.core as mx
        from qwen_mlx_compat import fixed_input_embeddings
        levels=[mx.full((2,3),i+1.) for i in range(3)]
        class Vision:
            patch_embed=SimpleNamespace(proj=SimpleNamespace(weight=mx.zeros((1,))))
            def __call__(self,*args):return mx.zeros((2,3)),levels
        model=SimpleNamespace(vision_tower=Vision(),
            language_model=SimpleNamespace(model=SimpleNamespace(embed_tokens=lambda ids:mx.zeros((1,2,3))),
                get_rope_index=lambda *args:(mx.array([0]),mx.array([0]))),
            config=SimpleNamespace(image_token_index=1,video_token_index=2),
            merge_input_ids_with_image_features=lambda *args:(mx.zeros((1,2,3)),mx.ones((1,2,3),dtype=mx.bool_)))
        result=fixed_input_embeddings(model,mx.array([[1,1]]),mx.zeros((2,3)),image_grid_thw=mx.array([[1,1,2]]))
        self.assertIsNotNone(result.deepstack_visual_embeds)
        self.assertEqual(len(result.deepstack_visual_embeds),3)
        self.assertEqual([float(x.mean()) for x in result.deepstack_visual_embeds],[1.,2.,3.])
        self.assertEqual(result.visual_pos_masks.shape,(1,2))


if __name__=='__main__':unittest.main()
