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


def sql_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def sql_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("'", "''")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return "'" + escaped + "'"


def render_name_sql(
    table: str,
    entry_column: str,
    entry: int,
    name_column: str,
    row_exists: bool,
    current: str | None,
    chinese: str,
    extra_required: list[str],
) -> str:
    entry_id = int(entry)
    table_sql = sql_ident(table)
    entry_sql = sql_ident(entry_column)
    name_sql = sql_ident(name_column)
    if not row_exists:
        extras = sorted(extra_required)
        columns = [entry_column, name_column, *extras]
        values = [str(entry_id), sql_string(chinese), *["''" for _ in extras]]
        column_sql = ", ".join(sql_ident(column) for column in columns)
        value_sql = ", ".join(values)
        return (
            f"INSERT INTO {table_sql} ({column_sql}) "
            f"SELECT {value_sql} FROM DUAL "
            f"WHERE NOT EXISTS (SELECT 1 FROM {table_sql} WHERE {entry_sql} = {entry_id});"
        )
    if current is None:
        condition = f"{name_sql} IS NULL"
    else:
        condition = f"{name_sql} = {sql_string(current)}"
    return (
        f"UPDATE {table_sql} SET {name_sql} = {sql_string(chinese)} "
        f"WHERE {entry_sql} = {entry_id} AND {condition};"
    )


def render_text_update(
    table: str, entry_column: str, entry: int, column: str, old: str, new: str
) -> str:
    return (
        f"UPDATE {sql_ident(table)} SET {sql_ident(column)} = {sql_string(new)} "
        f"WHERE {sql_ident(entry_column)} = {int(entry)} AND {sql_ident(column)} = {sql_string(old)};"
    )
