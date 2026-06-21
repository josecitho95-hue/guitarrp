"""Compatibilidad para correr modelos MT3 (mt3-infer) sobre el stack 2026.

El código T5 vendorizado en mt3-infer (escrito ~2024) usa métodos de
`transformers.ModuleUtilsMixin` que transformers 5.x removió o cambió de firma.
Aquí se restauran con sus implementaciones clásicas (idempotente). Llamar a
`apply()` antes de `mt3_infer.load_model()`.

Esto evita depender de parches dentro del venv (no reproducibles).
"""
from __future__ import annotations

import sys
import types

_applied = False


def apply() -> None:
    global _applied
    if _applied:
        return
    import torch

    # 1) stdout/stderr en UTF-8 (mt3-infer imprime caracteres unicode; Windows usa cp1252)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    # 2) shim de transformers.utils.model_parallel_utils (removido en 5.x)
    if "transformers.utils.model_parallel_utils" not in sys.modules:
        mod = types.ModuleType("transformers.utils.model_parallel_utils")

        def get_device_map(n_layers, devices):
            from math import ceil
            layers = list(range(n_layers))
            n_blocks = int(ceil(n_layers / len(devices)))
            chunks = [layers[i:i + n_blocks] for i in range(0, n_layers, n_blocks)]
            return dict(zip(devices, chunks))

        def assert_device_map(device_map, num_blocks):
            return  # validación no crítica en inferencia

        mod.get_device_map = get_device_map
        mod.assert_device_map = assert_device_map
        sys.modules["transformers.utils.model_parallel_utils"] = mod

    # 3) métodos clásicos de ModuleUtilsMixin
    from transformers.modeling_utils import ModuleUtilsMixin as MUM

    _orig_ext = MUM.get_extended_attention_mask

    def get_extended_attention_mask(self, attention_mask, input_shape, device=None, dtype=None):
        # transformers 5.x quitó el parámetro posicional `device`; tolerarlo.
        if isinstance(device, torch.dtype):
            dtype, device = device, None
        if isinstance(device, torch.device):
            device = None
        if dtype is None:
            dtype = self.dtype
        return _orig_ext(self, attention_mask, input_shape, dtype=dtype)

    MUM.get_extended_attention_mask = get_extended_attention_mask

    def _convert_head_mask_to_5d(self, head_mask, num_hidden_layers):
        if head_mask.dim() == 1:
            head_mask = head_mask.unsqueeze(0).unsqueeze(0).unsqueeze(-1).unsqueeze(-1)
            head_mask = head_mask.expand(num_hidden_layers, -1, -1, -1, -1)
        elif head_mask.dim() == 2:
            head_mask = head_mask.unsqueeze(1).unsqueeze(-1).unsqueeze(-1)
        return head_mask.to(dtype=self.dtype)

    def get_head_mask(self, head_mask, num_hidden_layers, is_attention_chunked=False):
        if head_mask is not None:
            head_mask = self._convert_head_mask_to_5d(head_mask, num_hidden_layers)
            if is_attention_chunked is True:
                head_mask = head_mask.unsqueeze(-1)
        else:
            head_mask = [None] * num_hidden_layers
        return head_mask

    def invert_attention_mask(self, encoder_attention_mask):
        if encoder_attention_mask.dim() == 3:
            ext = encoder_attention_mask[:, None, :, :]
        else:
            ext = encoder_attention_mask[:, None, None, :]
        ext = ext.to(dtype=self.dtype)
        return (1.0 - ext) * torch.finfo(self.dtype).min

    for name, fn in [
        ("_convert_head_mask_to_5d", _convert_head_mask_to_5d),
        ("get_head_mask", get_head_mask),
        ("invert_attention_mask", invert_attention_mask),
    ]:
        if not hasattr(MUM, name):
            setattr(MUM, name, fn)

    # 4) generate con KV-cache. El generate vendorizado (t5.py:252) decodifica SIN
    #    cache: en cada paso reconcatena la secuencia y recorre el decoder sobre TODA
    #    la secuencia (O(L^2) por segmento). El adapter agrupa todos los segmentos del
    #    audio en un solo batch y corre hasta que el segmento más largo termina (o
    #    max_length=1024); en audio denso (metal) las secuencias saturan y el coste
    #    explota (~50x peor que tiempo real). El T5Stack del decoder SÍ soporta
    #    past_key_values/use_cache, solo que generate no los usaba. Aquí se reescribe
    #    para alimentar solo el último token y encadenar el cache (O(L^2) -> O(L)).
    #    Produce exactamente la misma secuencia de tokens (mismo argmax/EOS/pad).
    _patch_mt3_generate_kvcache(torch)

    _applied = True


