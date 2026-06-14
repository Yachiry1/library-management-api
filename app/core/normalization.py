import re

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_human_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip()).casefold()

 
def clean_display_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip())


def normalize_author_name(first_name: str, last_name: str) -> tuple[str, str]:
    return normalize_human_text(first_name), normalize_human_text(last_name)


def normalize_title(title: str) -> str:
    return normalize_human_text(title)


def normalize_isbn(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[\s-]+", "", value).upper()
    return normalized or None


def is_valid_isbn(value: str) -> bool:
    return _is_valid_isbn10(value) or _is_valid_isbn13(value)


def _is_valid_isbn10(value: str) -> bool:
    if len(value) != 10:
        return False
    if not value[:9].isdigit():
        return False
    total = 0
    for index, char in enumerate(value[:9], start=1):
        total += index * int(char)
    check_char = value[-1]
    if check_char == "X":
        check = 10
    elif check_char.isdigit():
        check = int(check_char)
    else:
        return False
    total += 10 * check
    return total % 11 == 0


def _is_valid_isbn13(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    total = 0
    for index, char in enumerate(value[:12]):
        weight = 1 if index % 2 == 0 else 3
        total += weight * int(char)
    check = (10 - (total % 10)) % 10
    return check == int(value[-1])
