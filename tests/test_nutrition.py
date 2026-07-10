"""Питание: parse_meal (валидация), meals CRUD, дневные/недельные тоталы."""
from __future__ import annotations

import json

from tj import llm
from tjbot import db as botdb
from tjbot import vision


def _llm_meal(foods=None, question=None, confidence="high"):
    return json.dumps({
        "foods": foods if foods is not None else [
            {"name": "гречка отварная", "grams": 250, "kcal": 275,
             "protein_g": 10, "fat_g": 2, "carb_g": 57},
            {"name": "куриная грудка", "grams": 150, "kcal": 248,
             "protein_g": 46.5, "fat_g": 5.4, "carb_g": 0},
        ],
        "confidence": confidence, "question": question}, ensure_ascii=False)


def test_parse_meal_happy(monkeypatch):
    captured = {}

    def _vision(image_bytes, prompt, *, media_type="image/jpeg", engine="gemini", **k):
        captured["engine"] = engine
        captured["prompt"] = prompt
        return _llm_meal(question="Каша на молоке или воде?")

    monkeypatch.setattr(vision.llm, "vision", _vision)
    out = vision.parse_meal(b"img", engine="claude")
    assert captured["engine"] == "claude"
    assert len(out["foods"]) == 2
    assert out["totals"]["kcal"] == 523.0          # тоталы пересчитаны сервером
    assert out["totals"]["protein_g"] == 56.5
    assert out["question"].startswith("Каша")
    assert out["confidence"] == "high"


def test_parse_meal_correction_in_prompt(monkeypatch):
    captured = {}

    def _vision(image_bytes, prompt, **k):
        captured["prompt"] = prompt
        return _llm_meal()

    monkeypatch.setattr(vision.llm, "vision", _vision)
    vision.parse_meal(b"img", correction="это 2 яйца, не 3")
    assert "2 яйца" in captured["prompt"]


def test_parse_meal_rejects_garbage(monkeypatch):
    monkeypatch.setattr(vision.llm, "vision", lambda *a, **k: "не json")
    assert vision.parse_meal(b"img") is None
    monkeypatch.setattr(vision.llm, "vision",
                        lambda *a, **k: json.dumps({"foods": []}))
    assert vision.parse_meal(b"img") is None
    # блюдо без kcal — отбрасываем весь ответ
    monkeypatch.setattr(vision.llm, "vision", lambda *a, **k: json.dumps(
        {"foods": [{"name": "суп", "grams": 300}]}))
    assert vision.parse_meal(b"img") is None
    # монструозная калорийность — мусор
    monkeypatch.setattr(vision.llm, "vision", lambda *a, **k: _llm_meal(
        foods=[{"name": "x", "grams": 1, "kcal": 99999,
                "protein_g": 1, "fat_g": 1, "carb_g": 1}]))
    assert vision.parse_meal(b"img") is None


def test_meals_crud_and_totals(tmp_path):
    con = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(con)
    foods = [{"name": "овсянка", "grams": 300, "kcal": 210,
              "protein_g": 7, "fat_g": 4, "carb_g": 36}]
    t1 = {"kcal": 210, "protein_g": 7, "fat_g": 4, "carb_g": 36}
    mid = botdb.add_meal(con, 111, "2026-07-09", "2026-07-09T08:30:00", foods, t1,
                         photo_id="ph1", engine="claude")
    botdb.add_meal(con, 111, "2026-07-09", "2026-07-09T13:00:00", foods,
                   {"kcal": 520, "protein_g": 45, "fat_g": 18, "carb_g": 40})
    botdb.add_meal(con, 111, "2026-07-08", "2026-07-08T19:00:00", foods, t1)
    botdb.add_meal(con, 222, "2026-07-09", "2026-07-09T09:00:00", foods, t1)

    meals = botdb.meals_for_day(con, 111, "2026-07-09")
    assert len(meals) == 2 and meals[0]["foods"][0]["name"] == "овсянка"
    week = botdb.nutrition_days(con, 111, days=7, upto_day="2026-07-09")
    assert [w["day"] for w in week] == ["2026-07-09", "2026-07-08"]
    assert week[0]["kcal"] == 730 and week[0]["meals"] == 2
    # чужие приёмы не текут
    assert len(botdb.meals_for_day(con, 222, "2026-07-09")) == 1
    assert botdb.delete_meal(con, 111, mid) is True
    assert botdb.delete_meal(con, 111, mid) is False
    con.close()


def test_meal_module_shape():
    from tjbot.handlers import meal
    assert callable(meal.register)
    assert meal.nutrition_kb("ru") is not None


