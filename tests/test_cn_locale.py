from cn_locale import has_cjk, needs_chinese_name


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
