"""Движок программ: шаблоны, валидатор, резолвер, разворачивание формул, чек-ин."""
from __future__ import annotations

import copy
import importlib
import json
import sqlite3
from datetime import date

import pytest

from tj.services import program_engine as eng
from tjbot import db as botdb

TODAY = date(2026, 9, 28)


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    importlib.import_module("tj.migrations.0030_programs").upgrade(con)
    return con


def _user(con, uid=1, sex="m", bw=80):
    botdb.save_user(con, uid, nick="t", height_cm=180, weight_kg=bw, sex=sex, gym="Universe")


def _res(con, uid, disc, kg, day, reps=1):
    botdb.add_result(con, uid, disc, kg, "manual", day, reps=reps, est_1rm=kg)


# ------------------------------------------------------------------ шаблоны

def test_both_templates_valid():
    assert set(eng.template_slugs()) >= {"bulgarian-adaptation", "bulgarian-peak-8w"}
    for slug in ("bulgarian-adaptation", "bulgarian-peak-8w"):
        tpl = eng.load_template(slug)
        assert eng.template_errors(tpl) == []


def test_template_structure_matches_method():
    a = eng.load_template("bulgarian-adaptation")
    assert len(a["weeks"]) == 12
    days = [len(w["sessions"]) for w in a["weeks"]]
    assert days[0] == 3 and max(days) == 5 and days[:3] == [3, 3, 3]      # 3 дня на старте, потом рост частоты
    assert any(w["type"] == "deload" for w in a["weeks"])
    p = eng.load_template("bulgarian-peak-8w")
    types = [w["type"] for w in p["weeks"]]
    assert len(types) == 8 and types.count("volume") == 1 and types.count("medium") == 5 and types.count("high") == 2
    last = p["weeks"][-1]["sessions"][-1]
    assert last["kind"] == "test"
    steps = [st for b in last["blocks"] for ex in b["exercises"] for st in ex["steps"]]
    assert any(st.get("ladder", [0])[-1] == 95 for st in steps if "ladder" in st)
    assert any("attempts" in st and st["attempts"][0] == 100 for st in steps)
    for tpl in (a, p):                     # присед в каждой неделе, тяги не нужны
        for w in tpl["weeks"]:
            lifts = {ex["lift"] for s in w["sessions"] for b in s["blocks"] for ex in b["exercises"]}
            assert "back_squat" in lifts, (tpl["slug"], w["week"])
            assert not lifts & {"snatch_pull", "clean_pull", "deadlift"}
        for w in tpl["weeks"]:
            for s in w["sessions"]:
                assert 30 <= s["minutes"] <= 60


def test_bilingual_text_everywhere():
    for slug in ("bulgarian-adaptation", "bulgarian-peak-8w"):
        t = eng.load_template(slug)
        for key in ("title", "summary"):
            assert t[key]["ru"] and t[key]["en"]
        for w in t["weeks"]:
            assert w["title"]["ru"] and w["title"]["en"]
            for s in w["sessions"]:
                assert s["title"]["ru"] and s["title"]["en"]


def test_validator_rejects_bad_templates():
    good = eng.load_template("bulgarian-adaptation")

    def bad(mut):
        t = copy.deepcopy(good)
        mut(t)
        return eng.template_errors(t)

    assert bad(lambda t: t.pop("rules"))
    assert bad(lambda t: t["rules"].update(on_miss="whatever"))
    assert bad(lambda t: t["weeks"][0].update(week=5))
    assert bad(lambda t: t["weeks"][0].update(type="wild"))
    assert bad(lambda t: t["weeks"][0]["sessions"][0].update(dow=9))
    assert bad(lambda t: t["weeks"][0]["sessions"][1].update(dow=0))            # дни по возрастанию
    ex = lambda t: t["weeks"][0]["sessions"][0]["blocks"][0]["exercises"][0]
    assert bad(lambda t: ex(t).update(lift="pull_up"))                            # не весовое / не объявлено
    assert bad(lambda t: ex(t)["steps"].append({"ladder": [50], "sets": 3}))      # два вида шага
    assert bad(lambda t: ex(t)["steps"].__setitem__(0, {"ladder": [500]}))         # процент вне диапазона
    assert bad(lambda t: ex(t).update(id=""))
    assert bad(lambda t: t["required_lifts"].append("unknown_lift"))
    with pytest.raises(eng.TemplateError):
        eng.validate_template({"schema": 1})
    with pytest.raises(eng.NotFound):
        eng.load_template("no-such-program")


