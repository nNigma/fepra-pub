"""Сервис программ: каталог, миграция, запись, расписание, сессии, чек-ин, on_miss, тест-сессия, финиш."""
from __future__ import annotations

import importlib
import json
import sqlite3
from datetime import date

import pytest

from tj.services import program_engine as eng
from tj.services import programs as P
from tjbot import db as botdb

TODAY = date(2026, 9, 28)          # понедельник
D = TODAY.isoformat()


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    importlib.import_module("tj.migrations.0030_programs").upgrade(con)
    return con


def _user(con, uid=1, sex="m", bw=80):
    botdb.save_user(con, uid, nick="t", height_cm=180, weight_kg=bw, sex=sex, gym="Universe")


def _res(con, uid, disc, kg, day="2026-09-20"):
    botdb.add_result(con, uid, disc, kg, "manual", day, reps=1, est_1rm=kg)


def _fresh_user(con, uid=1):
    """Атлет со свежими максами по всем обязательным лифтам -> без тест-сессии."""
    _user(con, uid)
    _res(con, uid, "squat_snatch", 80)
    _res(con, uid, "clean_and_jerk", 100)
    _res(con, uid, "back_squat", 140)


def _sets(view):
    return [s for b in view["blocks"] for ex in b["exercises"] for s in ex["sets"]]


def _session(con, enr_id, week, idx):
    r = con.execute("SELECT id FROM program_sessions WHERE enrollment_id=? AND week=? AND idx=?",
                    (enr_id, week, idx)).fetchone()
    return r["id"]


# ------------------------------------------------------------------ миграция и каталог

def test_migration_idempotent_and_tables():
    con = _con()
    mig = importlib.import_module("tj.migrations.0030_programs")
    n = con.execute("SELECT COUNT(*) FROM program_nodes").fetchone()[0]
    mig.upgrade(con)
    mig.upgrade(con)
    assert con.execute("SELECT COUNT(*) FROM program_nodes").fetchone()[0] == n == 18
    for t in ("program_nodes", "program_enrollments", "program_sessions", "set_log"):
        cols = {r["name"] for r in con.execute(f"PRAGMA table_info({t})")}
        assert "id" in cols
    assert {"template_slug", "sort", "status", "kind", "slug"} <= {r["name"] for r in con.execute("PRAGMA table_info(program_nodes)")}
    assert {"base_maxes", "level", "deleted_at", "template_version"} <= {r["name"] for r in con.execute("PRAGMA table_info(program_enrollments)")}
    assert {"plan", "checkin", "activity_id", "kind"} <= {r["name"] for r in con.execute("PRAGMA table_info(program_sessions)")}
    assert {"planned_kg", "done_kg", "ok", "deleted_at"} <= {r["name"] for r in con.execute("PRAGMA table_info(set_log)")}


def test_seed_updates_rows_without_duplicates():
    con = _con()
    con.execute("UPDATE program_nodes SET title_ru='X', status='hidden' WHERE slug='crossfit'")
    P.seed_catalog(con)
    r = con.execute("SELECT title_ru, status FROM program_nodes WHERE slug='crossfit'").fetchone()
    assert r["title_ru"] == "Кроссфит" and r["status"] == "planned"


def test_tree_shape():
    con = _con()
    roots = {n["slug"]: n for n in P.tree(con)}
    assert list(roots) == ["crossfit", "weightlifting", "running"]
    assert roots["crossfit"]["soon"] and roots["running"]["soon"] and not roots["weightlifting"]["soon"]
    assert len(roots["crossfit"]["children"]) == 7
    assert [c["slug"] for c in roots["running"]["children"]] == [
        "run-endurance", "run-speed", "run-half-marathon", "run-marathon", "run-intervals"]
    bg = roots["weightlifting"]["children"][0]
    assert bg["slug"] == "bulgarian" and bg["kind"] == "system" and bg["status"] == "active"
    assert [c["slug"] for c in bg["children"]] == ["bulgarian-adaptation", "bulgarian-peak-8w"]
    assert all(c["kind"] == "program" and c["template_slug"] == c["slug"] for c in bg["children"])
    con.execute("UPDATE program_nodes SET status='hidden' WHERE slug='run-speed'")
    assert "run-speed" not in [c["slug"] for c in {n["slug"]: n for n in P.tree(con)}["running"]["children"]] 


