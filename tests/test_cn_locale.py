from cn_locale import (
    has_cjk,
    needs_chinese_name,
    has_name_region,
    parse_capycraft_name,
    capycraft_url,
    render_name_sql,
    render_text_update,
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
