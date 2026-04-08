from __future__ import annotations

from memorylens._audit.splitter import split_sentences


class TestSplitSentences:
    def test_basic_split(self):
        text = "First sentence. Second sentence. Third sentence."
        result = split_sentences(text)
        assert result == ["First sentence.", "Second sentence.", "Third sentence."]

    def test_question_and_exclamation(self):
        text = "Is this a question? Yes it is! Great."
        result = split_sentences(text)
        assert result == ["Is this a question?", "Yes it is!", "Great."]

    def test_preserves_abbreviations(self):
        text = "Dr. Smith went to Washington. He arrived at 3 p.m. today."
        result = split_sentences(text)
        assert len(result) == 2

    def test_single_sentence(self):
        text = "Just one sentence."
        result = split_sentences(text)
        assert result == ["Just one sentence."]

    def test_no_trailing_period(self):
        text = "First sentence. Second without period"
        result = split_sentences(text)
        assert result == ["First sentence.", "Second without period"]

    def test_empty_string(self):
        result = split_sentences("")
        assert result == []

    def test_whitespace_only(self):
        result = split_sentences("   ")
        assert result == []

    def test_newlines(self):
        text = "First sentence.\nSecond sentence.\nThird."
        result = split_sentences(text)
        assert result == ["First sentence.", "Second sentence.", "Third."]

    def test_multiple_spaces(self):
        text = "First sentence.   Second sentence."
        result = split_sentences(text)
        assert result == ["First sentence.", "Second sentence."]