def test_get_program():
    con = _con()
    p = P.get_program(con, "bulgarian-peak-8w")
    assert p["template"]["version"] == 1 and len(p["template"]["weeks"]) == 8
    assert P.get_program(con, "running")["children"]
    assert "template" not in P.get_program(con, "run-speed")
    with pytest.raises(eng.NotFound):
        P.get_program(con, "nope")


# ------------------------------------------------------------------ запись на программу

def test_enroll_unavailable_and_missing():
    con = _con()
    _fresh_user(con)
    with pytest.raises(eng.Unavailable):
        P.enroll(con, 1, "run-speed", start_day=D, today=D)
    with pytest.raises(eng.NotFound):
        P.enroll(con, 1, "ghost", start_day=D, today=D)


def test_enroll_needs_input_lists_lifts():
    con = _con()
    _user(con)
    with pytest.raises(eng.NeedsInput) as ei:
        P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D)
    assert set(ei.value.items) >= {"squat_snatch", "clean_and_jerk", "back_squat"}
    assert ei.value.items["squat_snatch"]["options"]["normal"] == 48
    assert con.execute("SELECT COUNT(*) FROM program_enrollments").fetchone()[0] == 0   # ничего не записали


def test_enroll_fresh_maxes_no_test_and_schedule():
    con = _con()
    _fresh_user(con)
    e = P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D, enrollment_id="e-1")
    assert e["test_lifts"] == [] and e["sessions"]["total"] == 4 + 5 * 6 + 4
    assert e["base_maxes"]["clean_and_jerk"]["kg"] == 100 and e["base_maxes"]["clean_and_jerk"]["source"] == "best"
    assert e["base_maxes"]["front_squat"]["source"] == "derived"          # 0.85 * 140 = 119 -> 120
    days = [r["planned_day"] for r in con.execute(
        "SELECT planned_day FROM program_sessions WHERE enrollment_id='e-1' ORDER BY week, idx")]
    assert days == sorted(days) and len(set(days)) == len(days)
    # неделя 1 (пн 28.09): дни шаблона 0,1,3,4 -> пн, вт, чт, пт
    assert days[:4] == ["2026-09-28", "2026-09-29", "2026-10-01", "2026-10-02"]
    assert days[4] == "2026-10-05"
    # неделя 8: тест в субботу
    last = con.execute("SELECT * FROM program_sessions WHERE enrollment_id='e-1' ORDER BY week DESC, idx DESC").fetchone()
    assert last["kind"] == "test" and last["week"] == 8 and last["planned_day"] == "2026-11-21"


def test_enroll_mid_week_start_keeps_order_and_min_day():
    con = _con()
    _fresh_user(con)
    e = P.enroll(con, 1, "bulgarian-adaptation", start_day="2026-09-30", today=D, enrollment_id="e-2")   # среда
    days = [r["planned_day"] for r in con.execute(
        "SELECT planned_day FROM program_sessions WHERE enrollment_id='e-2' ORDER BY week, idx")]
    assert days[0] == "2026-09-30" and min(days) >= "2026-09-30"
    assert days == sorted(days) and len(set(days)) == len(days)
    assert e["sessions"]["total"] == len(days) == sum(
        len(w["sessions"]) for w in eng.load_template("bulgarian-adaptation")["weeks"])


def test_enroll_custom_weekdays():
    con = _con()
    _fresh_user(con)
    P.enroll(con, 1, "bulgarian-adaptation", start_day=D, today=D, enrollment_id="e-3", weekdays=[1, 3, 5])
    days = [date.fromisoformat(r["planned_day"]).weekday() for r in con.execute(
        "SELECT planned_day FROM program_sessions WHERE enrollment_id='e-3' AND week=1 ORDER BY idx")]
    assert days == [1, 3, 5]
    with pytest.raises(eng.ProgramError):
        P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D, weekdays=[9])


def test_enroll_idempotent_and_conflict():
    con = _con()
    _fresh_user(con)
    a = P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D, enrollment_id="same")
    b = P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D, enrollment_id="same")
    assert b["existing"] is True and a["id"] == b["id"]
    assert con.execute("SELECT COUNT(*) FROM program_sessions").fetchone()[0] == a["sessions"]["total"]
    with pytest.raises(eng.Conflict):
        P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D)          # вторая активная запись
    _user(con, 2)
    with pytest.raises(eng.Conflict):
        P.enroll(con, 2, "bulgarian-peak-8w", start_day=D, today=D, enrollment_id="same")
    P.enroll(con, 1, "bulgarian-adaptation", start_day=D, today=D)          # параллельно другая — можно


