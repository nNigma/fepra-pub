"""Промпт и payload ИИ-разбора питания."""
import json

from tj.analysis import llm_coach
from tjbot import db as botdb
from tjapp import api as apimod


def test_sys_nutrition_registered():
    assert "nutr_day" in llm_coach._SYS_BY_KIND
    assert "nutr_week" in llm_coach._SYS_BY_KIND
    ru = llm_coach._SYS_BY_KIND["nutr_week"]("ru", False)
    en = llm_coach._SYS_BY_KIND["nutr_week"]("en", False)
    assert "ИТОГ" in ru and "продукт" in ru.lower()
    assert "TAKEAWAY" in en
    assert not any("а" <= c.lower() <= "я" for c in en)


def test_sys_nutrition_astro_addendum():
    plain = llm_coach._SYS_BY_KIND["nutr_day"]("ru", False)
    astro = llm_coach._SYS_BY_KIND["nutr_day"]("ru", True)
    assert "Астро-разбор от Месье Клода" in astro
    assert "\nГадание" in astro
    assert "Месье Клода" not in plain
    en = llm_coach._SYS_BY_KIND["nutr_day"]("en", True)
    assert "\nFortune" in en and "TAKEAWAY" in en


def _setup(tmp_path):
    dbp = tmp_path / "t.db"
    con = botdb.connect(dbp)
    botdb.init_schema(con)
    botdb.save_user(con, 1, nick="ник", height_cm=183, weight_kg=78,
                    sex="m", gym="дом", age=36)
    botdb.set_goal(con, 1, "cut")
    con.execute(
        'INSERT INTO activities ("tg_id","day","sport","activity_id","source",'
        '"calories","extra") VALUES (?,?,?,?,?,?,?)',
        (1, "2026-07-08", "run", "a1", "test", 300, json.dumps({})))
    con.commit()
    botdb.add_meal(con, 1, "2026-07-07", "2026-07-07T12:00:00",
                   [], {"kcal": 500, "protein_g": 30, "fat_g": 15, "carb_g": 50},
                   quality=1)
    botdb.add_meal(con, 1, "2026-07-08", "2026-07-08T12:00:00",
                   [], {"kcal": 600, "protein_g": 40, "fat_g": 20, "carb_g": 60},
                   quality=2)
    return con


def test_nutr_llm_payload_week(tmp_path):
    con = _setup(tmp_path)
    payload = apimod._nutr_llm_payload(con, 1, "2026-07-08", week=True)
    assert payload["period"] == "week"
    assert payload["goal"] == "cut"
    assert payload["targets"]["kcal"]
    assert len(payload["days"]) == 2
    day = payload["days"][0]
    assert "totals" in day and "verdict" in day and "water_target_l" in day
    assert payload["workouts"]
    assert payload["logged_days"] == 2
    con.close()


def test_nutr_llm_payload_day_with_meal(tmp_path):
    con = _setup(tmp_path)
    payload = apimod._nutr_llm_payload(con, 1, "2026-07-08", week=False)
    assert payload is not None
    assert payload["period"] == "day"
    assert len(payload["days"]) == 1
    assert payload["days"][0]["totals"]["kcal"] == 600
    con.close()


def test_nutr_llm_payload_day_no_meals(tmp_path):
    con = _setup(tmp_path)
    assert apimod._nutr_llm_payload(con, 1, "2026-07-05", week=False) is None
    con.close()


def test_sys_summary_has_all_sections():
    ru = llm_coach._SYS_BY_KIND["summary"]("ru", False)
    for h in ("Куда идёт форма", "Оценка месяца", "Риски и куда дальше", "Питание"):
        assert h in ru, h
    assert "СОВЕТ" in ru
    en = llm_coach._SYS_BY_KIND["summary"]("en", False)
    for h in ("fitness is heading", "Month", "Risks", "Nutrition"):
        assert h in en, h
    assert not any("а" <= c.lower() <= "я" for c in en)
