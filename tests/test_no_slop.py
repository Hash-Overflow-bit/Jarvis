"""
tests/test_no_slop.py
=====================
Unit tests for the NoSlopLinter and Nopus bounded stop hooks.
"""

from core.llm.no_slop import NoSlopLinter


def test_slop_word_cleanup():
    linter = NoSlopLinter()
    raw_text = "Delve into the code. Moreover, it is a testament to our nexus and beacon."
    expected = "into the code. it is a proof to our connection and guide."
    cleaned = linter.clean_slop(raw_text)
    assert cleaned.lower() == expected.lower()


def test_no_slop_linter_integration():
    linter = NoSlopLinter()
    raw_text = "In conclusion, we must delve into this tapestry. Furthermore, not only Python but also JS is crucial."
    # tapestry -> complexity, delve -> deleted, furthermore -> deleted, not only X but also Y -> X and Y
    cleaned = linter.lint(raw_text)
    assert "delve" not in cleaned.lower()
    assert "tapestry" not in cleaned.lower()
    assert "furthermore" not in cleaned.lower()
    assert "python and js" in cleaned.lower()


def test_repetition_detection_and_truncation():
    linter = NoSlopLinter(repeat_threshold=3)
    repetitive_text = (
        "This is a unique sentence one. This is a unique sentence one. "
        "This is a unique sentence one. This is a unique sentence one."
    )
    assert linter.detect_repetition(repetitive_text) is True

    # Check that linting halts execution on repetition
    cleaned = linter.lint(repetitive_text)
    assert "[Execution halted: repetition detected]" in cleaned


def test_length_bounding():
    linter = NoSlopLinter(max_chars=20)
    long_text = "This is a very long string that should be cut off."
    cleaned = linter.lint(long_text)
    assert "[Truncated due to length bounds]" in cleaned
    assert len(cleaned) <= 60  # text limit (20) + warning text length
