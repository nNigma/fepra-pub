"""tj.services.profile: валидация, профиль, онбординг, правило «один источник часов»."""
import pytest

from p5a_env import p5a  # noqa: F401
from tj.services import auth, profile as pf
from tjbot import db as botdb


def test_validate_ok_normalizes(p5a):
    c = pf.validate_fields(p5a.con, {"nick": "  Ник ", "height_cm": "180", "weight_kg": "80,5",
                                     "sex": "f", "age": 30, "gym": "solo", "lang": "en",
                                     "goal": "bulk", "city": " Казань ", "astro": True})
    assert c == {"nick": "Ник", "height_cm": 180, "weight_kg": 80.5, "sex": "f", "age": 30,
                 "gym": "solo", "lang": "en", "goal": "bulk", "city": "Казань", "astro": True}


@pytest.mark.parametrize("field,bad", [
    ("nick", ""), ("nick", "x" * 41), ("height_cm", 99), ("height_cm", 251), ("height_cm", "abc"),
    ("height_cm", True), ("height_cm", 180.5), ("weight_kg", "тяжёлый"), ("weight_kg", 5),
    ("sex", "x"), ("age", 9), ("age", 101), ("gym", "Нет такого"), ("lang", "de"),
    ("goal", "fly"), ("city", "  "), ("astro", "yes"), ("bogus", 1)])
def test_validate_rejects(p5a, field, bad):
    with pytest.raises(pf.ProfileError) as e:
        pf.validate_fields(p5a.con, {field: bad})
    assert field in e.value.errors


def test_validate_boundaries(p5a):
    pf.validate_fields(p5a.con, {"height_cm": 100, "age": 10})
    pf.validate_fields(p5a.con, {"height_cm": 250, "age": 100})


def test_validate_collects_all_errors(p5a):
    with pytest.raises(pf.ProfileError) as e:
        pf.validate_fields(p5a.con, {"height_cm": 5, "age": 5})
    assert set(e.value.errors) == {"height_cm", "age"}


def test_gym_from_list(p5a):
    botdb.add_gym(p5a.con, "Другой")
    assert pf.validate_fields(p5a.con, {"gym": "Другой"}) == {"gym": "Другой"}


def test_get_profile_missing_and_full(p5a):
    assert pf.get_profile(p5a.con, 42) is None
    p5a.user(42, "Вася")
    p = pf.get_profile(p5a.con, 42)
    assert p["nick"] == "Вася" and p["height_cm"] == 180 and p["lang"] == "ru"
    assert p["goal"] == "maintain" and p["astro"] is False and p["city"] == "Москва"
    assert p["available_watch_actions"] == ["garmin_connect", "samsung_connect",
                                            "whoop_connect", "apple_connect"]


def test_update_profile_partial_keeps_created_at(p5a):
    p5a.user(42, "Вася")
    before = pf.get_profile(p5a.con, 42)
    p = pf.update_profile(p5a.con, 42, {"height_cm": 190, "goal": "cut", "astro": True})
    assert (p["height_cm"], p["goal"], p["astro"]) == (190, "cut", True)
    assert p["nick"] == "Вася" and p["weight_kg"] == 80.0 and p["created_at"] == before["created_at"]
    assert p["updated_at"]


def test_update_invalid_changes_nothing(p5a):
    p5a.user(42, "Вася")
    with pytest.raises(pf.ProfileError):
        pf.update_profile(p5a.con, 42, {"height_cm": 190, "age": 5})
    assert pf.get_profile(p5a.con, 42)["height_cm"] == 180


def test_update_creates_missing_row_needs_nick(p5a):
    with pytest.raises(pf.ProfileError):
        pf.update_profile(p5a.con, 7, {"age": 30})
    p = pf.update_profile(p5a.con, 7, {"nick": "Новый", "age": 30})
    assert p["nick"] == "Новый" and p["age"] == 30


def test_onboarding_status(p5a):
    uid = auth.create_web_user(p5a.con, "Веб")
    s = pf.onboarding_status(p5a.con, uid)
    assert s["complete"] is False
    assert s["missing"] == ["height_cm", "weight_kg", "sex", "age", "gym"]
    assert s["optional_missing"] == ["watch"]
    pf.update_profile(p5a.con, uid, {"height_cm": 175, "weight_kg": 70, "sex": "f", "age": 25,
                                     "gym": "Universe"})
    assert pf.onboarding_status(p5a.con, uid)["complete"] is True
    assert pf.onboarding_status(p5a.con, 999)["missing"][0] == "nick"


def test_list_gyms(p5a):
    p5a.user(1, gym="Universe")
    g = pf.list_gyms(p5a.con)
    assert g["gyms"][0] == {"name": "Universe", "is_default": True, "members": 1}
    assert g["special"] == ["solo", "other"]


def _w(garmin=None, sam=False, whoop=False, apple=False):
    return {"watch": {"garmin": garmin, "samsung": sam, "whoop": whoop, "apple": apple}}


def test_watch_actions_none():
    assert pf.available_watch_actions(_w()) == ["garmin_connect", "samsung_connect",
                                                "whoop_connect", "apple_connect"]
    assert pf.available_watch_actions({}) == pf.available_watch_actions(_w())


def test_watch_actions_garmin_ok_and_expired():
    assert pf.available_watch_actions(_w({"status": "ok"})) == [
        "garmin_sync", "garmin_history", "garmin_disconnect"]
    assert pf.available_watch_actions(_w({"status": "expired"})) == [
        "garmin_connect", "garmin_sync", "garmin_history", "garmin_disconnect"]


@pytest.mark.parametrize("kw,expected", [
    ({"sam": True}, ["samsung_disconnect"]),
    ({"whoop": True}, ["whoop_sync", "whoop_disconnect"]),
    ({"apple": True}, ["apple_disconnect"]),
])
def test_watch_actions_single_source(kw, expected):
    assert pf.available_watch_actions(_w(**kw)) == expected


def test_watch_state_from_db(p5a):
    p5a.user(5)
    botdb.garmin_account_set(p5a.con, 5, "a@b.c", "expired")
    p = pf.get_profile(p5a.con, 5)
    assert p["watch"]["garmin"] == {"status": "expired"}
    assert "garmin_connect" in p["available_watch_actions"] and "whoop_connect" not in p["available_watch_actions"]
    assert pf.onboarding_status(p5a.con, 5)["optional_missing"] == []
