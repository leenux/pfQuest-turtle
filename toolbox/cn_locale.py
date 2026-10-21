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


import re

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def has_name_region(html: str) -> bool:
    return _TITLE_RE.search(html) is not None or _H1_RE.search(html) is not None


def parse_capycraft_name(html: str) -> str | None:
    for pattern in (_TITLE_RE, _H1_RE):
        match = pattern.search(html)
        if not match:
            continue
        raw = _TAG_RE.sub("", match.group(1))
        raw = (
            raw.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
        )
        name = _slice_cjk(raw)
        if name and has_cjk(name):
            return name
    return None


def _slice_cjk(raw: str) -> str | None:
    start = None
    for index, char in enumerate(raw):
        if has_cjk(char):
            start = index
            break
    if start is None:
        return None
    end = len(raw)
    for index in range(start, len(raw)):
        char = raw[index]
        if ("A" <= char <= "Z") or ("a" <= char <= "z"):
            end = index
            break
    sliced = raw[start:end].strip(" \t\r\n-|·–—:：/")
    return sliced or None


def capycraft_url(fetch_type: str, entry: int) -> str:
    return f"https://capycraft.io/db/?{fetch_type}={int(entry)}"
