"""Match a command by meaning when the wording is not a known phrase.

Exemplars are short descriptions of each task. A local MiniLM embedding
compares the utterance with those meanings. This does not move the rover.
"""

import os

import numpy as np

from rover_voice.nlu.parser import Intent, ParseResult, normalize

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Ordinary speech sits near 0.5. A paraphrase has to be clearly closer
# than that, and clearly closer than the next command, before it fires.
_MIN_SIMILARITY = 0.63
# Two task meanings this close together are a clarification, not a guess.
_MIN_MARGIN = 0.10

_MEANINGS: dict[str, tuple[str, ...]] = {
    "FOLLOW": (
        "follow me",
        "walk with me",
        "come with me",
        "keep up with me",
        "tag along",
        "track me",
        "shadow me",
        "accompany me",
        "follow behind me",
        "trail behind me",
        "stick with me",
        "walk behind me",
        "keep following me",
        "by my side",
        "beside me",
    ),
    "STAY": (
        "stay",
        "stay where you are",
        "do not move",
        "dont move",
        "remain here",
        "hold still",
        "wait here",
        "hold position",
        "freeze",
        "wait until I come back",
        "stay put",
        "hang back",
        "stop there",
        "stop right there",
        "stand still",
        "do not go anywhere",
        "remain there",
        "sit down",
    ),
    "FETCH": (
        "fetch the hammer",
        "fetch the tool",
        "go get the tool",
        "pick up the rock pick hammer",
        "grab the hammer",
        "retrieve the hammer",
        "bring the tool over",
        "go grab the rock hammer",
        "collect the rock pick",
        "bring me the hammer",
        "retrieve the tool",
    ),
    "COME": (
        "come here",
        "come to me",
        "head over to me",
        "drive over to me",
        "get over here",
        "come closer",
        "approach me",
        "walk over to me",
        "make your way to me",
        "come on over here",
        "come over to where I am",
        "come on over to my position",
        "over here",
        "right over here",
        "this way",
        "head over here",
    ),
    "GIVE": (
        "drop the hammer",
        "put it down",
        "place it on the ground",
        "set the hammer down",
        "let go of the hammer",
        "release the tool",
        "leave it on the ground",
        "put the tool on the ground",
        "release the hammer",
        "drop that tool",
        "let go",
        "hand me the hammer",
        "put the tool down",
        "drop it",
    ),
    "NONE": (
        "hello",
        "hello there",
        "how are you",
        "what time is it",
        "thank you",
        "thanks",
        "give me a second",
        "nice weather today",
        "what can you do",
        "I am talking to someone else",
        "lets go",
        "down",
        "leave it",
        "get it",
        "bring it",
        "out",
        "set",
        "place",
        "follow the instructions",
    ),
}


class MeaningMatcher:
    """Map unseen wording onto Follow, Stay, Fetch, Come, or Give."""

    def __init__(self) -> None:
        labels: list[str] = []
        examples: list[str] = []
        for label, group in _MEANINGS.items():
            for example in group:
                labels.append(label)
                examples.append(normalize(example))
        self._labels = labels
        self._model = _load_model()
        self._bank = self._model.encode(
            examples, normalize_embeddings=True, show_progress_bar=False
        )

    def match(self, text: str) -> ParseResult | None:
        """Return a command or a clarification, or None when it is not a command."""
        normalized = normalize(text)
        if not normalized:
            return None
        vector = self._model.encode(
            [normalized], normalize_embeddings=True, show_progress_bar=False
        )[0]
        scores = self._best_scores(vector)
        ranked = sorted(
            ((label, score) for label, score in scores.items() if label != "NONE"),
            key=lambda item: item[1],
            reverse=True,
        )
        top_label, top_score = ranked[0]
        second_score = ranked[1][1]
        if top_score < _MIN_SIMILARITY or top_score < scores["NONE"]:
            return None
        intent = Intent[top_label]
        slots = {"object": "rock_pick_hammer"} if intent is Intent.FETCH else {}
        if top_score - second_score < _MIN_MARGIN:
            return ParseResult("clarify", intent, top_score, slots, "ambiguous_meaning")
        return ParseResult("command", intent, top_score, slots, "meaning")

    def _best_scores(self, vector: np.ndarray) -> dict[str, float]:
        similarities = self._bank @ vector
        best = {label: 0.0 for label in _MEANINGS}
        for label, score in zip(self._labels, similarities):
            best[label] = max(best[label], float(score))
        return best


_MODEL = None


def _load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    from sentence_transformers import SentenceTransformer

    # CPU avoids an MPS watermark crash in this torch build.
    _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
    return _MODEL
