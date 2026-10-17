"""Small chat model for conversation that is not a rover command.

Qwen2.5 0.5B Instruct runs through MLX at 4-bit on a Mac, and through
transformers on Linux. Replies are capped to one short sentence so speech
stays quick. This module is not consulted when the command parser has
already accepted an intent.
"""

import time
from typing import Protocol

from rover_voice.config import CHAT_FALLBACK, LLM_BACKEND, LLM_MAX_TOKENS, LLM_MODEL
from rover_voice.errors import ModelLoadError

_SYSTEM = (
    "You are Rover, a small outdoor robot speaking aloud to a nearby person. "
    "Reply with one short sentence, twelve words or fewer. No markdown. "
    "You only chat. Never say that you are already moving or following. "
    "If asked what you can do, say: You can say follow, stay, fetch, come, or give. "
    "Current rover state: {state}."
)


class QuantizedChat:
    """Local quantized chat model used only for non-command speech."""

    def __init__(self, model_id: str = LLM_MODEL) -> None:
        self.model_id = model_id
        try:
            from mlx_lm import load
        except Exception as exc:
            raise ModelLoadError(
                "mlx-lm is not installed. Re-run scripts/setup.sh."
            ) from exc
        try:
            self._model, self._tokenizer = load(model_id)
        except Exception as exc:
            raise ModelLoadError(f"Could not load chat model {model_id}: {exc}") from exc
        self.last_ms = 0.0
        self._sampler = self._make_sampler()
        # Compile the Metal kernels before the first live reply.
        self.reply("Say ready.", "idle, not holding the hammer", [])

    def reply(self, user_text: str, state_line: str, history: list[dict[str, str]]) -> str:
        started = time.perf_counter()
        messages = [
            {"role": "system", "content": _SYSTEM.format(state=state_line)},
            *history[-6:],
            {"role": "user", "content": user_text},
        ]
        prompt = self._tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=False,
        )
        from mlx_lm import generate

        raw = generate(
            self._model,
            self._tokenizer,
            prompt=prompt,
            max_tokens=LLM_MAX_TOKENS,
            sampler=self._sampler,
            verbose=False,
        )
        speech = _first_sentence(raw)
        if not speech:
            speech = CHAT_FALLBACK
        self.last_ms = (time.perf_counter() - started) * 1000
        return speech

    def _make_sampler(self):
        from mlx_lm.sample_utils import make_sampler

        # Argmax is the fastest stable setting for one-sentence replies.
        return make_sampler(temp=0.0)


class TransformersChat:
    """The same model through transformers, on CUDA when available, else CPU."""

    def __init__(self, model_id: str = LLM_MODEL) -> None:
        self.model_id = model_id
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except Exception as exc:
            raise ModelLoadError(
                "transformers is not installed. Re-run scripts/setup.sh."
            ) from exc
        self._torch = torch
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(model_id)
            self._model = AutoModelForCausalLM.from_pretrained(
                model_id,
                dtype=torch.float16 if self._device == "cuda" else torch.float32,
            ).to(self._device)
        except Exception as exc:
            raise ModelLoadError(f"Could not load chat model {model_id}: {exc}") from exc
        self._model.eval()
        self.last_ms = 0.0
        self.reply("Say ready.", "idle, not holding the hammer", [])

    def reply(self, user_text: str, state_line: str, history: list[dict[str, str]]) -> str:
        started = time.perf_counter()
        messages = [
            {"role": "system", "content": _SYSTEM.format(state=state_line)},
            *history[-6:],
            {"role": "user", "content": user_text},
        ]
        prompt = self._tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._device)
        with self._torch.inference_mode():
            output = self._model.generate(
                **inputs,
                max_new_tokens=LLM_MAX_TOKENS,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        new_tokens = output[0][inputs["input_ids"].shape[1] :]
        raw = self._tokenizer.decode(new_tokens, skip_special_tokens=True)
        speech = _first_sentence(raw) or CHAT_FALLBACK
        self.last_ms = (time.perf_counter() - started) * 1000
        return speech


class ChatModel(Protocol):
    model_id: str
    last_ms: float

    def reply(self, user_text: str, state_line: str, history: list[dict[str, str]]) -> str: ...


def create_chat(backend: str = LLM_BACKEND) -> ChatModel:
    """MLX on a Mac, transformers on Linux. Raises ModelLoadError."""
    if backend == "mlx":
        return QuantizedChat()
    if backend == "transformers":
        return TransformersChat()
    raise ModelLoadError(f"Unknown chat backend {backend!r}. Use mlx or transformers.")


def _first_sentence(text: str) -> str:
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    line = line.replace("*", "").strip("\"' ")
    if not line:
        return ""
    for mark in (".", "!", "?"):
        index = line.find(mark)
        if 0 <= index <= 180:
            return line[: index + 1].strip()
    return line[:180].strip()