def test_schema_file_exists_and_declares_required_keys():
    sch = json.loads((eng.PROGRAMS_DIR / "template.schema.json").read_text(encoding="utf-8"))
    for k in ("schema", "slug", "version", "title", "summary", "params", "required_lifts", "rules", "weeks"):
        assert k in sch["required"]
    assert eng.template_slugs() == ["bulgarian-adaptation", "bulgarian-peak-8w"]


# ------------------------------------------------------------------ округление, стартовый уровень

def test_round_kg():
    assert eng.round_kg(61.2) == 60 and eng.round_kg(61.3) == 62.5 and eng.round_kg(63.75) == 65
    assert eng.round_kg(46.24) == 45


def test_starter_example_80kg_male():
    assert eng.starter_options("squat_snatch", "m", 80) == {"careful": 34, "normal": 48, "experienced": 66}
    f = eng.starter_options("squat_snatch", "f", 60)
    assert f["careful"] < f["normal"] < f["experienced"]
    assert eng.starter_options("squat_snatch", None, 80) is None
    assert eng.starter_options("jerk", "m", 80) is None          # нет норматива


# ------------------------------------------------------------------ резолвер, четыре ветви

def test_resolver_best_fresh_and_stale():
    con = _con()
    _user(con)
    _res(con, 1, "clean_and_jerk", 100, "2026-09-10")
    r = eng.resolve_reference(con, 1, "clean_and_jerk", TODAY)
    assert r["source"] == "best" and r["kg"] == 100 and r["stale"] is False
    _res(con, 1, "back_squat", 140, "2026-05-01")                 # старше 60 дней
    r = eng.resolve_reference(con, 1, "back_squat", TODAY)
    assert r["source"] == "best" and r["kg"] == 140 and r["stale"] is True
    _res(con, 1, "back_squat", 130, "2026-09-20")                 # свежий (ниже) результат вытесняет stale
    r = eng.resolve_reference(con, 1, "back_squat", TODAY)
    assert r["kg"] == 130 and r["stale"] is False


def test_resolver_uses_real_weight_not_epley():
    con = _con()
    _user(con)
    botdb.add_result(con, 1, "clean_and_jerk", 100, "manual", "2026-09-20", reps=3, est_1rm=110)
    assert eng.resolve_reference(con, 1, "clean_and_jerk", TODAY)["kg"] == 100


def test_resolver_derived():
    con = _con()
    _user(con)
    _res(con, 1, "clean_and_jerk", 100, "2026-09-20")
    ss = eng.resolve_reference(con, 1, "squat_snatch", TODAY)
    assert ss["source"] == "derived" and ss["kg"] == 80 and ss["from"] == ["clean_and_jerk"]
    ps = eng.resolve_reference(con, 1, "power_snatch", TODAY)          # через два шага: 0.8 * 0.8 * 100 = 64 -> 65
    assert ps["source"] == "derived" and ps["kg"] == 65 and ps["from"] == ["clean_and_jerk", "squat_snatch"]
    assert eng.resolve_reference(con, 1, "jerk", TODAY)["kg"] == 100
    assert eng.resolve_reference(con, 1, "clean_floor", TODAY)["kg"] == 90
    _res(con, 1, "back_squat", 120, "2026-09-20")
    assert eng.resolve_reference(con, 1, "front_squat", TODAY)["kg"] == 102.5     # 0.85 * 120 = 102 -> 102.5
    assert eng.resolve_reference(con, 1, "squat_snatch", TODAY)["kg"] == 80
    assert set(eng.DERIVE["squat_snatch"][0]) == {"clean_and_jerk", 0.80}


