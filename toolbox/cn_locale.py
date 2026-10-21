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


LONG_TEXT_COLUMNS = (
    "Details_loc4",
    "Objectives_loc4",
    "OfferRewardText_loc4",
    "RequestItemsText_loc4",
    "EndText_loc4",
)


def official_name(current: str | None, fetched: str | None) -> str | None:
    if has_cjk(current):
        return current
    if has_cjk(fetched):
        return fetched
    return None


def objective_slot(
    creature_id: int,
    item_id: int,
    current: str | None,
    creature_zh: str | None,
    item_zh: str | None,
) -> tuple[str, str | None]:
    if creature_id > 0 and item_id > 0:
        return ("skip", None)
    if creature_id > 0:
        official = creature_zh
    elif item_id > 0:
        official = item_zh
    else:
        return ("keep", None)
    if current is None or current.strip() == "":
        return ("keep", None)
    if not has_cjk(official) or current == official:
        return ("keep", None)
    return ("replace", official)


def replace_english_names(text: str, pairs: list[tuple[str, str]]) -> str | None:
    ordered = sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)
    updated = text
    for english, chinese in ordered:
        if len(english) < 4:
            continue
        updated = _replace_bounded(updated, english, chinese)
    if updated == text or updated == "":
        return None
    return updated


def _is_ascii_letter(char: str) -> bool:
    return len(char) == 1 and (("A" <= char <= "Z") or ("a" <= char <= "z"))


def _replace_bounded(text: str, english: str, chinese: str) -> str:
    result = []
    start = 0
    while True:
        index = text.find(english, start)
        if index < 0:
            result.append(text[start:])
            break
        before = text[index - 1] if index else ""
        after_index = index + len(english)
        after = text[after_index] if after_index < len(text) else ""
        if _is_ascii_letter(before) or _is_ascii_letter(after):
            result.append(text[start:after_index])
            start = after_index
            continue
        result.append(text[start:index])
        result.append(chinese)
        start = after_index
    return "".join(result)


def quest_text_statements(
    quest: dict,
    item_names: dict,
    creature_names: dict,
    locale_table: str,
    entry_column: str,
) -> tuple[list[str], list[str]]:
    lines = []
    skips = []
    for index in range(4):
        creature_id = quest["req_creatures"][index]
        item_id = quest["req_items"][index]
        column = f"ObjectiveText{index + 1}_loc4"
        action, new_text = objective_slot(
            creature_id,
            item_id,
            quest["texts"].get(column),
            None if creature_id <= 0 else (creature_names.get(creature_id) or {}).get("zh"),
            None if item_id <= 0 else (item_names.get(item_id) or {}).get("zh"),
        )
        if action == "skip":
            skips.append(
                f"quest\t{quest['entry']}\tobjective slot {index + 1} has both creature and item"
            )
        elif action == "replace":
            lines.append(
                render_text_update(
                    locale_table,
                    entry_column,
                    quest["entry"],
                    column,
                    quest["texts"][column],
                    new_text,
                )
            )
    pairs = []
    seen = set()

    def add_pair(names: dict, entity_id: int) -> None:
        if entity_id <= 0:
            return
        entity = names.get(entity_id)
        if not entity or not has_cjk(entity.get("zh")):
            return
        english = entity.get("english") or ""
        if english in seen:
            return
        seen.add(english)
        pairs.append((english, entity["zh"]))

    for item_id in [*quest["req_items"], quest["src_item"]]:
        add_pair(item_names, item_id)
    for creature_id in [*quest["req_creatures"], *quest["starters"], *quest["enders"]]:
        add_pair(creature_names, creature_id)
    for column in LONG_TEXT_COLUMNS:
        current = quest["texts"].get(column)
        if current is None or current.strip() == "":
            continue
        updated = replace_english_names(current, pairs)
        if updated is None:
            continue
        lines.append(
            render_text_update(locale_table, entry_column, quest["entry"], column, current, updated)
        )
    return lines, skips


def find_column(columns: set[str], candidates: list[str]) -> str | None:
    lowered = {column.lower(): column for column in columns}
    for candidate in candidates:
        found = lowered.get(candidate.lower())
        if found:
            return found
    return None


