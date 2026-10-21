from cn_locale import (
    has_cjk,
    needs_chinese_name,
    has_name_region,
    parse_capycraft_name,
    capycraft_url,
    render_name_sql,
    render_text_update,
    official_name,
    objective_slot,
    quest_text_statements,
    replace_english_names,
)


def test_has_cjk_detects_unified_ideographs():
    assert has_cjk("炎刃") is True
    assert has_cjk("Wolf") is False
    assert has_cjk("") is False
    assert has_cjk(None) is False
    assert has_cjk("A炎") is True


def test_needs_chinese_name_only_when_missing_or_not_chinese():
    assert needs_chinese_name(None, "Wolf") is True
    assert needs_chinese_name("   ", "Wolf") is True
    assert needs_chinese_name("Wolf", "Wolf") is True
    assert needs_chinese_name("Lobo", "Wolf") is True
    assert needs_chinese_name("狼", "Wolf") is False
    assert needs_chinese_name("狼皮", "Wolf") is False


def test_parse_capycraft_name_stops_before_ascii_letters():
    html = "<html><title>炎刃 - Capycraft</title></html>"
    assert parse_capycraft_name(html) == "炎刃"


def test_parse_capycraft_name_reads_h1_when_title_has_no_cjk():
    html = "<html><title>Item</title><h1>狼皮</h1></html>"
    assert parse_capycraft_name(html) == "狼皮"


def test_parse_capycraft_name_rejects_pages_without_cjk():
    html = "<html><title>Wolf Pelt</title></html>"
    assert parse_capycraft_name(html) is None


def test_has_name_region_requires_title_or_h1():
    assert has_name_region("<html></html>") is False
    assert has_name_region("<title>炎刃</title>") is True


def test_capycraft_url_uses_the_agreed_query():
    assert capycraft_url("npc", 42) == "https://capycraft.io/db/?npc=42"


def test_render_name_sql_inserts_when_the_locale_row_is_missing():
    sql = render_name_sql(
        "locales_item", "entry", 7, "name_loc4", False, None, "狼皮", ["description_loc4"]
    )
    assert "INSERT INTO `locales_item`" in sql
    assert "WHERE NOT EXISTS" in sql
    assert "`description_loc4`" in sql
    assert "'狼皮'" in sql


def test_render_name_sql_updates_null_and_exact_old_values():
    null_sql = render_name_sql(
        "locales_item", "entry", 7, "name_loc4", True, None, "狼皮", []
    )
    old_sql = render_name_sql(
        "locales_item", "entry", 8, "name_loc4", True, "Wolf's Pelt", "狼皮", []
    )
    assert "`name_loc4` IS NULL" in null_sql
    assert "UPDATE `locales_item`" in old_sql
    assert "`name_loc4` = 'Wolf''s Pelt'" in old_sql


def test_sql_string_escapes_quotes_backslashes_and_newlines():
    statement = render_text_update(
        "locales_quest", "entry", 3, "Details_loc4", "A\\B\nC", "甲'乙"
    )
    assert "`Details_loc4` = '甲''乙'" in statement
    assert "`Details_loc4` = 'A\\\\B\\nC'" in statement


def test_official_name_prefers_existing_chinese():
    assert official_name("狼", "野狼") == "狼"
    assert official_name("Wolf", "狼") == "狼"
    assert official_name("Wolf", "Wolf") is None
    assert official_name(None, None) is None


def test_objective_slot_replaces_one_target_and_skips_both():
    assert objective_slot(5, 9, "旧", "野猪", "肉") == ("skip", None)
    assert objective_slot(5, 0, "旧", "野猪", None) == ("replace", "野猪")
    assert objective_slot(0, 9, "肉", None, "肉") == ("keep", None)
    assert objective_slot(0, 9, None, None, "肉") == ("keep", None)
    assert objective_slot(5, 0, "Boar", None, None) == ("keep", None)


def test_replace_english_names_respects_length_order_and_word_edges():
    replaced = replace_english_names(
        "Kill the Bear Cub and the Bear",
        [("Bear", "熊"), ("Bear Cub", "幼熊")],
    )
    assert replaced == "Kill the 幼熊 and the 熊"
    assert replace_english_names("Wolfsbane", [("Wolf", "狼")]) is None
    assert replace_english_names("Use an Axe", [("Axe", "斧")]) is None
    assert replace_english_names("去找老板", [("Boss", "老板")]) is None
    assert replace_english_names("Wolf", [("Wolf", "")]) is None


def test_quest_text_statements_updates_short_text_and_details():
    quest = {
        "entry": 10,
        "req_items": [0, 4, 0, 0],
        "src_item": 0,
        "req_creatures": [5, 9, 0, 0],
        "starters": [],
        "enders": [],
        "texts": {
            "ObjectiveText1_loc4": "Boar",
            "ObjectiveText2_loc4": "冲突",
            "ObjectiveText3_loc4": None,
            "ObjectiveText4_loc4": "",
            "Details_loc4": "Kill the Bear Cub",
            "Objectives_loc4": None,
            "OfferRewardText_loc4": "",
            "RequestItemsText_loc4": None,
            "EndText_loc4": None,
        },
    }
    statements, skips = quest_text_statements(
        quest,
        {4: {"english": "Meat", "zh": "肉"}},
        {
            5: {"english": "Boar", "zh": "野猪"},
            9: {"english": "Wolf", "zh": "狼"},
        },
        "locales_quest",
        "entry",
    )
    assert any("`ObjectiveText1_loc4` = '野猪'" in line for line in statements)
    assert any("objective slot 2 has both creature and item" in line for line in skips)
    assert all("ObjectiveText2_loc4" not in line for line in statements)


def test_quest_long_text_replaces_linked_english_names_only():
    quest = {
        "entry": 11,
        "req_items": [0, 0, 0, 0],
        "src_item": 0,
        "req_creatures": [5, 0, 0, 0],
        "starters": [8],
        "enders": [],
        "texts": {
            "ObjectiveText1_loc4": "野猪",
            "ObjectiveText2_loc4": None,
            "ObjectiveText3_loc4": None,
            "ObjectiveText4_loc4": None,
            "Details_loc4": "Kill the Bear Cub near the inn",
            "Objectives_loc4": "去找老板",
            "OfferRewardText_loc4": None,
            "RequestItemsText_loc4": None,
            "EndText_loc4": None,
        },
    }
    statements, skips = quest_text_statements(
        quest,
        {},
        {
            5: {"english": "Bear Cub", "zh": "幼熊"},
            8: {"english": "Innkeeper", "zh": "旅店老板"},
        },
        "locales_quest",
        "entry",
    )
    assert skips == []
    assert any("Kill the 幼熊 near the inn" in line for line in statements)
    assert any("`Details_loc4` = 'Kill the Bear Cub near the inn'" in line for line in statements)
    assert all("Objectives_loc4" not in line for line in statements)
