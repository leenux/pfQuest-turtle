from __future__ import annotations

from cn_locale import (
    has_cjk,
    has_name_region,
    needs_chinese_name,
    official_name,
    parse_capycraft_name,
    quest_text_statements,
    render_name_sql,
)

FILE_NAMES = {
    "item": "item-cn-2026-10-21.sql",
    "spell": "spell-cn-2026-10-21.sql",
    "quest": "quest-cn-2026-10-21.sql",
    "creature": "creature-2026-10-21.sql",
}
FETCH_TYPES = {"item": "item", "spell": "spell", "quest": "quest", "creature": "npc"}
ROW_KEYS = {"item": "items", "spell": "spells", "quest": "quests", "creature": "creatures"}


class FetchError(Exception):
    def __init__(self, status: int | None):
        super().__init__(str(status))
        self.status = status


def generate_documents(bundle: dict, cache: dict, fetch) -> dict:
    skipped = []
    stored = {
        key: dict(cache.get(key, {}))
        for key in ("item", "spell", "quest", "npc")
    }
    state = {"count": 0, "stopped": False}
    files = {}
    category_stopped = set()

    def note(category: str, entry, reason: str) -> None:
        skipped.append(f"{category}\t{entry}\t{reason}")

    def pull(category: str, entry: int, seen_region: bool):
        fetch_type = FETCH_TYPES[category]
        key = str(entry)
        if key in stored[fetch_type]:
            return "hit", stored[fetch_type][key], seen_region
        if state["stopped"] or category in category_stopped:
            note(category, entry, "fetch stopped")
            return "miss", None, seen_region
        try:
            html = fetch(fetch_type, entry)
        except FetchError as exc:
            state["count"] += 1
            status = exc.status if exc.status is not None else "error"
            note(category, entry, f"http {status}")
            if state["count"] >= 20:
                state["stopped"] = True
            return "miss", None, seen_region
        if not has_name_region(html):
            if not seen_region:
                note(category, "*", "no name region")
                category_stopped.add(category)
                return "structural", None, seen_region
            state["count"] += 1
            note(category, entry, "no name region")
            if state["count"] >= 20:
                state["stopped"] = True
            return "miss", None, seen_region
        name = parse_capycraft_name(html)
        if not name:
            state["count"] += 1
            note(category, entry, "no chinese name")
            if state["count"] >= 20:
                state["stopped"] = True
            return "miss", None, True
        state["count"] = 0
        stored[fetch_type][key] = name
        return "hit", name, True

    for category in ("item", "spell", "creature", "quest"):
        schema = bundle["schema"][category]
        if not schema["ok"]:
            note(category, "*", schema["reason"])
            continue
        seen_region = False
        statements = []
        for row in bundle[ROW_KEYS[category]]:
            if not needs_chinese_name(row["current"], row["english"]):
                continue
            status, name, seen_region = pull(category, row["entry"], seen_region)
            if status != "hit":
                continue
            statements.append(
                render_name_sql(
                    schema["locale_table"],
                    schema["locale_entry"],
                    row["entry"],
                    schema["name_column"],
                    row["row_exists"],
                    row["current"],
                    name,
                    bundle.get("extra_required", {}).get(schema["locale_table"], []),
                )
            )
        if category == "quest":
            statements.extend(_quest_text(bundle, stored, skipped, note))
        if category not in category_stopped:
            files[FILE_NAMES[category]] = _sql_file(statements)
    text = "\n".join(skipped)
    if text:
        text += "\n"
    return {"files": files, "skipped": text, "cache": stored}


def _sql_file(statements: list[str]) -> str:
    body = "-- generated zhCN sql 2026-10-21\n"
    if statements:
        body += "\n".join(statements) + "\n"
    return body


def _names_for(rows: list[dict], fetch_type: str, cache: dict) -> dict:
    names = {}
    for row in rows:
        names[row["entry"]] = {
            "english": row["english"],
            "zh": official_name(row["current"], cache[fetch_type].get(str(row["entry"]))),
        }
    return names


def _quest_text(bundle: dict, cache: dict, skipped: list[str], note) -> list[str]:
    relations = bundle["schema"]["relations"]
    if relations["creature_questrelation"] is None or relations["creature_involvedrelation"] is None:
        note("quest", "*", "relation tables unavailable")
    schema = bundle["schema"]["quest"]
    item_names = _names_for(bundle["items"], "item", cache)
    creature_names = _names_for(bundle["creatures"], "npc", cache)
    statements = []
    for quest in bundle["quests"]:
        lines, skips = quest_text_statements(
            quest,
            item_names,
            creature_names,
            schema["locale_table"],
            schema["locale_entry"],
        )
        statements.extend(lines)
        skipped.extend(skips)
    return statements