def test_enroll_user_bases_and_derivation_from_them():
    con = _con()
    _user(con)
    e = P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D, base_maxes={
        "clean_and_jerk": 100, "back_squat": {"kg": 130}, "squat_snatch": 82.5})
    assert e["base_maxes"]["squat_snatch"] == {**e["base_maxes"]["squat_snatch"], "kg": 82.5, "source": "user"}
    assert e["base_maxes"]["front_squat"]["kg"] == 110                       # 0.85 * 130 = 110.5 -> 110
    assert e["test_lifts"] == []                                              # заданные атлетом — не повод для теста
    with pytest.raises(eng.ProgramError):
        P.enroll(con, 1, "bulgarian-adaptation", start_day=D, today=D, base_maxes={"squat_snatch": -5})


def test_enroll_test_session_when_no_or_stale_maxes():
    con = _con()
    _user(con)
    e = P.enroll(con, 1, "bulgarian-peak-8w", start_day="2026-09-30", today=D, level="normal", enrollment_id="t1")
    assert set(e["test_lifts"]) == {"squat_snatch", "clean_and_jerk", "back_squat"}
    first = con.execute("SELECT * FROM program_sessions WHERE enrollment_id='t1' ORDER BY planned_day, week, idx").fetchone()
    assert first["kind"] == "test" and first["week"] == 0 and first["planned_day"] == "2026-09-30"
    w1 = con.execute("SELECT MIN(planned_day) d FROM program_sessions WHERE enrollment_id='t1' AND week=1").fetchone()["d"]
    assert w1 > "2026-09-30"
    v = P.get_session(con, 1, first["id"])
    lads = [s for s in _sets(v) if s["kind"] == "ladder"]
    assert len(lads) == 7 * 3 and [s["kind"] for s in _sets(v)].count("attempt") == 9
    # устаревший макс -> тоже тест
    con2 = _con()
    _user(con2)
    for d, kg in (("squat_snatch", 80), ("clean_and_jerk", 100), ("back_squat", 140)):
        _res(con2, 1, d, kg, "2026-03-01")
    e2 = P.enroll(con2, 1, "bulgarian-peak-8w", start_day=D, today=D)
    assert set(e2["test_lifts"]) == {"squat_snatch", "clean_and_jerk", "back_squat"}
    assert e2["base_maxes"]["squat_snatch"]["stale"] is True
    # часть максов свежая -> тест только по недостающим
    con3 = _con()
    _user(con3)
    _res(con3, 1, "clean_and_jerk", 100)
    _res(con3, 1, "back_squat", 140)
    e3 = P.enroll(con3, 1, "bulgarian-peak-8w", start_day=D, today=D)
    assert e3["test_lifts"] == ["squat_snatch"] and e3["base_maxes"]["squat_snatch"]["source"] == "derived"


# ------------------------------------------------------------------ сессия: план, чек-ин, on_miss

def _enrolled(con, eid="e"):
    _fresh_user(con)
    P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D, enrollment_id=eid)
    return eid


def test_plan_session_resolves_kg():
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 1, 1)
    v = P.plan_session(con, 1, sid, D)
    sn = next(ex for b in v["blocks"] for ex in b["exercises"] if ex["lift"] == "squat_snatch")
    kgs = [s["planned_kg"] for s in sn["sets"]]
    assert kgs[:2] == [40, 47.5]                        # 50% и 60% от 80 (48 -> 47.5)
    assert all(k % 2.5 == 0 for k in kgs) and kgs == sorted(kgs)
    n = con.execute("SELECT COUNT(*) FROM set_log WHERE session_id=?", (sid,)).fetchone()[0]
    assert n == len(_sets(v))
    v2 = P.plan_session(con, 1, sid, D)                  # повтор не плодит строки
    assert con.execute("SELECT COUNT(*) FROM set_log WHERE session_id=?", (sid,)).fetchone()[0] == n
    assert [s["id"] for s in _sets(v)] == [s["id"] for s in _sets(v2)]


def test_ownership_isolated():
    con = _con()
    eid = _enrolled(con)
    _user(con, 2)
    sid = _session(con, eid, 1, 1)
    with pytest.raises(eng.NotFound):
        P.get_session(con, 2, sid)
    with pytest.raises(eng.NotFound):
        P.get_enrollment(con, 2, eid)
    assert P.list_enrollments(con, 2) == []


