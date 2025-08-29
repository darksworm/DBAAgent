from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional
import os
import re


@dataclass
class ClassifyResult:
    score: float
    reason: Optional[str] = None


class Classifier:
    def score(self, text: str, image: Optional[bytes] = None) -> ClassifyResult:
        raise NotImplementedError


class StubClassifier(Classifier):
    """Heuristic classifier for offline/dev use.

    - Scores higher when include-like keywords appear in the text.
    - Penalizes when common exclude words are present.
    """

    def __init__(self, include: Iterable[str] | None = None, exclude: Iterable[str] | None = None) -> None:
        self.include = [w.lower() for w in (include or []) if w]
        self.exclude = [w.lower() for w in (exclude or []) if w]

    def score(self, text: str, image: Optional[bytes] = None) -> ClassifyResult:
        t = (text or "").lower()
        pos = sum(2.0 for w in self.include if re.search(r"\b" + re.escape(w) + r"\b", t))
        neg = sum(1.5 for w in self.exclude if re.search(r"\b" + re.escape(w) + r"\b", t))
        raw = max(0.0, min(1.0, 0.1 + 0.2 * pos - 0.15 * neg))
        return ClassifyResult(score=raw, reason=None)


def get_classifier(include: Iterable[str] | None = None, exclude: Iterable[str] | None = None) -> Classifier:
    # In the future, select provider based on env (e.g., OPENAI_API_KEY)
    if os.environ.get("LLM_PROVIDER"):
        # Placeholder: return stub until a provider is implemented
        pass
    return StubClassifier(include=include, exclude=exclude)

