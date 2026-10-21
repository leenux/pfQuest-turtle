from cn_locale import classify_schema
from gen_cn_sql import FetchError, generate_documents


def _schema():
    tables = {
        "item_template": {"entry", "name"},
        "locales_item": {"entry", "name_loc4"},
        "spell_template": {"entry", "name"},
        "locales_spell": {"entry", "name_loc4"},
        "creature_template": {"entry", "name"},
        "locales_creature": {"entry", "name_loc4"},
        "quest_template": {
            "entry", "Title", "ReqItemId1", "ReqItemId2", "ReqItemId3", "ReqItemId4",
            "SrcItemId", "ReqCreatureOrGOId1", "ReqCreatureOrGOId2",
            "ReqCreatureOrGOId3", "ReqCreatureOrGOId4",
        },
        "locales_quest": {
            "entry", "Title_loc4", "Details_loc4", "Objectives_loc4",
            "ObjectiveText1_loc4", "ObjectiveText2_loc4", "ObjectiveText3_loc4",
            "ObjectiveText4_loc4", "OfferRewardText_loc4", "RequestItemsText_loc4",
            "EndText_loc4",
        },
    }
    return classify_schema(tables)


def _quest():
    return {
        "entry": 11,
        "english": "Kill the Bear Cub",
        "current": "旧标题",
        "row_exists": True,
        "req_items": [0, 0, 0, 0],
        "src_item": 0,
        "req_creatures": [5, 0, 0, 0],
        "starters": [],
        "enders": [],
        "texts": {
            "ObjectiveText1_loc4": "Bear Cub",
            "ObjectiveText2_loc4": None,
            "ObjectiveText3_loc4": None,
            "ObjectiveText4_loc4": None,
            "Details_loc4": "Kill the Bear Cub",
            "Objectives_loc4": None,
            "OfferRewardText_loc4": None,
            "RequestItemsText_loc4": None,
            "EndText_loc4": None,
        },
    }


def test_generate_documents_writes_names_and_skips_existing_chinese(monkeypatch):
    calls = []

    def fetch(fetch_type, entry):
        calls.append((fetch_type, entry))
        return f"<title>{fetch_type}-{entry}-狼</title>"

    bundle = {
        "schema": _schema(),
        "extra_required": {},
        "items": [
            {"entry": 1, "english": "Wolf Pelt", "current": None, "row_exists": False},
            {"entry": 2, "english": "Cooked", "current": "熟肉", "row_exists": True},
        ],
        "spells": [],
        "creatures": [
            {"entry": 5, "english": "Bear Cub", "current": "幼熊", "row_exists": True},
        ],
        "quests": [_quest()],
    }
    first = generate_documents(bundle, {}, fetch)
    assert calls == [("item", 1)]
    assert "INSERT INTO `locales_item`" in first["files"]["item-cn-2026-10-21.sql"]
    assert "熟肉" not in first["files"]["item-cn-2026-10-21.sql"]
    assert "`ObjectiveText1_loc4` = '幼熊'" in first["files"]["quest-cn-2026-10-21.sql"]
    assert "Kill the 幼熊" in first["files"]["quest-cn-2026-10-21.sql"]
    second = generate_documents(bundle, first["cache"], fetch)
    assert second["files"] == first["files"]
    assert calls == [("item", 1)]


def test_generate_documents_stops_after_twenty_consecutive_failures():
    def fetch(fetch_type, entry):
        raise FetchError(404)

    items = [
        {"entry": index, "english": f"Item {index}", "current": None, "row_exists": False}
        for index in range(1, 22)
    ]
    bundle = {
        "schema": _schema(),
        "extra_required": {},
        "items": items,
        "spells": [],
        "creatures": [],
        "quests": [],
    }
    result = generate_documents(bundle, {}, fetch)
    assert "item-cn-2026-10-21.sql" in result["files"]
    assert "INSERT" not in result["files"]["item-cn-2026-10-21.sql"]
    assert result["skipped"].count("http 404") == 20
    assert "fetch stopped" in result["skipped"]