def test_checkin_changes_weights_and_explains():
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 2, 1)
    base = [s["planned_kg"] for s in _sets(P.get_session(con, 1, sid))]
    v = P.submit_checkin(con, 1, sid, {"tired": True}, D)
    assert "устал" in v["why"] and v["why_en"]
    lowered = [s["planned_kg"] for s in _sets(v)]
    assert all(a <= b for a, b in zip(lowered, base)) and lowered != base
    v = P.submit_checkin(con, 1, sid, {"tired": True, "sleepy": True}, D)
    assert v["adjust"]["level"] == "cap" and "70%" in v["why"]
    bases = {"squat_snatch": 80, "clean_and_jerk": 100, "back_squat": 140, "front_squat": 120}
    for b in v["blocks"]:
        for ex in b["exercises"]:
            for s in ex["sets"]:
                assert s["planned_kg"] <= 0.7 * bases[ex["lift"]] + 1.25, (ex["lift"], s)   # потолок 70% (с округлением)
    v = P.submit_checkin(con, 1, sid, {}, D)              # чек-ин «всё хорошо» возвращает исходные веса
    assert [s["planned_kg"] for s in _sets(v)] == base and v["why"] is None
    with pytest.raises(eng.ProgramError):
        P.submit_checkin(con, 1, sid, {"energy": 9}, D)


def test_checkin_keeps_logged_sets_frozen():
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 2, 1)
    v = P.plan_session(con, 1, sid, D)
    base_kg = [s["planned_kg"] for s in _sets(v)]
    first = _sets(v)[0]
    P.log_set(con, 1, sid, first["id"], done_kg=first["planned_kg"], reps=1, ok=True)
    v = P.submit_checkin(con, 1, sid, {"ill": True}, D)
    assert _sets(v)[0]["planned_kg"] == first["planned_kg"]
    assert v["adjust"]["level"] == "illness" and _sets(v)[2]["planned_kg"] < base_kg[2]


def test_on_miss_drops_5kg_for_rest_of_lift_only():
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 3, 1)
    v = P.plan_session(con, 1, sid, D)
    sets = _sets(v)
    sn = [s for b in v["blocks"] for ex in b["exercises"] if ex["lift"] == "squat_snatch" for s in ex["sets"]]
    sq = [s for b in v["blocks"] for ex in b["exercises"] if ex["lift"] == "back_squat" for s in ex["sets"]]
    for s in sn[:3]:
        P.log_set(con, 1, sid, s["id"], done_kg=s["planned_kg"], reps=1, ok=True)
    r = P.log_set(con, 1, sid, sn[3]["id"], done_kg=sn[3]["planned_kg"], reps=1, ok=False)
    assert r["changed"] and r["why"] and "5" in r["why"]["ru"]
    v2 = P.get_session(con, 1, sid)
    sn2 = [s for b in v2["blocks"] for ex in b["exercises"] if ex["lift"] == "squat_snatch" for s in ex["sets"]]
    sq2 = [s for b in v2["blocks"] for ex in b["exercises"] if ex["lift"] == "back_squat" for s in ex["sets"]]
    assert [s["planned_kg"] for s in sn2[:4]] == [s["planned_kg"] for s in sn[:4]]         # отмеченные не меняются
    assert [s["planned_kg"] for s in sn2[4:]] == [s["planned_kg"] - 5 for s in sn[4:]]
    assert [s["planned_kg"] for s in sq2] == [s["planned_kg"] for s in sq]                  # другой лифт не тронут
    # идемпотентность: тот же PUT ещё раз не роняет вес второй раз
    r2 = P.log_set(con, 1, sid, sn[3]["id"], done_kg=sn[3]["planned_kg"], reps=1, ok=False)
    assert r2["changed"] == []
    assert [s["planned_kg"] for s in P.get_session(con, 1, sid)["blocks"][0]["exercises"][0]["sets"][4:]] == [s["planned_kg"] - 5 for s in sn[4:]]
    # второй промах — ещё −5
    P.log_set(con, 1, sid, sn2[4]["id"], done_kg=sn2[4]["planned_kg"], reps=1, ok=False)
    sn3 = [s for b in P.get_session(con, 1, sid)["blocks"] for ex in b["exercises"] if ex["lift"] == "squat_snatch" for s in ex["sets"]]
    assert sn3[5]["planned_kg"] == sn[5]["planned_kg"] - 10
    # исправление «не вышло» на «вышло» снимает поправку
    P.log_set(con, 1, sid, sn[3]["id"], done_kg=sn[3]["planned_kg"], reps=1, ok=True)
    sn4 = [s for b in P.get_session(con, 1, sid)["blocks"] for ex in b["exercises"] if ex["lift"] == "squat_snatch" for s in ex["sets"]]
    assert sn4[5]["planned_kg"] == sn[5]["planned_kg"] - 5
    assert P.get_session(con, 1, sid)["status"] == "in_progress"


