"""MLX Whisper backend for Apple Silicon."""

import numpy as np

from rover_voice.asr.base import prepare_audio, warmup_tone
from rover_voice.config import SAMPLE_RATE
from rover_voice.errors import ModelLoadError

DEFAULT_MODEL = "mlx-community/whisper-base.en-mlx"


class MlxWhisperASR:
    """English Whisper Base, running locally through MLX."""

    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self.model_id = model_id

    def warmup(self) -> None:
        # A real tone forces the model to download and compile.
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
        try:
            import mlx_whisper
        except Exception as exc:
            raise ModelLoadError(
                "mlx-whisper is not installed. Re-run scripts/setup.sh."
            ) from exc
        try:
            result = mlx_whisper.transcribe(
                samples,
                path_or_hf_repo=self.model_id,
                language="en",
                temperature=0.0,
                condition_on_previous_text=False,
                verbose=None,
            )
        except Exception as exc:
            raise ModelLoadError(f"Speech recognition failed: {exc}") from exc
        text = str(result.get("text", "")).strip()
        return text
