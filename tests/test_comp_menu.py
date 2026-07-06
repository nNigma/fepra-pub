from __future__ import annotations


def test_comp_kb_layout():
    from tj import i18n
    from tjbot.handlers.competition import comp_kb
    for lang in ("ru", "en"):
        texts = [b.text for row in comp_kb(lang).keyboard for b in row]
        for key in ("btn.comp", "btn.comp_fill", "btn.back"):
            assert i18n.t(key, lang) in texts, (lang, key)


def test_comp_section_routes_both_langs():
    from tj import i18n
    from tjbot.handlers import menu
    variants = menu.btn_variants("btn.comp_section")
    assert i18n.t("btn.comp_section", "ru") in variants
    assert i18n.t("btn.comp_section", "en") in variants