def test_log_set_extra_and_validation_and_closed():
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 1, 1)
    with pytest.raises(eng.ProgramError):
        P.log_set(con, 1, sid, "client-uuid-1", done_kg=50)              # внеплановый без exercise
    P.log_set(con, 1, sid, "client-uuid-1", done_kg=50, reps=3, ok=True, exercise="back_squat", note="доп")
    v = P.get_session(con, 1, sid)
    assert [x["id"] for x in v["extra_sets"]] == ["client-uuid-1"] and v["extra_sets"][0]["note"] == "доп"
    with pytest.raises(eng.ProgramError):
        P.log_set(con, 1, sid, "client-uuid-1", done_kg=9999, exercise="back_squat")
    P.finish_session(con, 1, sid, today=D)
    with pytest.raises(eng.SessionClosed):
        P.log_set(con, 1, sid, "client-uuid-1", done_kg=60, exercise="back_squat")
    with pytest.raises(eng.SessionClosed):
        P.submit_checkin(con, 1, sid, {"tired": True}, D)


def test_today_session_states():
    con = _con()
    eid = _enrolled(con)
    t = P.today_session(con, 1, eid, D)
    assert t["state"] == "today" and t["session"]["planned_day"] == D
    t = P.today_session(con, 1, eid, "2026-09-27")
    assert t["state"] == "upcoming" and t["session"]["planned_day"] == D
    t = P.today_session(con, 1, eid, "2026-09-30")               # ср: сегодня нет, впереди чт
    assert t["state"] == "upcoming" and t["session"]["planned_day"] == "2026-10-01"
    t = P.today_session(con, 1, eid, "2027-06-01")
    assert t["state"] == "overdue"
    con.execute("UPDATE program_sessions SET status='done' WHERE enrollment_id=?", (eid,))
    assert P.today_session(con, 1, eid, D) == {"state": "none", "enrollment_id": eid, "date": D, "session": None}


# ------------------------------------------------------------------ финиш

def _log_all(con, sid, view=None, factor=1.0):
    v = view or P.plan_session(con, 1, sid, D)
    for s in _sets(v):
        P.log_set(con, 1, sid, s["id"], done_kg=s["planned_kg"] * factor, reps=s["reps"], ok=True)


def test_finish_records_activity_and_maxes_and_is_idempotent():
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 1, 1)
    v = P.plan_session(con, 1, sid, D)
    sn = [s for b in v["blocks"] for ex in b["exercises"] if ex["lift"] == "squat_snatch" for s in ex["sets"]]
    top = max(s["planned_kg"] for s in sn)
    _log_all(con, sid, v)
    aid = "0b9e6a20-1c9c-4f0a-9b32-2f3a1d8c5e11"
    r = P.finish_session(con, 1, sid, rpe=7, feel=4, activity_id=aid, today=D)
    assert r["status"] == "done" and r["already"] is False and r["activity_id"] == aid
    m = {x["lift"]: x for x in r["maxes"]}
    assert m["squat_snatch"]["kg"] == top and m["back_squat"]["kg"] > 0
    act = con.execute("SELECT * FROM activities WHERE tg_id=1 AND activity_id=?", (aid,)).fetchone()
    assert act["sport"] == "weightlifting" and act["source"] == "manual" and act["perf_rpe"] == 7
    ex = json.loads(act["extra"])
    assert ex["program"]["session_id"] == sid and ex["program"]["slug"] == "bulgarian-peak-8w" and ex["feel"] == 4
    assert "Рывок в сед" in ex["board_text"]
    auto = con.execute("SELECT discipline, value, source, activity_id FROM discipline_results WHERE tg_id=1 AND "
                       "activity_id=? ORDER BY discipline", (aid,)).fetchall()
    assert {a["discipline"] for a in auto} == {"squat_snatch", "back_squat"} and all(a["source"] == "auto" for a in auto)
    assert next(a for a in auto if a["discipline"] == "squat_snatch")["value"] == top
    # идемпотентность
    r2 = P.finish_session(con, 1, sid, rpe=9, activity_id="another-uuid", today="2026-10-05")
    assert r2["already"] is True and r2["activity_id"] == aid and r2["maxes"] == r["maxes"]
    assert con.execute("SELECT COUNT(*) FROM activities WHERE tg_id=1 AND sport='weightlifting'").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM discipline_results WHERE tg_id=1 AND source='auto'").fetchone()[0] == len(auto)
    s = con.execute("SELECT status, activity_id FROM program_sessions WHERE id=?", (sid,)).fetchone()
    assert s["status"] == "done" and s["activity_id"] == aid


