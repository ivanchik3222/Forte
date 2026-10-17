"""Narrow compatibility fix for mlx-vlm 0.4.4's Qwen3-VL DeepStack path.

Upstream assigns `deepstack_visual_embeds = mx.eval(deepstack_image_embeds)`.
mlx.eval evaluates arrays and returns None, discarding all three auxiliary visual
levels. Preserve the evaluated arrays instead. No site-packages files are edited.
"""
import inspect
from types import MethodType

PATCH_VERSION='qwen3_vl_deepstack_v1'


def fixed_input_embeddings(self,input_ids=None,pixel_values=None,**kwargs):
    import mlx.core as mx
    from mlx_vlm.models.base import InputEmbeddingsFeatures
    image_grid=kwargs.get('image_grid_thw');video_grid=kwargs.get('video_grid_thw')
    grid=image_grid if image_grid is not None else video_grid
    if pixel_values is None:
        self.language_model._position_ids=None;self.language_model._rope_deltas=None
        return InputEmbeddingsFeatures(inputs_embeds=self.language_model.model.embed_tokens(input_ids))
    pixel_values=pixel_values.astype(self.vision_tower.patch_embed.proj.weight.dtype)
    inputs=self.language_model.model.embed_tokens(input_ids)
    cached=kwargs.get('cached_image_features')
    if cached is not None:hidden,deepstack=cached,None
    else:hidden,deepstack=self.vision_tower(pixel_values,grid)
    inputs,image_mask=self.merge_input_ids_with_image_features(hidden,inputs,input_ids,
        self.config.image_token_index,self.config.video_token_index)
    if deepstack is not None:mx.eval(deepstack)
    if image_grid is not None or video_grid is not None:
        positions,deltas=self.language_model.get_rope_index(input_ids,image_grid,video_grid,kwargs.get('mask'))
        self.language_model._position_ids=positions;self.language_model._rope_deltas=deltas
    return InputEmbeddingsFeatures(inputs_embeds=inputs,visual_pos_masks=image_mask[...,0],
        deepstack_visual_embeds=deepstack)


def install_deepstack_fix(model):
    if getattr(model,'_forte_deepstack_fix',None):return PATCH_VERSION
    if model.config.model_type!='qwen3_vl':raise ValueError('DeepStack compatibility fix only applies to Qwen3-VL')
    original=inspect.getsource(type(model).get_input_embeddings)
    if 'deepstack_visual_embeds = mx.eval(deepstack_image_embeds)' not in original:
        raise RuntimeError('Qwen3-VL runtime changed; review whether the compatibility fix is still required')
    model.get_input_embeddings=MethodType(fixed_input_embeddings,model)
    model._forte_deepstack_fix=PATCH_VERSION
    return PATCH_VERSION