def test_structural_failure_stops_only_that_category():
    def fetch(fetch_type, entry):
        if fetch_type == "item":
            return "<html>blocked</html>"
        return "<title>火球</title>"

    bundle = {
        "schema": _schema(),
        "extra_required": {},
        "items": [
            {"entry": 1, "english": "One", "current": None, "row_exists": False},
            {"entry": 2, "english": "Two", "current": None, "row_exists": False},
        ],
        "spells": [
            {"entry": 9, "english": "Fireball", "current": "Fireball", "row_exists": True},
        ],
        "creatures": [],
        "quests": [],
    }
    result = generate_documents(bundle, {}, fetch)
    assert "item-cn-2026-10-21.sql" not in result["files"]
    assert "no name region" in result["skipped"]
    assert "`name_loc4` = '火球'" in result["files"]["spell-cn-2026-10-21.sql"]


def _item(entry):
    return {"entry": entry, "english": f"Item {entry}", "current": None, "row_exists": False}


def _bundle(items=(), spells=(), quests=()):
    return {
        "schema": _schema(),
        "extra_required": {},
        "items": list(items),
        "spells": list(spells),
        "creatures": [],
        "quests": list(quests),
    }


def test_cached_rows_do_not_count_as_seen_name_region():
    calls = []

    def fetch(fetch_type, entry):
        calls.append((fetch_type, entry))
        return "<html>blocked</html>"

    bundle = _bundle(items=[_item(1), _item(2), _item(3)])
    result = generate_documents(bundle, {"item": {"1": "狼皮"}}, fetch)
    assert calls == [("item", 2)]
    assert "no name region" in result["skipped"]
    assert "狼皮" in result["files"]["item-cn-2026-10-21.sql"]


def test_relation_tables_unavailable_recorded_once():
    quest = _quest()
    quest["current"] = None
    result = generate_documents(_bundle(quests=[quest]), {"quest": {"11": "熊"}}, lambda t, e: "")
    assert result["skipped"].count("relation tables unavailable") == 1


def test_failure_counter_shared_across_categories():
    calls = []

    def fetch(fetch_type, entry):
        calls.append((fetch_type, entry))
        raise FetchError(404)

    quest = _quest()
    quest["current"] = None
    bundle = _bundle(
        items=[_item(i) for i in range(1, 20)],
        spells=[{"entry": 100, "english": "Fireball", "current": None, "row_exists": False}],
        quests=[quest],
    )
    result = generate_documents(bundle, {}, fetch)
    assert len(calls) == 20
    assert ("quest", 11) not in calls
    assert result["skipped"].count("http 404") == 20
    assert "quest\t11\tfetch stopped" in result["skipped"]


def test_cached_name_still_produces_sql_after_global_stop():
    def fetch(fetch_type, entry):
        raise FetchError(404)

    bundle = _bundle(items=[_item(i) for i in range(1, 22)])
    result = generate_documents(bundle, {"item": {"1": "狼皮"}}, fetch)
    assert result["skipped"].count("http 404") == 20
    assert "狼皮" in result["files"]["item-cn-2026-10-21.sql"]


def test_title_without_chinese_is_logged_and_not_inserted():
    def fetch(fetch_type, entry):
        return "<title>Wolf Pelt</title>"

    result = generate_documents(_bundle(items=[_item(1)]), {}, fetch)
    assert "item\t1\tno chinese name" in result["skipped"]
    assert "INSERT" not in result["files"]["item-cn-2026-10-21.sql"]


from pathlib import Path

from gen_cn_sql import load_bundle, run