def _set_decoder_layer_idx(model) -> None:
    """Los bloques del decoder se crean sin layer_idx (warning de transformers 5.x);
    sin él, el cache (EncoderDecoderCache, indexado por layer_idx) no funciona."""
    for i, block in enumerate(model.decoder.block):
        block.layer[0].SelfAttention.layer_idx = i
        block.layer[1].EncDecAttention.layer_idx = i


def _patch_mt3_generate_kvcache(torch) -> None:
    try:
        from mt3_infer.models.mr_mt3 import t5 as _t5
        from transformers.cache_utils import DynamicCache, EncoderDecoderCache
    except Exception:
        return  # mt3_infer/transformers no disponibles o estructura distinta: no romper

    cls = getattr(_t5, "T5ForConditionalGeneration", None)
    if cls is None or getattr(cls, "_kvcache_patched", False):
        return

    def generate(self, inputs, max_length=1024, output_hidden_states=False, **kwargs):
        # transformers 5.12 guarda el K/V dentro de un objeto Cache (mutado in-place)
        # y los bloques del decoder tienen has_relative_attention_bias=False -> la
        # posicion la aporta pos_emb sumado a los embeddings, asi que el cache es
        # exacto. Decodificamos llamando los bloques directamente (el T5Stack.forward
        # vendorizado indexa la tupla con la convencion vieja y rompe con use_cache).
        if not getattr(self, "_layer_idx_set", False):
            _set_decoder_layer_idx(self)
            self._layer_idx_set = True

        dec = self.decoder
        batch_size = inputs.shape[0]
        inputs_embeds = self.proj(inputs)
        encoder_outputs = self.encoder(inputs_embeds=inputs_embeds, return_dict=True)
        hidden_states = encoder_outputs[0]

        start_id = self.config.decoder_start_token_id
        generated = torch.ones((batch_size, 1), dtype=torch.long,
                               device=self.device) * start_id
        next_input = generated
        unfinished = torch.ones(batch_size, dtype=torch.long, device=self.device)
        cache = EncoderDecoderCache(DynamicCache(), DynamicCache())

        for step in range(max_length):
            tok_embeds = dec.embed_tokens(next_input)               # (B, 1, d)
            tok_embeds = tok_embeds + dec.pos_emb(seq=1, offset=step)
            h = dec.dropout(tok_embeds)
            position_bias = None
            enc_dec_position_bias = None
            for block in dec.block:
                out = block(
                    h,
                    attention_mask=None,                # 1 token causal: nada que enmascarar
                    position_bias=position_bias,
                    encoder_hidden_states=hidden_states,
                    encoder_attention_mask=None,        # audio sin padding: atiende todo
                    encoder_decoder_position_bias=enc_dec_position_bias,
                    past_key_values=cache,
                    use_cache=True,
                    output_attentions=False,
                )
                h = out[0]
                position_bias = out[1]                  # compartido entre capas
                enc_dec_position_bias = out[2]
            h = dec.final_layer_norm(h)
            h = dec.dropout(h)
            lm_logits = self.lm_head(h)

            next_tokens = torch.argmax(lm_logits[:, -1, :].unsqueeze(1), dim=-1)
            next_tokens = (next_tokens * unfinished.unsqueeze(-1)
                           + self.config.pad_token_id * (1 - unfinished.unsqueeze(-1)))
            eos_indices = torch.where(next_tokens == self.config.eos_token_id)[0]
            unfinished[eos_indices] = 0
            generated = torch.cat([generated, next_tokens], dim=-1)
            next_input = next_tokens
            if unfinished.max() == 0:
                break

        if output_hidden_states:
            return generated, hidden_states
        return generated

    cls.generate = generate
    cls._kvcache_patched = True
