"""Runtime settings for the voice loop.

Environment variables override the backends and model ids, so a Linux
rover computer can run the same command path as the Mac.
"""

import os
import sys

ON_MAC = sys.platform == "darwin"

SAMPLE_RATE = 16_000
FRAME_MS = 30

# Trailing silence required before an utterance is finalized.
# Chat and unfinished phrases still wait for this. A stable command does not.
ENDPOINT_SILENCE_S = 0.18
# How often a live partial transcript is attempted while speech continues.
PARTIAL_INTERVAL_S = 0.20
# Do not send a clip to Whisper until this much speech is in it.
PARTIAL_MIN_SPEECH_S = 0.16
# Words that could still grow into a different command wait for this pause.
EARLY_HOLD_SILENCE_S = 0.08
# Short commands such as "stop" and "give" are only a few loud frames.
MIN_SPEECH_S = 0.09
# Consecutive loud frames required before speech is accepted.
SPEECH_START_FRAMES = 3
# Noise floor multiplier. Higher is less sensitive.
SPEECH_THRESHOLD_MULTIPLIER = 4.0
# Absolute RMS floor so a silent calibration cannot open the gate on fan noise.
MIN_RMS_THRESHOLD = 0.012
MAX_UTTERANCE_S = 10.0

# Parser accepts a command at or above this score.
COMMAND_THRESHOLD = 0.82
# Below this score the utterance is conversation, not a failed command.
CHAT_THRESHOLD = 0.62

# MLX runs only on Apple Silicon. Linux uses faster-whisper for speech,
# transformers for chat, and espeak-ng for the voice.
ASR_BACKEND = os.environ.get("ROVER_ASR_BACKEND", "mlx" if ON_MAC else "faster-whisper")
_ASR_DEFAULTS = {"mlx": "mlx-community/whisper-base.en-mlx", "faster-whisper": "base.en"}
ASR_MODEL = os.environ.get("ROVER_ASR_MODEL", _ASR_DEFAULTS.get(ASR_BACKEND, ""))
LLM_BACKEND = os.environ.get("ROVER_LLM_BACKEND", "mlx" if ON_MAC else "transformers")
_LLM_DEFAULTS = {
    "mlx": "mlx-community/Qwen2.5-0.5B-Instruct-4bit",
    "transformers": "Qwen/Qwen2.5-0.5B-Instruct",
}
LLM_MODEL = os.environ.get("ROVER_LLM_MODEL", _LLM_DEFAULTS.get(LLM_BACKEND, ""))
TTS_BACKEND = os.environ.get("ROVER_TTS", "say" if ON_MAC else "espeak-ng")
LLM_MAX_TOKENS = 40

CLARIFY_SPEECH = (
    "I did not understand. You can say follow, stay, fetch, come, or give."
)
CHAT_FALLBACK = "I can follow, stay, fetch, come, or give."

QUIT_PHRASES = frozenset(
    {"quit", "exit", "goodbye", "good bye", "shut down", "stop listening"}
)
