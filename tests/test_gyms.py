from __future__ import annotations
import sqlite3
from tj import i18n
from tjbot import db as botdb
from tjbot.handlers import admin, onboarding


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def _user(con, tg_id, gym):
    botdb.save_user(con, tg_id, nick=f"u{tg_id}", height_cm=180, weight_kg=80,
                    sex="m", age=30, gym=gym)


def test_init_schema_seeds_universe_default():
    con = _con()
    gyms = botdb.list_gyms(con)
    assert [g["name"] for g in gyms] == ["Universe"]
    assert gyms[0]["is_default"] == 1
    botdb.init_schema(con)
    assert len(botdb.list_gyms(con)) == 1


def test_add_gym_and_order():
    con = _con()
    botdb.add_gym(con, "Берлога")
    botdb.add_gym(con, "Atlant")
    assert [g["name"] for g in botdb.list_gyms(con)] == ["Universe", "Atlant", "Берлога"]


def test_gym_exists_case_insensitive():
    con = _con()
    assert botdb.gym_exists(con, "universe")
    assert botdb.gym_exists(con, "UNIVERSE")
    botdb.add_gym(con, "Берлога")
    assert botdb.gym_exists(con, "берлога")
    assert not botdb.gym_exists(con, "Atlant")


def test_gym_name_validation():
    con = _con()
    assert admin._gym_name_error(con, "") == "admin.gym_name_invalid"
    assert admin._gym_name_error(con, "a\nb") == "admin.gym_name_invalid"
    assert admin._gym_name_error(con, "х" * 26) == "admin.gym_name_too_long"
    assert admin._gym_name_error(con, "💪" * 16) == "admin.gym_name_too_long"
    assert admin._gym_name_error(con, "other") == "admin.gym_name_reserved"
    assert admin._gym_name_error(con, "Solo") == "admin.gym_name_reserved"
    assert admin._gym_name_error(con, "universe") == "admin.gym_exists"
    assert admin._gym_name_error(con, "Берлога") is None
    assert admin._gym_name_error(con, "х" * 25) is None


def test_gyms_text_counts_members():
    con = _con()
    botdb.add_gym(con, "Берлога")
    _user(con, 1, "Universe")
    _user(con, 2, "Universe")
    _user(con, 3, "solo")
    text = admin._gyms_text(con, "ru")
    assert "Universe - 2" in text
    assert "Берлога - 0" in text
    assert "solo" not in text


def test_onboarding_gym_kb_dynamic():
    con = _con()
    botdb.add_gym(con, "Берлога")
    kb = onboarding._gym_kb(con, "ru")
    btns = [b for row in kb.inline_keyboard for b in row]
    assert btns[0].callback_data == "gym:Universe"
    assert "по умолчанию" in btns[0].text
    assert btns[1].callback_data == "gym:Берлога"
    assert btns[1].text == "Берлога"
    assert btns[-2].callback_data == "gym:other"
    assert btns[-1].callback_data == "gym:solo"


def test_admin_kb_has_gyms_button():
    texts = [b.text for row in admin.admin_kb().keyboard for b in row]
    assert i18n.t("btn.admin_gyms", "ru") in texts


def test_register_builds_handlers():
    captured = []

    class App:
        def add_handler(self, h):
            captured.append(h)

    admin.register(App())
    assert len(captured) == 13