def test_resolver_derived_inherits_stale():
    con = _con()
    _user(con)
    _res(con, 1, "clean_and_jerk", 100, "2026-01-10")
    r = eng.resolve_reference(con, 1, "squat_snatch", TODAY)
    assert r["source"] == "derived" and r["stale"] is True


def test_resolver_needs_input_and_starter():
    con = _con()
    _user(con)
    r = eng.resolve_reference(con, 1, "squat_snatch", TODAY)
    assert r["source"] == "needs_input" and r["kg"] is None
    assert r["options"] == {"careful": 34, "normal": 48, "experienced": 66}
    assert "рывок" in r["question"]["ru"].lower() and r["question"]["en"]
    s = eng.resolve_reference(con, 1, "squat_snatch", TODAY, level="normal")
    assert s["source"] == "starter" and s["kg"] == 48 and s["level"] == "normal"
    with pytest.raises(eng.ProgramError):
        eng.resolve_reference(con, 1, "squat_snatch", TODAY, level="crazy")


def test_resolver_needs_input_without_profile():
    con = _con()
    r = eng.resolve_reference(con, 77, "squat_snatch", TODAY)
    assert r["source"] == "needs_input" and r["options"] is None
    assert eng.resolve_reference(con, 77, "squat_snatch", TODAY, level="normal")["source"] == "needs_input"


# ------------------------------------------------------------------ разворачивание и чек-ин

SPEC = {"blocks": [{"title": {"ru": "a", "en": "a"}, "exercises": [
    {"id": "sn", "lift": "squat_snatch", "name": {"ru": "Р", "en": "S"},
     "steps": [{"ladder": [50, 60, 70, {"pct": 75, "reps": 2}], "reps": 1},
               {"day_max": {"pct": 80, "tries": 2}}]},
    {"id": "sq", "lift": "back_squat", "name": {"ru": "П", "en": "B"},
     "steps": [{"pct": 70, "sets": 3, "reps": 5}]},
    {"id": "fs", "lift": "front_squat", "name": {"ru": "Ф", "en": "F"},
     "steps": [{"load": {"lift": "back_squat", "pct": 60, "rounding": 5}, "sets": 1, "reps": 3}]}]}]}
BASES = {"squat_snatch": {"kg": 90}, "back_squat": {"kg": 130}, "front_squat": {"kg": 105}}


def test_expand_formulas_and_rounding():
    sets = eng.expand_session(SPEC, BASES, "sess")
    kgs = [(s["exercise"], s["kind"], s["planned_kg"], s["reps"]) for s in sets]
    assert kgs[:4] == [("sn", "ladder", 45, 1), ("sn", "ladder", 55, 1), ("sn", "ladder", 62.5, 1), ("sn", "ladder", 67.5, 2)]
    assert [k for k in kgs if k[1] == "day_max"] == [("sn", "day_max", 72.5, 1)] * 2
    assert [k[2] for k in kgs if k[0] == "sq"] == [90, 90, 90]           # 0.7 * 130 = 91 -> 90
    assert [k[2] for k in kgs if k[0] == "fs"] == [80]                   # 60% от back_squat, шаг 5: 78 -> 80
    assert len({s["id"] for s in sets}) == len(sets)
    assert sets == eng.expand_session(SPEC, BASES, "sess")               # детерминированно
    assert eng.expand_session(SPEC, {}, "sess")[0]["planned_kg"] is None


