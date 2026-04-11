import re


TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9_]+")


def normalize_text(text: str) -> str:
    return " ".join(tokenize(text))


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]
