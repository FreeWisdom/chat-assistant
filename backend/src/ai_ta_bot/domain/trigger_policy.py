"""Question trigger policies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HandRaiseTriggerPolicy:
    """Only accept messages that start with an explicit hand-raise marker."""

    markers: tuple[str, ...] = ("#举手", "＃举手")

    def extract(self, content: str) -> str | None:
        text = str(content or "").strip()
        for marker in self.markers:
            if not text.startswith(marker):
                continue
            question = text[len(marker):].strip()
            return question or None
        return None

    def matches(self, content: str) -> bool:
        return self.extract(content) is not None
