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