def test_expand_bar_floor_and_attempts_monotonic():
    spec = {"blocks": [{"title": {"ru": "a", "en": "a"}, "exercises": [
        {"id": "sn", "lift": "squat_snatch", "name": {"ru": "Р", "en": "S"},
         "steps": [{"ladder": [50]}, {"attempts": [100, 103, 106]}]}]}]}
    s = eng.expand_session(spec, {"squat_snatch": {"kg": 30}}, "x")
    assert s[0]["planned_kg"] == 20                                       # не ниже грифа
    att = [x["planned_kg"] for x in s if x["kind"] == "attempt"]
    assert att == [30, 32.5, 35]                                          # каждая попытка минимум на 2.5 тяжелее


def test_checkin_rules():
    c = eng.checkin_adjust
    assert c({})["level"] == "none" and c({})["why"] is None
    assert c({"energy": 4})["level"] == "none"
    tired = c({"tired": True})
    assert tired["level"] == "minus5" and tired["delta_pct"] == -5 and "устал" in tired["why"]
    assert c({"joint": True})["delta_pct"] == -5
    assert c({"ill": True})["delta_pct"] == -10
    cap = c({"tired": True, "sleepy": True})
    assert cap["level"] == "cap" and cap["cap_pct"] == 70 and "70%" in cap["why"]
    assert c({"tired": True, "energy": 1})["level"] == "cap"
    assert c({"joint": True, "ill": True, "sleepy": True})["level"] == "cap"
    assert c({"tired": True}, {"deload_pct": 65}, "normal")["level"] == "minus5"
    t = c({"tired": True, "sleepy": True}, kind="test")
    assert t["level"] == "none" and t["postpone_advised"] and t["cap_pct"] is None
    assert tired["why_en"] and cap["why_en"]


def test_expand_with_adjust():
    minus5 = eng.checkin_adjust({"tired": True})
    sets = eng.expand_session(SPEC, BASES, "s", adjust=minus5)
    assert [s["planned_kg"] for s in sets if s["exercise"] == "sq"] == [85, 85, 85]    # 65% от 130 = 84.5 -> 85
    cap = eng.checkin_adjust({"tired": True, "sleepy": True})
    sets = eng.expand_session(SPEC, BASES, "s", adjust=cap)
    assert max(s["eff_pct"] for s in sets) == 70


def test_apply_miss_helper():
    sets = eng.expand_session(SPEC, BASES, "s")
    failed = sets[2]
    changed = eng.apply_miss(sets, failed)
    assert changed and sets[3]["planned_kg"] == 62.5      # было 67.5
    assert sets[0]["planned_kg"] == 45                    # выше по сессии не трогаем


def test_rest_sec_in_templates_and_expansion():
    for slug in ("bulgarian-adaptation", "bulgarian-peak-8w"):
        tpl = eng.load_template(slug)
        for w in tpl["weeks"]:
            for s in w["sessions"]:
                for b in s["blocks"]:
                    for ex in b["exercises"]:
                        assert all("rest_sec" in st for st in ex["steps"]), (slug, w["week"])
    sets = eng.expand_session(SPEC, BASES, "s")
    assert all(isinstance(x["rest_sec"], int) and x["rest_sec"] > 0 for x in sets)      # умолчания
    assert sets[0]["rest_sec"] == 60 and eng.default_rest_sec("attempt", 100) == 240
    spec = json.loads(json.dumps(SPEC))
    spec["blocks"][0]["exercises"][0]["steps"][0]["rest_sec"] = [10, 20, 30, 40]
    assert [x["rest_sec"] for x in eng.expand_session(spec, BASES, "s")[:4]] == [10, 20, 30, 40]


def test_validator_rest_sec():
    t = eng.load_template("bulgarian-adaptation")
    st = t["weeks"][0]["sessions"][0]["blocks"][0]["exercises"][0]["steps"][0]
    st["rest_sec"] = [60]
    assert eng.template_errors(t)
    st["rest_sec"] = 5000
    assert eng.template_errors(t)
