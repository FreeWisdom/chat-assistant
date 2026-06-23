"""Question trigger policies."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class TriggerMatch:
    question: str
    trigger_type: str
    marker: str


@dataclass(frozen=True)
class HandRaiseTriggerPolicy:
    """Accept explicit hand raises and messages directed at the bot account."""

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

    def extract_persisted(self, content: str, marker: str) -> str | None:
        """Extract a question while preserving original content for UI locating."""
        text = str(content or "").strip()
        if marker in self.markers or marker == "#举手":
            return self.extract(text)
        if marker == "@机器人":
            match = re.match(
                r"^@\s*[^\s\u2005\u2009\u202f\u3000]+"
                r"[\s\u2005\u2009\u202f\u3000]+(.*)$",
                unicodedata.normalize("NFKC", text),
                flags=re.DOTALL,
            )
            if not match:
                return None
            question = match.group(1).strip()
            return self.extract(question) or question or None
        if marker == "引用机器人":
            return self.extract(text) or text or None
        return self.extract(text)

    def match_message(
        self,
        message,
        bot_names: tuple[str, ...] = (),
    ) -> TriggerMatch | None:
        content = str(getattr(message, "content", "") or "").strip()
        hand_raise = self.extract(content)
        if hand_raise:
            return TriggerMatch(
                question=hand_raise,
                trigger_type="hand_raise",
                marker="#举手",
            )

        normalized_names = tuple(
            name
            for name in (
                self._normalize_name(item)
                for item in bot_names
            )
            if name
        )
        if not normalized_names:
            return None

        mention_question = self._extract_mention(content, normalized_names)
        if mention_question:
            return TriggerMatch(
                question=mention_question,
                trigger_type="mention",
                marker="@机器人",
            )

        message_type = str(getattr(message, "type", "") or "").lower()
        quoted_name = self._normalize_name(
            getattr(message, "quote_nickname", "")
        )
        if (
            message_type == "quote"
            and quoted_name
            and quoted_name in normalized_names
        ):
            question = self.extract(content) or content
            question = question.strip()
            if question:
                return TriggerMatch(
                    question=question,
                    trigger_type="quote",
                    marker="引用机器人",
                )
        return None

    def _extract_mention(
        self,
        content: str,
        normalized_names: tuple[str, ...],
    ) -> str | None:
        text = unicodedata.normalize("NFKC", content).strip()
        for name in normalized_names:
            pattern = (
                r"^@\s*"
                + re.escape(name)
                + r"(?:[\s\u2005\u2009\u202f\u3000]+|$)"
            )
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            question = text[match.end():].strip()
            question = self.extract(question) or question
            return question or None
        return None

    @staticmethod
    def _normalize_name(value: str) -> str:
        return (
            unicodedata.normalize("NFKC", str(value or ""))
            .strip()
            .lstrip("@")
            .strip()
            .casefold()
        )
