"""faster-whisper backend for Linux: CPU, or CUDA when it is available."""

import os

import numpy as np

from rover_voice.asr.base import prepare_audio, warmup_tone
from rover_voice.config import SAMPLE_RATE
from rover_voice.errors import ModelLoadError

DEFAULT_MODEL = "base.en"


class FasterWhisperASR:
    """English Whisper Base through CTranslate2.

    ROVER_ASR_DEVICE (auto, cpu, cuda) and ROVER_ASR_COMPUTE (default, int8,
    float16...) are passed to faster-whisper unchanged.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.device = device or os.environ.get("ROVER_ASR_DEVICE", "auto")
        self.compute_type = compute_type or os.environ.get("ROVER_ASR_COMPUTE", "default")
        self._model = None

    def warmup(self) -> None:
        self._load()
        try:
            self.transcribe(warmup_tone(), SAMPLE_RATE)
        except ModelLoadError:
            raise
        except Exception as exc:
            raise ModelLoadError(
                f"Could not load speech model {self.model_id}: {exc}"
            ) from exc

    def transcribe(self, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"Expected {SAMPLE_RATE} Hz audio, got {sample_rate}")
        samples = prepare_audio(audio)
        if samples.size == 0:
            return ""
        model = self._load()
        try:
            segments, _ = model.transcribe(
                samples,
                language="en",
                beam_size=1,
                temperature=0.0,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            # Segments are a generator; decoding happens while joining.
            text = " ".join(segment.text.strip() for segment in segments)
        except Exception as exc:
            raise ModelLoadError(f"Speech recognition failed: {exc}") from exc
        return text.strip()

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise ModelLoadError(
                "faster-whisper is not installed. Re-run scripts/setup.sh."
            ) from exc
        try:
            self._model = WhisperModel(
                self.model_id, device=self.device, compute_type=self.compute_type
            )
        except Exception as exc:
            raise ModelLoadError(
                f"Could not load speech model {self.model_id}: {exc}"
            ) from exc
        return self._model
