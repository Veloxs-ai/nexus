from nexus_guardrails.normalization import luhn_valid, normalize_text


def test_normalize_text_strips_zero_width():
    text = "ig​nore previous"
    assert normalize_text(text) == "ignore previous"


def test_normalize_text_strips_bidi_control():
    text = "abc‮def"
    assert normalize_text(text) == "abcdef"


def test_normalize_text_folds_fullwidth_to_ascii():
    fullwidth_a = "ＡＢＣ"
    assert normalize_text(fullwidth_a) == "ABC"


def test_normalize_text_handles_empty_string():
    assert normalize_text("") == ""


def test_luhn_valid_known_test_cards():
    assert luhn_valid("4111 1111 1111 1111") is True
    assert luhn_valid("5500-0000-0000-0004") is True
    assert luhn_valid("340000000000009") is True


def test_luhn_valid_rejects_random_digits():
    assert luhn_valid("4111 1111 1111 1112") is False
    assert luhn_valid("1234567890123") is False


def test_luhn_valid_rejects_too_short():
    assert luhn_valid("4111") is False