def test_water_crud(tmp_path):
    con = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(con)
    assert botdb.water_for_day(con, 111, "2026-07-09") == 0.0
    assert botdb.add_water(con, 111, "2026-07-09", 0.25) == 0.25
    assert botdb.add_water(con, 111, "2026-07-09", 0.5) == 0.75
    assert botdb.add_water(con, 111, "2026-07-09", -0.25) == 0.5
    assert botdb.add_water(con, 111, "2026-07-09", -5) == 0.0    # не уходит в минус
    assert botdb.water_for_day(con, 222, "2026-07-09") == 0.0    # изоляция юзеров
    con.close()


def test_day_totals_and_advice():
    from tj.analysis import nutrition as nutr
    meals = [{"kcal": 1800, "protein_g": 80, "fat_g": 60, "carb_g": 190,
              "foods": [{"fiber_g": 8, "sugar_g": 90, "sodium_mg": 1500,
                         "iron_mg": 6, "calcium_mg": 400, "magnesium_mg": 150,
                         "potassium_mg": 1800}]}]
    t = nutr.day_totals(meals)
    assert t["kcal"] == 1800 and t["fiber_g"] == 8 and t["sugar_g"] == 90
    advice = nutr.day_advice(t, water_l=1.0, weight_kg=78.0, lang="ru")
    joined = " ".join(advice)
    assert "белка" in joined.lower() or "Мало белка" in joined   # 1.03 г/кг
    assert any("клетчатк" in a.lower() for a in advice)
    assert len(advice) <= 4
    assert nutr.day_advice({}, 1.0, 78.0) == []                  # пустой день — молчим


def test_period_summary():
    from tj.analysis import nutrition as nutr
    rows = [{"day": "2026-07-09", "kcal": 2000, "protein_g": 150},
            {"day": "2026-07-08", "kcal": 2400, "protein_g": 130}]
    s = nutr.period_summary(rows, {"2026-07-09": 2.0}, weight_kg=78.0)
    assert s["days"] == 2 and s["avg_kcal"] == 2200
    assert s["avg_protein_per_kg"] == round(140 / 78, 2)
    adv = nutr.period_advice(s, "ru")
    assert any("2" in a for a in adv)                            # мало дней записано


def test_period_summary_vs_targets():
    from tj.analysis import nutrition as nutr
    days = [{"day": "2026-07-07", "kcal": 2000, "protein_g": 120},
            {"day": "2026-07-08", "kcal": 2200, "protein_g": 140}]
    s = nutr.period_summary(days, {}, 78.0, targets={"kcal": 2361, "protein_g": 172})
    assert s["target_kcal"] == 2361
    assert s["target_protein_g"] == 172


def test_period_summary_no_targets():
    from tj.analysis import nutrition as nutr
    days = [{"day": "2026-07-07", "kcal": 2000, "protein_g": 120}]
    s = nutr.period_summary(days, {}, 78.0)
    assert s["target_kcal"] is None and s["target_protein_g"] is None


def test_day_verdict_weighted_by_kcal():
    from tj.analysis import nutrition as nutr
    meals = [{"kcal": 500, "quality": 1}, {"kcal": 1700, "quality": 4}, {"kcal": 300, "quality": 2}]
    assert nutr.day_verdict(meals) == 3


def test_day_verdict_none_without_quality():
    from tj.analysis import nutrition as nutr
    assert nutr.day_verdict([{"kcal": 500}]) is None
    assert nutr.day_verdict([]) is None
    assert nutr.day_verdict(None) is None


def test_day_verdict_clamped():
    from tj.analysis import nutrition as nutr
    assert nutr.day_verdict([{"kcal": 100, "quality": 1}]) == 1
    assert nutr.day_verdict([{"kcal": 100, "quality": 4}]) == 4


def test_micro_week_flags_low_fiber():
    from tj.analysis import nutrition as nutr
    days = [{"day": f"2026-07-0{i}", "kcal": 2000, "fiber_g": 14} for i in range(1, 6)]
    flags = nutr.micro_week_flags(days)
    assert "fiber_g" in flags


def test_micro_week_flags_needs_min_days():
    from tj.analysis import nutrition as nutr
    days = [{"day": "2026-07-01", "kcal": 2000, "fiber_g": 5}] * 3
    assert nutr.micro_week_flags(days) == []


def test_micro_week_flags_sugar_over():
    from tj.analysis import nutrition as nutr
    days = [{"day": f"2026-07-0{i}", "kcal": 2000, "sugar_g": 90, "fiber_g": 30,
             "sodium_mg": 2000, "iron_mg": 8, "calcium_mg": 1000,
             "magnesium_mg": 400, "potassium_mg": 3500} for i in range(1, 6)]
    assert nutr.micro_week_flags(days) == ["sugar_g"]
