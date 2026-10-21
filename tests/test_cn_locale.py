from cn_locale import (
    has_cjk,
    needs_chinese_name,
    has_name_region,
    parse_capycraft_name,
    capycraft_url,
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
