from __future__ import annotations


def has_cjk(text: str | None) -> bool:
    if not text:
        return False
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def needs_chinese_name(current: str | None, english: str | None) -> bool:
    if current is None or current.strip() == "":
        return True
    if has_cjk(current):
        return False
    return True
