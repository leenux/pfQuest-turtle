from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from cn_locale import (
    capycraft_url,
    classify_schema,
    extra_required_columns,
    has_cjk,
    has_name_region,
    needs_chinese_name,
    official_name,
    parse_capycraft_name,
    quest_text_statements,
    render_name_sql,
    sql_ident,
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


def load_bundle(query) -> dict:
    rows = query(
        "SELECT TABLE_NAME, COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, EXTRA "
        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()"
    )
    table_columns = {}
    columns_by_table = {}
    for row in rows:
        table_columns.setdefault(row["TABLE_NAME"], set()).add(row["COLUMN_NAME"])
        columns_by_table.setdefault(row["TABLE_NAME"], []).append(
            {
                "name": row["COLUMN_NAME"],
                "nullable": row["IS_NULLABLE"],
                "default": row["COLUMN_DEFAULT"],
                "extra": row["EXTRA"],
            }
        )
    schema = classify_schema(table_columns)
    extra = {}
    for category in ("item", "spell", "creature", "quest"):
        found = schema[category]
        if not found["ok"]:
            continue
        extra[found["locale_table"]] = extra_required_columns(
            columns_by_table[found["locale_table"]],
            found["locale_entry"],
            found["name_column"],
        )
    bundle = {
        "schema": schema,
        "extra_required": extra,
        "items": _name_rows(query, schema["item"]) if schema["item"]["ok"] else [],
        "spells": _name_rows(query, schema["spell"]) if schema["spell"]["ok"] else [],
        "creatures": _name_rows(query, schema["creature"]) if schema["creature"]["ok"] else [],
        "quests": _quest_rows(query, schema) if schema["quest"]["ok"] else [],
    }
    return bundle


def _name_rows(query, schema) -> list[dict]:
    english_table = sql_ident(schema["english_table"])
    locale_table = sql_ident(schema["locale_table"])
    entry_column = sql_ident(schema["entry_column"])
    locale_entry = sql_ident(schema["locale_entry"])
    english_name = sql_ident(schema["english_name"])
    locale_name = sql_ident(schema["name_column"])
    sql = (
        f"SELECT t.{entry_column} AS entry, t.{english_name} AS english, "
        f"l.{locale_entry} AS locale_entry, l.{locale_name} AS current "
        f"FROM {english_table} t LEFT JOIN {locale_table} l "
        f"ON l.{locale_entry} = t.{entry_column}"
    )
    return [_loaded_name(row) for row in query(sql)]


def _loaded_name(row: dict) -> dict:
    return {
        "entry": row["entry"],
        "english": row["english"] or "",
        "current": row["current"],
        "row_exists": row["locale_entry"] is not None,
    }


def _quest_rows(query, schema) -> list[dict]:
    found = schema["quest"]
    template = found["columns"]["template"]
    locale = found["columns"]["locale"]
    select_list = [
        f"t.{sql_ident(found['entry_column'])} AS entry",
        f"t.{sql_ident(found['english_name'])} AS english",
        f"l.{sql_ident(found['locale_entry'])} AS locale_entry",
        f"l.{sql_ident(found['name_column'])} AS current",
    ]
    for index in range(1, 5):
        select_list.append(f"t.{sql_ident(template[f'ReqItemId{index}'])} AS req_item_{index}")
        select_list.append(
            f"t.{sql_ident(template[f'ReqCreatureOrGOId{index}'])} AS req_creature_{index}"
        )
        select_list.append(f"l.{sql_ident(locale[f'ObjectiveText{index}_loc4'])} AS objective_{index}")
    select_list.append(f"t.{sql_ident(template['SrcItemId'])} AS src_item")
    for column, alias in (
        ("Details_loc4", "details"),
        ("Objectives_loc4", "objectives"),
        ("OfferRewardText_loc4", "offer"),
        ("RequestItemsText_loc4", "request"),
        ("EndText_loc4", "end_text"),
    ):
        select_list.append(f"l.{sql_ident(locale[column])} AS {alias}")
    sql = (
        f"SELECT {', '.join(select_list)} FROM {sql_ident(found['english_table'])} t "
        f"LEFT JOIN {sql_ident(found['locale_table'])} l "
        f"ON l.{sql_ident(found['locale_entry'])} = t.{sql_ident(found['entry_column'])}"
    )
    starters, enders = _relations(query, schema["relations"])
    quests = []
    for row in query(sql):
        entry = row["entry"]
        quests.append(
            {
                **_loaded_name(row),
                "req_items": [row[f"req_item_{index}"] or 0 for index in range(1, 5)],
                "src_item": row["src_item"] or 0,
                "req_creatures": [row[f"req_creature_{index}"] or 0 for index in range(1, 5)],
                "starters": starters.get(entry, []),
                "enders": enders.get(entry, []),
                "texts": {
                    "ObjectiveText1_loc4": row["objective_1"],
                    "ObjectiveText2_loc4": row["objective_2"],
                    "ObjectiveText3_loc4": row["objective_3"],
                    "ObjectiveText4_loc4": row["objective_4"],
                    "Details_loc4": row["details"],
                    "Objectives_loc4": row["objectives"],
                    "OfferRewardText_loc4": row["offer"],
                    "RequestItemsText_loc4": row["request"],
                    "EndText_loc4": row["end_text"],
                },
            }
        )
    return quests


def _relations(query, relations) -> tuple[dict, dict]:
    starters = _relation_map(query, relations["creature_questrelation"])
    enders = _relation_map(query, relations["creature_involvedrelation"])
    return starters, enders


def _relation_map(query, mapping) -> dict:
    if mapping is None:
        return {}
    sql = (
        f"SELECT {sql_ident(mapping['creature'])} AS creature_id, "
        f"{sql_ident(mapping['quest'])} AS quest_id "
        f"FROM {sql_ident(mapping['table'])}"
    )
    grouped = {}
    for row in query(sql):
        grouped.setdefault(row["quest_id"], []).append(row["creature_id"])
    return grouped


def write_outputs(root: Path, documents: dict) -> None:
    sql_dir = root / "sql"
    cache_dir = sql_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in documents["files"].items():
        (sql_dir / filename).write_text(content, encoding="utf-8")
    (sql_dir / "cn-2026-10-21-skipped.txt").write_text(documents["skipped"], encoding="utf-8")
    (cache_dir / "capycraft.json").write_text(
        json.dumps(documents["cache"], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def default_fetch(fetch_type: str, entry: int) -> str:
    request = Request(capycraft_url(fetch_type, entry), headers={"User-Agent": "pfQuest-turtle-cn-sql"})
    try:
        with urlopen(request, timeout=20) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise FetchError(status)
            return response.read().decode("utf-8", errors="replace")
    except FetchError:
        raise
    except Exception as exc:
        status = getattr(exc, "code", None)
        raise FetchError(status) from exc


def run(config: dict, connect, fetch, root: Path) -> int:
    try:
        connection = connect(config)
    except Exception as exc:
        print(f"database connection failed: {exc}", file=sys.stderr)
        return 1
    try:
        def query(sql: str):
            with connection.cursor() as cursor:
                cursor.execute(sql)
                return list(cursor.fetchall())

        cache_path = root / "sql" / "cache" / "capycraft.json"
        cache = {}
        if cache_path.exists():
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        documents = generate_documents(load_bundle(query), cache, fetch)
        write_outputs(root, documents)
    finally:
        connection.close()
    return 0


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    config_path = root / "sql" / "db.local.json"
    if not config_path.exists():
        print("missing sql/db.local.json", file=sys.stderr)
        return 1
    config = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        import pymysql
    except ImportError:
        print("pip install pymysql", file=sys.stderr)
        return 1

    def connect(loaded):
        return pymysql.connect(
            host=loaded.get("host", "127.0.0.1"),
            port=int(loaded.get("port", 3306)),
            user=loaded["user"],
            password=loaded["password"],
            database=loaded["database"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    return run(config, connect, default_fetch, root)


if __name__ == "__main__":
    raise SystemExit(main())