def relation_mapping(columns: set[str]) -> tuple[str, str] | None:
    lowered = {column.lower(): column for column in columns}
    found = []
    for left, right in (("id", "quest"), ("creature_entry", "quest"), ("creature", "quest")):
        if left in lowered and right in lowered:
            found.append((lowered[left], lowered[right]))
    if len(found) == 1:
        return found[0]
    return None


def classify_schema(table_columns: dict[str, set[str]]) -> dict:
    by_lower = {name.lower(): (name, columns) for name, columns in table_columns.items()}
    specs = {
        "item": ("item_template", "locales_item", ["name"], ["name_loc4"]),
        "spell": ("spell_template", "locales_spell", ["name", "SpellName"], ["name_loc4"]),
        "creature": ("creature_template", "locales_creature", ["Name", "name"], ["name_loc4"]),
        "quest": ("quest_template", "locales_quest", ["Title"], ["Title_loc4"]),
    }
    quest_template_required = [
        "ReqItemId1", "ReqItemId2", "ReqItemId3", "ReqItemId4", "SrcItemId",
        "ReqCreatureOrGOId1", "ReqCreatureOrGOId2", "ReqCreatureOrGOId3", "ReqCreatureOrGOId4",
        "Title",
    ]
    quest_locale_required = [
        "Title_loc4", "Details_loc4", "Objectives_loc4",
        "ObjectiveText1_loc4", "ObjectiveText2_loc4", "ObjectiveText3_loc4", "ObjectiveText4_loc4",
        "OfferRewardText_loc4", "RequestItemsText_loc4", "EndText_loc4",
    ]
    result = {}
    for key, (english_table, locale_table, english_names, locale_names) in specs.items():
        if english_table not in by_lower or locale_table not in by_lower:
            result[key] = {"ok": False, "reason": f"missing {english_table} or {locale_table}"}
            continue
        english_actual, english_columns = by_lower[english_table]
        locale_actual, locale_columns = by_lower[locale_table]
        entry_column = find_column(english_columns, ["entry", "Entry"])
        locale_entry = find_column(locale_columns, ["entry", "Entry"])
        english_name = find_column(english_columns, english_names)
        locale_name = find_column(locale_columns, locale_names)
        mapped = {"template": {}, "locale": {}}
        if key == "quest":
            missing = False
            for column in quest_template_required:
                found = find_column(english_columns, [column])
                mapped["template"][column] = found
                missing = missing or found is None
            for column in quest_locale_required:
                found = find_column(locale_columns, [column])
                mapped["locale"][column] = found
                missing = missing or found is None
            if missing or not entry_column or not locale_entry or not english_name or not locale_name:
                result[key] = {"ok": False, "reason": "missing quest text or link columns"}
                continue
        elif not entry_column or not locale_entry or not english_name or not locale_name:
            result[key] = {"ok": False, "reason": f"missing columns for {key}"}
            continue
        result[key] = {
            "ok": True,
            "english_table": english_actual,
            "locale_table": locale_actual,
            "entry_column": entry_column,
            "locale_entry": locale_entry,
            "english_name": english_name,
            "name_column": locale_name,
            "columns": mapped,
        }
    relations = {}
    for table in ("creature_questrelation", "creature_involvedrelation"):
        if table not in by_lower:
            relations[table] = None
            continue
        actual, columns = by_lower[table]
        mapping = relation_mapping(columns)
        if mapping is None:
            relations[table] = None
        else:
            relations[table] = {"table": actual, "creature": mapping[0], "quest": mapping[1]}
    result["relations"] = relations
    return result


def extra_required_columns(
    column_rows: list[dict], entry_column: str, name_column: str
) -> list[str]:
    required = []
    for column in column_rows:
        if column["name"] in (entry_column, name_column):
            continue
        extra = (column.get("extra") or "").lower()
        if "auto_increment" in extra:
            continue
        if column["nullable"] == "NO" and column["default"] is None:
            required.append(column["name"])
    return sorted(required)

