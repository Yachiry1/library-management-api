from app.core.normalization import (
    is_valid_isbn,
    normalize_author_name,
    normalize_isbn,
    normalize_title,
)


def test_author_normalization_uses_casefold_and_preserves_diacritics() -> None:
    first, last = normalize_author_name("  Straße   María  ", "  O'Neil  ")

    assert first == "strasse maría"
    assert last == "o'neil"
    assert len(first) > len("Straße maría".lower())


def test_title_and_isbn_normalization() -> None:
    assert normalize_title(" A   Wizard\tOf Earthsea ") == "a wizard of earthsea"
    assert normalize_isbn("978-0-547-77374-2") == "9780547773742"
    assert normalize_isbn("0-8044-2957-X") == "080442957X"


def test_isbn_checksum_validation() -> None:
    assert is_valid_isbn("9780547773742")
    assert is_valid_isbn("080442957X")
    assert not is_valid_isbn("9780547773740")