def test_load_bundle_uses_select_and_distinguishes_missing_locale_rows():
    seen = []

    def query(sql):
        assert sql.lstrip().upper().startswith("SELECT")
        seen.append(sql)
        if "information_schema.COLUMNS" in sql:
            return [
                {"TABLE_NAME": "item_template", "COLUMN_NAME": "entry", "IS_NULLABLE": "NO", "COLUMN_DEFAULT": None, "EXTRA": ""},
                {"TABLE_NAME": "item_template", "COLUMN_NAME": "name", "IS_NULLABLE": "NO", "COLUMN_DEFAULT": None, "EXTRA": ""},
                {"TABLE_NAME": "locales_item", "COLUMN_NAME": "entry", "IS_NULLABLE": "NO", "COLUMN_DEFAULT": None, "EXTRA": ""},
                {"TABLE_NAME": "locales_item", "COLUMN_NAME": "name_loc4", "IS_NULLABLE": "YES", "COLUMN_DEFAULT": None, "EXTRA": ""},
                {"TABLE_NAME": "locales_item", "COLUMN_NAME": "description_loc4", "IS_NULLABLE": "NO", "COLUMN_DEFAULT": None, "EXTRA": ""},
            ]
        if "FROM `item_template`" in sql:
            return [
                {"entry": 7, "english": "Wolf Pelt", "locale_entry": None, "current": None},
                {"entry": 8, "english": "Cooked", "locale_entry": 8, "current": "熟肉"},
            ]
        return []

    bundle = load_bundle(query)
    assert bundle["items"][0]["row_exists"] is False
    assert bundle["items"][1]["row_exists"] is True
    assert bundle["extra_required"]["locales_item"] == ["description_loc4"]
    assert bundle["schema"]["spell"]["ok"] is False
    assert any(sql.startswith("SELECT") for sql in seen)


def test_run_writes_nothing_when_connect_fails(tmp_path):
    def connect(config):
        raise OSError("down")

    code = run({"user": "a", "password": "b", "database": "world"}, connect, None, tmp_path)
    assert code == 1
    assert list(tmp_path.rglob("*.sql")) == []


def test_load_bundle_reads_quest_objectives_and_relations():
    seen = []
    columns = {
        "quest_template": [
            "entry", "Title", "ReqItemId1", "ReqItemId2", "ReqItemId3", "ReqItemId4",
            "SrcItemId", "ReqCreatureOrGOId1", "ReqCreatureOrGOId2",
            "ReqCreatureOrGOId3", "ReqCreatureOrGOId4",
        ],
        "locales_quest": [
            "entry", "Title_loc4", "Details_loc4", "Objectives_loc4",
            "ObjectiveText1_loc4", "ObjectiveText2_loc4", "ObjectiveText3_loc4",
            "ObjectiveText4_loc4", "OfferRewardText_loc4", "RequestItemsText_loc4",
            "EndText_loc4",
        ],
        "creature_questrelation": ["id", "quest"],
        "creature_involvedrelation": ["id", "quest"],
    }
    schema_rows = [
        {"TABLE_NAME": table, "COLUMN_NAME": column, "IS_NULLABLE": "YES", "COLUMN_DEFAULT": None, "EXTRA": ""}
        for table, names in columns.items()
        for column in names
    ]
    quest_row = {
        "entry": 11,
        "english": "Kill the Boar",
        "locale_entry": 11,
        "current": "杀野猪",
        "req_item_1": 4, "req_item_2": 0, "req_item_3": 0, "req_item_4": 0,
        "src_item": 0,
        "req_creature_1": 5, "req_creature_2": -6, "req_creature_3": 0, "req_creature_4": 0,
        "objective_1": "Boar", "objective_2": None, "objective_3": None, "objective_4": None,
        "details": "Kill the Boar",
        "objectives": None, "offer": None, "request": None, "end_text": None,
    }

    def query(sql):
        assert sql.lstrip().upper().startswith("SELECT")
        seen.append(sql)
        if "information_schema.COLUMNS" in sql:
            return schema_rows
        if "FROM `creature_questrelation`" in sql:
            return [{"creature_id": 8, "quest_id": 11}]
        if "FROM `creature_involvedrelation`" in sql:
            return [{"creature_id": 9, "quest_id": 11}]
        if "FROM `quest_template`" in sql:
            return [quest_row]
        return []

    bundle = load_bundle(query)
    assert len(bundle["quests"]) == 1
    quest = bundle["quests"][0]
    assert quest["req_items"] == [4, 0, 0, 0]
    assert quest["src_item"] == 0
    assert quest["req_creatures"] == [5, -6, 0, 0]
    assert quest["starters"] == [8]
    assert quest["enders"] == [9]
    assert quest["texts"]["Details_loc4"] == "Kill the Boar"
    assert quest["texts"]["ObjectiveText1_loc4"] == "Boar"
    assert quest["current"] == "杀野猪"
    assert quest["row_exists"] is True
    assert any("FROM `creature_questrelation`" in sql and sql.startswith("SELECT") for sql in seen)
    assert any("FROM `quest_template`" in sql and sql.startswith("SELECT") for sql in seen)
