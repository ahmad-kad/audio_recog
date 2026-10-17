"""Speech recognition backends."""

from rover_voice.asr.base import ASRBackend
from rover_voice.config import ASR_BACKEND, ASR_MODEL
from rover_voice.errors import ModelLoadError


def create_asr(backend: str = ASR_BACKEND, model_id: str = "") -> ASRBackend:
    """The speech model for this platform: MLX on a Mac, faster-whisper on Linux."""
    # ROVER_ASR_MODEL names a model for the configured backend only.
    configured = ASR_MODEL if backend == ASR_BACKEND else ""
    if backend == "mlx":
        from rover_voice.asr.mlx_whisper import DEFAULT_MODEL, MlxWhisperASR

        return MlxWhisperASR(model_id or configured or DEFAULT_MODEL)
    if backend == "faster-whisper":
        from rover_voice.asr.faster_whisper import DEFAULT_MODEL as FW_MODEL
        from rover_voice.asr.faster_whisper import FasterWhisperASR

        return FasterWhisperASR(model_id or configured or FW_MODEL)
    raise ModelLoadError(
        f"Unknown speech backend {backend!r}. Use mlx or faster-whisper."
    )