def test_finish_default_activity_id_deterministic_and_ignores_misses():
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 1, 1)
    v = P.plan_session(con, 1, sid, D)
    sn = [s for b in v["blocks"] for ex in b["exercises"] if ex["lift"] == "squat_snatch" for s in ex["sets"]]
    for s in sn[:-1]:
        P.log_set(con, 1, sid, s["id"], done_kg=s["planned_kg"], reps=1, ok=True)
    P.log_set(con, 1, sid, sn[-1]["id"], done_kg=sn[-1]["planned_kg"] + 10, reps=1, ok=False)   # не вышло — в макс не идёт
    r = P.finish_session(con, 1, sid, today=D)
    assert {x["lift"]: x["kg"] for x in r["maxes"]}["squat_snatch"] == sn[-2]["planned_kg"]
    assert r["activity_id"] and len(r["activity_id"]) == 36
    with pytest.raises(eng.ProgramError):
        P.finish_session(con, 1, _session(con, eid, 1, 2), rpe=11, today=D)


def test_finish_empty_session_no_results():
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 1, 2)
    r = P.finish_session(con, 1, sid, today=D)
    assert r["maxes"] == [] and con.execute("SELECT COUNT(*) FROM discipline_results WHERE source='auto'").fetchone()[0] == 0


def test_refresh_suggestion_not_silent_and_refresh_base():
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 1, 1)
    v = P.plan_session(con, 1, sid, D)
    sn = [s for b in v["blocks"] for ex in b["exercises"] if ex["lift"] == "squat_snatch" for s in ex["sets"]]
    # рывок 80 -> тянем до 85 (новый макс +5)
    P.log_set(con, 1, sid, sn[0]["id"], done_kg=85, reps=1, ok=True)
    r = P.finish_session(con, 1, sid, today=D)
    assert [x["lift"] for x in r["refresh"]] == ["squat_snatch"]
    assert r["refresh"][0]["base_kg"] == 80 and r["refresh"][0]["new_kg"] == 85 and "Обновить" in r["refresh"][0]["ru"]
    assert P.get_enrollment(con, 1, eid)["base_maxes"]["squat_snatch"]["kg"] == 80     # молча не меняем
    e = P.refresh_base(con, 1, eid)
    assert e["base_maxes"]["squat_snatch"]["kg"] == 85 and e["refreshed"] == ["squat_snatch"]
    assert P.suggest_base_refresh(con, 1, eid) == []
    # +1 кг — не повод
    con2 = _con()
    eid2 = _enrolled(con2)
    sid2 = _session(con2, eid2, 1, 1)
    v = P.plan_session(con2, 1, sid2, D)
    P.log_set(con2, 1, sid2, _sets(v)[0]["id"], done_kg=81, reps=1, ok=True)
    assert P.finish_session(con2, 1, sid2, today=D)["refresh"] == []


