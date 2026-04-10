from __future__ import annotations

import re

# Common abbreviations that shouldn't trigger sentence splits
_ABBREVS = {
    "dr",
    "mr",
    "mrs",
    "ms",
    "prof",
    "sr",
    "jr",
    "st",
    "ave",
    "vs",
    "etc",
    "i.e",
    "e.g",
    "a.m",
    "p.m",
}

_SENTENCE_END = re.compile(r"([.!?])(?:\s+|$)")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences.

    Splits on sentence-ending punctuation (.!?) followed by whitespace or end-of-string.
    Handles common abbreviations like Dr., Mr., a.m., p.m.
    """
    if not text or not text.strip():
        return []

    sentences: list[str] = []
    current = ""

    for i, char in enumerate(text):
        current += char
        if char in ".!?":
            # Check if this is end of sentence
            is_end = False
            # End of string
            if i == len(text) - 1:
                is_end = True
            # Followed by whitespace
            elif i + 1 < len(text) and text[i + 1] in " \n\r\t":
                # Check it's not an abbreviation
                word_before = (
                    current.rstrip(".!?").rsplit(None, 1)[-1].lower()
                    if current.rstrip(".!?").strip()
                    else ""
                )
                if word_before not in _ABBREVS:
                    is_end = True

            if is_end:
                stripped = current.strip()
                if stripped:
                    sentences.append(stripped)
                current = ""
        elif char in " \n\r\t" and not current.strip():
            current = ""

    # Handle remaining text without terminal punctuation
    remaining = current.strip()
    if remaining:
        sentences.append(remaining)

    return sentences
