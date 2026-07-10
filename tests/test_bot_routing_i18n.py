from __future__ import annotations

from tjbot.handlers import menu


def test_btn_variants_gives_both_langs():
    v = menu.btn_variants("btn.record")
    assert "Записать тренировку" in v and "Log workout" in v


def test_all_variants_covers_menu_buttons():
    allv = menu.all_menu_variants()
    assert "📊 Аналитика" in allv and "📊 Analytics" in allv


def test_main_kb_labels_follow_lang():
    kb_ru = menu.main_kb(12345678, "ru")
    kb_en = menu.main_kb(12345678, "en")
    flat = lambda kb: [b.text for row in kb.keyboard for b in row]
    assert "Записать тренировку" in flat(kb_ru)
    assert "Log workout" in flat(kb_en)


import tjbot.db as db


def test_lang_picker_sets_explicit(tmp_path):
    con = db.connect(str(tmp_path / "t.db")); db.init_schema(con)
    db.save_user(con, 1, nick="a", height_cm=1, weight_kg=1, sex="m", gym="G")
    assert db.user_lang(con, 1) == "ru"
    db.set_lang(con, 1, "en")
    assert db.user_lang(con, 1) == "en"


def test_lang_kb_has_both_endonyms():
    texts = [b.text for row in menu.lang_kb("en").keyboard for b in row]
    assert menu.BTN_LANG_RU in texts and menu.BTN_LANG_EN in texts