def test_test_session_updates_bases_and_recomputes_weights():
    con = _con()
    _user(con)
    e = P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D, level="normal", enrollment_id="t")
    assert e["base_maxes"]["squat_snatch"]["source"] == "starter"
    assert e["base_maxes"]["front_squat"]["source"] == "starter"       # фронт тоже есть в нормативах
    tid = _session(con, "t", 0, 0)
    v = P.plan_session(con, 1, tid, D)
    lifts = {}
    for s in _sets(v):
        ex = next(x for b in v["blocks"] for x in b["exercises"] if any(y["id"] == s["id"] for y in x["sets"]))
        lifts.setdefault(ex["lift"], []).append(s)
    # рывок: лесенка выполнена, лучшая попытка 60; толчок 75; присед 110
    targets = {"squat_snatch": 60, "clean_and_jerk": 75, "back_squat": 110}
    for lift, ss in lifts.items():
        for s in ss:
            kg = min(s["planned_kg"], targets[lift]) if s["kind"] != "attempt" else (targets[lift] if s["n"] == 7 else None)
            if kg is not None:
                P.log_set(con, 1, tid, s["id"], done_kg=kg, reps=1, ok=True)
    before_plan = [x["planned_kg"] for x in _sets(P.get_session(con, 1, _session(con, "t", 1, 1)))]
    r = P.finish_session(con, 1, tid, today=D)
    assert set(r["base_updated"]) == {"squat_snatch", "clean_and_jerk", "back_squat"}
    b = P.get_enrollment(con, 1, "t")["base_maxes"]
    assert b["squat_snatch"] == {**b["squat_snatch"], "kg": 60, "source": "test"}
    assert b["clean_and_jerk"]["kg"] == 75 and b["back_squat"]["kg"] == 110
    assert b["front_squat"]["kg"] == 92.5 and b["front_squat"]["source"] == "derived"   # 0.85 * 110 = 93.5 -> 92.5
    assert r["refresh"] == []                                         # тест уже стал базой
    after_plan = [x["planned_kg"] for x in _sets(P.get_session(con, 1, _session(con, "t", 1, 1)))]
    assert after_plan != before_plan                                   # остальные веса пересчитались
    assert P.get_session(con, 1, tid)["status"] == "done"
    assert eng.resolve_reference(con, 1, "squat_snatch", D)["kg"] == 60


def test_enrollment_done_after_last_session():
    con = _con()
    eid = _enrolled(con)
    con.execute("UPDATE program_sessions SET status='skipped' WHERE enrollment_id=? AND NOT (week=1 AND idx=1)", (eid,))
    r = P.finish_session(con, 1, _session(con, eid, 1, 1), today=D)
    assert r["enrollment_done"] is True and P.get_enrollment(con, 1, eid)["status"] == "done"
    P.enroll(con, 1, "bulgarian-peak-8w", start_day=D, today=D)       # после завершения можно записаться снова


# ------------------------------------------------------------------ тренд «максимум дня»

def test_day_max_trend():
    con = _con()
    eid = _enrolled(con)
    assert P.day_max_trend(con, 1, "squat_snatch")["trend"] == "none"
    vals = [(1, 1, 70), (1, 3, 72.5), (2, 1, 75), (2, 3, 80)]     # сессии с рывком в сед
    for wk, idx, kg in vals:
        sid = _session(con, eid, wk, idx)
        v = P.plan_session(con, 1, sid, D)
        sn = next(ex for b in v["blocks"] for ex in b["exercises"] if ex["lift"] == "squat_snatch")
        P.log_set(con, 1, sid, sn["sets"][0]["id"], done_kg=kg, reps=1, ok=True)
    t = P.day_max_trend(con, 1, "squat_snatch")
    assert [p["kg"] for p in t["points"]] == [70, 72.5, 75, 80] and t["trend"] == "up" and t["delta_kg"] == 10
    assert t["best"] == 80
    assert len(P.day_max_trend(con, 1, "squat_snatch", window=2)["points"]) == 2
    assert P.day_max_trend(con, 2, "squat_snatch")["points"] == []


def test_finish_uses_workouts_save_result(monkeypatch):
    """finish_session не дублирует запись тренировки: делегирует tj.services.workouts.save_result."""
    from tj.services import workouts
    calls = []
    real = workouts.save_result

    def spy(con, uid, aid, payload, **kw):
        calls.append((aid, payload))
        return real(con, uid, aid, payload, **kw)

    monkeypatch.setattr(workouts, "save_result", spy)
    con = _con()
    eid = _enrolled(con)
    sid = _session(con, eid, 1, 1)
    _log_all(con, sid)
    P.finish_session(con, 1, sid, today=D)
    assert len(calls) == 1 and calls[0][1]["sport"] == "weightlifting" and calls[0][1]["form_result"]
    from tj.services.errors import BadRequest
    with pytest.raises(BadRequest):
        P.finish_session(con, 1, _session(con, eid, 1, 2), activity_id="not-a-uuid", today=D)
