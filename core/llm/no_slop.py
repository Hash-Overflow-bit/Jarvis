"""
core/llm/no_slop.py
===================
No-Slop Text Linter and Nopus Bounded Stop Hooks.
Intercepts LLM responses to strip abstract AI slop keywords
and halts execution if repetition loops or character limits are breached.
"""

import re
import logging

logger = logging.getLogger("no_slop")


class NoSlopLinter:
    """
    Governs text quality by removing overused AI filler words
    and acting as a bounded stop hook to prevent infinite repetition loops.
    """

    # Common AI filler keywords that bloat sentences
    SLOP_PATTERNS = [
        (re.compile(r"\bdelve\b", re.IGNORECASE), ""),
        (re.compile(r"\btestament\b", re.IGNORECASE), "proof"),
        (re.compile(r"\bnot only\b", re.IGNORECASE), ""),
        (re.compile(r"\bbut also\b", re.IGNORECASE), "and"),
        (re.compile(r"\bin summary\b,?", re.IGNORECASE), ""),
        (re.compile(r"\bmoreover\b,?", re.IGNORECASE), ""),
        (re.compile(r"\bfurthermore\b,?", re.IGNORECASE), ""),
        (re.compile(r"\btapestry\b", re.IGNORECASE), "complexity"),
        (re.compile(r"\bnexus\b", re.IGNORECASE), "connection"),
        (re.compile(r"\bbeacon\b", re.IGNORECASE), "guide"),
        (re.compile(r"\bin conclusion\b,?", re.IGNORECASE), ""),
        (re.compile(r"\bfirst and foremost\b,?", re.IGNORECASE), ""),
        (re.compile(r"\bdemystify\b", re.IGNORECASE), "explain"),
        (re.compile(r"\bcomprehensive\b", re.IGNORECASE), "full"),
    ]

    def __init__(self, max_chars: int = 4000, repeat_threshold: int = 3):
        self.max_chars = max_chars
        self.repeat_threshold = repeat_threshold

    def clean_slop(self, text: str) -> str:
        """Strips out AI slop patterns and replaces them with direct, simple terms."""
        cleaned = text
        for pattern, replacement in self.SLOP_PATTERNS:
            # Replace pattern, cleaning up extra double spaces or leading commas
            cleaned = pattern.sub(replacement, cleaned)

        # Clean up double spaces or loose commas left behind
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r",[ \t]*,", ",", cleaned)
        cleaned = re.sub(r"^[ \t]*,\s*", "", cleaned)
        return cleaned.strip()

    def detect_repetition(self, text: str) -> bool:
        """
        Detects if the LLM has entered an infinite repetition loop
        by checking for duplicate adjacent sentences or phrases.
        """
        # Split into sentences or lines
        sentences = [s.strip().lower() for s in re.split(r"[.!?\n]", text) if len(s.strip()) > 10]
        if not sentences:
            return False

        # Count consecutive identical sentences
        consecutive_count = 1
        for i in range(len(sentences) - 1):
            if sentences[i] == sentences[i + 1]:
                consecutive_count += 1
                if consecutive_count >= self.repeat_threshold:
                    return True
            else:
                consecutive_count = 1
        return False

    def lint(self, text: str, bypass_length_limit: bool = False) -> str:
        """
        Runs the full linter on LLM output.
        Cleans slop, checks bounds, and truncates if repetition is detected.
        """
        if not text:
            return ""

        # 1. Bounded stop hook: Truncate if extreme length (prevent resource hogging)
        if not bypass_length_limit and len(text) > self.max_chars:
            logger.warning(f"Response length {len(text)} exceeds limit {self.max_chars}. Truncating.")
            text = text[: self.max_chars] + "\n[Truncated due to length bounds]"

        # 2. Bounded stop hook: Repetition check
        if self.detect_repetition(text):
            logger.warning("Infinite repetition loop detected. Truncating response.")
            # Find where the repetition starts and truncate there
            sentences = re.split(r"([.!?\n])", text)
            clean_sents = []
            seen = set()
            for s in sentences:
                s_lower = s.strip().lower()
                if len(s_lower) > 10:
                    if s_lower in seen:
                        # Repetition started, break here
                        clean_sents.append("... [Execution halted: repetition detected]")
                        break
                    seen.add(s_lower)
                clean_sents.append(s)
            text = "".join(clean_sents)

        # 3. Clean AI slop words
        return self.clean_slop(text)


# Singleton linter instance
no_slop_linter = NoSlopLinter()
