from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from svc_common import BOARD, fill_by, make_con
from tj.analysis.workouts import recent_workouts
from tj.models import Activity, Sport
from tj.services import board as board_svc
from tj.services import workouts as W
from tj.services.errors import BadRequest, Forbidden, Invalid, NotFound
from tjbot import db as botdb

UID = 101
DAY = "2026-09-01"


def _uid() -> str:
    return str(uuid.uuid4())


def _board(con):
    return board_svc.build(con, UID, BOARD, verify=False, use_llm=False)


def _payload(con, **over):
    b = _board(con)
    form = b["form"]
    p = {"day": DAY, "sport": "crossfit",
         "board": {"text": BOARD, "source": "own", "blocks": b["blocks"]},
         "form_result": fill_by(form, {
             "раунд 1": "100x5", "раунд 2": "105x5", "раунд 3": "110x3",
             "время": "8:36", "круги, амрап 1": "5+3", "круги, амрап 2": 4})}
    p.update(over)
    return p


def _acts(con, uid=UID):
    return con.execute("SELECT * FROM activities WHERE tg_id=?", (uid,)).fetchall()


# --- сохранение из формы -----------------------------------------------------------------

def test_save_result_from_form(tmp_path):
    con = make_con(tmp_path)
    aid = _uid()
    r = W.save_result(con, UID, aid, _payload(con, rpe=8, scaling="rx", bodyweight=79.5))
    assert r["created"] and r["activity_id"] == aid and r["rpe"] == 8 and r["scaling"] == "rx"
    row = _acts(con)[0]
    assert row["source"] == "manual" and row["activity_id"] == aid and row["day"] == DAY
    assert row["perf_rpe"] == 8 and row["perf_scaling"] == "rx"
    extra = json.loads(row["extra"])
    assert extra["board_source"] == "own" and extra["board_text"].startswith("Актив")
    assert extra["metcon"]["times_sec"] == [516]
    assert extra["metcon"]["amrap"]["total_rounds"] == 9
    assert extra["result_blocks"] and extra["form_result"]
    assert "start_ts" not in extra                   # время не называли — не выдумываем
    assert any("8:36" in ln for ln in r["metcon_lines"])
    # макс по приседу ушёл в уровни (лучший подход 110x3), вес тела записан
    sq = [c for c in r["credited"] if c["discipline"] == "back_squat"]
    assert sq and sq[0]["weight"] == 110 and sq[0]["reps"] == 3
    assert con.execute("SELECT weight_kg FROM daily WHERE tg_id=? AND day=?",
                       (UID, DAY)).fetchone()[0] == 79.5
    assert botdb.best_results(con, UID)["back_squat"]["value"] == 110


def test_put_is_idempotent(tmp_path):
    con = make_con(tmp_path)
    aid = _uid()
    p = _payload(con)
    r1 = W.save_result(con, UID, aid, p)
    r2 = W.save_result(con, UID, aid, p)
    assert r1["created"] and not r2["created"]
    assert len(_acts(con)) == 1
    n = con.execute("SELECT COUNT(*) FROM discipline_results WHERE tg_id=? AND activity_id=?",
                    (UID, aid)).fetchone()[0]
    assert n == len(r1["credited"]) == len(r2["credited"])
    # изменённый результат заменяет строку и максы, а не плодит
    p2 = _payload(con)
    p2["form_result"] = fill_by(_board(con)["form"], {"раунд 1": "120x1"})
    W.save_result(con, UID, aid, p2)
    assert len(_acts(con)) == 1
    vals = [r["value"] for r in con.execute(
        "SELECT value FROM discipline_results WHERE tg_id=? AND activity_id=? AND discipline='back_squat'",
        (UID, aid))]
    assert vals == [120]
    assert json.loads(_acts(con)[0]["extra"])["created_at"]


def test_several_workouts_per_day_including_two_weightlifting(tmp_path):
    con = make_con(tmp_path)
    ids = {k: _uid() for k in ("ta1", "ta2", "cf", "run")}
    W.save_result(con, UID, ids["ta1"], {"day": DAY, "sport": "weightlifting", "start_time": "09:00",
                                         "board": {"text": "Рывок 5x2", "source": "own"}})
    W.save_result(con, UID, ids["ta2"], {"day": DAY, "sport": "weightlifting", "start_time": "18:00",
                                         "board": {"text": "Толчок 5x2", "source": "own"}})
    W.save_result(con, UID, ids["cf"], _payload(con))
    W.save_result(con, UID, ids["run"], {"day": DAY, "sport": "run", "duration_min": 40,
                                         "distance_km": 8, "rpe": 6})
    rows = _acts(con)
    assert len(rows) == 4 and {r["activity_id"] for r in rows} == set(ids.values())
    assert sorted(r["sport"] for r in rows) == ["crossfit", "run", "weightlifting", "weightlifting"]
    run = W.get(con, UID, ids["run"])
    assert run["distance_km"] == 8 and run["rpe"] == 6 and run["duration_min"] == 40
    assert [w["id"] for w in W.recent(con, UID)][0] == ids["run"]   # последняя записанная сверху
    assert W.get(con, UID, ids["ta2"])["start_time"] == "18:00"


def test_legacy_id_still_editable_but_only_own(tmp_path):
    con = make_con(tmp_path)
    legacy = f"manual-{UID}-{DAY}-crossfit"
    from tj.models import StrengthWodDetails
    a = Activity(source="manual", sport=Sport.CROSSFIT,
                 start=datetime(2026, 9, 1, 12, tzinfo=timezone.utc), activity_id=legacy)
    a.strength = StrengthWodDetails()
    a.extra = {"board_text": "WOD", "board_source": "own"}
    botdb.insert_activity(con, a, UID)
    assert W.update(con, UID, legacy, {"rpe": 7})["workout"]["rpe"] == 7
    assert W.normalize_activity_id(UID, legacy) == legacy
    with pytest.raises(BadRequest):
        W.normalize_activity_id(UID + 1, legacy)          # чужой старый id не принимаем
    with pytest.raises(BadRequest):
        W.normalize_activity_id(UID, "not-a-uuid")


# --- валидация ---------------------------------------------------------------------------

def test_validation_errors(tmp_path):
    con = make_con(tmp_path)
    good = _payload(con)
    with pytest.raises(BadRequest):
        W.save_result(con, UID, "abc", good)
    with pytest.raises(Invalid):
        W.save_result(con, UID, _uid(), {**good, "sport": "curling"})
    with pytest.raises(Invalid):
        W.save_result(con, UID, _uid(), {**good, "day": "01.09.2026"})
    with pytest.raises(Invalid):
        W.save_result(con, UID, _uid(), {**good, "rpe": 11})
    with pytest.raises(Invalid):
        W.save_result(con, UID, _uid(), {**good, "start_time": "25:00"})
    with pytest.raises(Invalid):
        W.save_result(con, UID, _uid(), {**good, "bodyweight": 5})
    with pytest.raises(Invalid) as e:
        W.save_result(con, UID, _uid(), {**good, "form_result": {"9.9": "1"}})
    assert e.value.code == "unknown_field"
    with pytest.raises(Invalid):
        W.save_result(con, UID, _uid(), {**good, "form_result": fill_by(_board(con)["form"],
                                                                        {"время": "8-36"})})
    assert _acts(con) == []                           # ничего не записано при ошибке


def test_cannot_overwrite_watch_activity(tmp_path):
    con = make_con(tmp_path)
    g = Activity(source="garmin", sport=Sport.RUN, activity_id=str(uuid.uuid4()),
                 start=datetime(2026, 9, 1, 7, tzinfo=timezone.utc), duration_min=30)
    botdb.insert_activity(con, g, UID)
    with pytest.raises(Forbidden):
        W.save_result(con, UID, g.activity_id, {"day": DAY, "sport": "run"})
    with pytest.raises(Forbidden):
        W.delete(con, UID, g.activity_id)
    with pytest.raises(Forbidden):
        W.update(con, UID, g.activity_id, {"rpe": 5})


# --- слияние с часами по времени ---------------------------------------------------------

def _garmin(con, hh, mm, dur=60, sport=Sport.CROSSFIT, hr=140):
    a = Activity(source="garmin", sport=sport, activity_id=f"g-{hh}{mm}", avg_hr=hr, duration_min=dur,
                 start=datetime(2026, 9, 1, hh, mm, tzinfo=timezone.utc))
    botdb.insert_activity(con, a, UID)


def _report(tmp_path, con):
    con.commit()
    return [r for r in recent_workouts(str(tmp_path / "t.db"), "sqlite", 50, tg_id=UID)
            if r["day"] == DAY]


def test_merge_with_watch_by_time_overlap(tmp_path):
    con = make_con(tmp_path)
    _garmin(con, 9, 0, hr=131)
    _garmin(con, 18, 30, hr=152)
    # вечерняя запись пришла в БД РАНЬШЕ утренней — порядок не должен влиять
    W.save_result(con, UID, _uid(), {"day": DAY, "sport": "weightlifting", "start_time": "18:35",
                                     "duration_min": 55, "board": {"text": "Толчок 5x2", "source": "own"}})
    W.save_result(con, UID, _uid(), {"day": DAY, "sport": "crossfit", "start_time": "09:05",
                                     "duration_min": 50, "board": {"text": "WOD Fran", "source": "own"}})
    rows = _report(tmp_path, con)
    assert len(rows) == 2                              # две сессии, не четыре
    by_sport = {r["sport"]: r for r in rows}
    assert by_sport["weightlifting"]["avg_hr"] == 152  # вечерняя ТА <-> вечерние часы
    assert by_sport["crossfit"]["avg_hr"] == 131       # утренний кроссфит <-> утренние часы


def test_no_merge_when_times_do_not_overlap(tmp_path):
    con = make_con(tmp_path)
    _garmin(con, 9, 0, hr=131)
    W.save_result(con, UID, _uid(), {"day": DAY, "sport": "crossfit", "start_time": "20:00",
                                     "duration_min": 40, "board": {"text": "WOD", "source": "own"}})
    rows = _report(tmp_path, con)
    assert len(rows) == 2                              # разные сессии одного дня


def test_two_ta_sessions_each_take_their_own_watch_row(tmp_path):
    con = make_con(tmp_path)
    _garmin(con, 8, 0, hr=120)
    _garmin(con, 19, 0, hr=160)
    for hh in ("08:10", "19:05"):
        W.save_result(con, UID, _uid(), {"day": DAY, "sport": "weightlifting", "start_time": hh,
                                         "duration_min": 60, "board": {"text": "ТА", "source": "own"}})
    rows = _report(tmp_path, con)
    assert sorted(r["avg_hr"] for r in rows) == [120, 160] and len(rows) == 2


def test_manual_without_time_merges_by_day_like_before(tmp_path):
    con = make_con(tmp_path)
    _garmin(con, 9, 0, hr=131)
    W.save_result(con, UID, _uid(), {"day": DAY, "sport": "crossfit",
                                     "board": {"text": "WOD", "source": "own"}})
    rows = _report(tmp_path, con)
    assert len(rows) == 1 and rows[0]["avg_hr"] == 131


def test_run_never_merges_with_crossfit_family(tmp_path):
    con = make_con(tmp_path)
    _garmin(con, 9, 0, sport=Sport.RUN, hr=150)
    W.save_result(con, UID, _uid(), {"day": DAY, "sport": "crossfit", "start_time": "09:00",
                                     "board": {"text": "WOD", "source": "own"}})
    assert len(_report(tmp_path, con)) == 2


# --- неоднозначные лифты -------------------------------------------------------------------

def _snatch_blocks():
    return [{"header": "ТА", "format": "strength", "rounds": 2, "reps": 2, "has_cap": False,
             "movements": [{"name": "рывок", "canon": "snatch", "weighted": True}],
             "benchmark": None}]


def test_ambiguous_lift_question_and_resolution(tmp_path):
    con = make_con(tmp_path)
    aid = _uid()
    blocks = _snatch_blocks()
    form = board_svc.result_form(blocks)
    payload = {"day": DAY, "sport": "weightlifting",
               "board": {"text": "Рывок 2x2", "source": "own", "blocks": blocks},
               "form_result": fill_by(form, {"раунд 1": "70x2", "раунд 2": "80x2"})}
    r = W.save_result(con, UID, aid, payload)
    assert r["credited"] == []
    assert len(r["ambiguous"]) == 1
    q = r["ambiguous"][0]
    assert q["family"] == "snatch" and q["weight"] == 80 and q["reps"] == 2
    assert [v["id"] for v in q["variants"]] == ["squat_snatch", "power_snatch"]
    assert all(v["label"] for v in q["variants"])
    with pytest.raises(Invalid):
        W.resolve_lift(con, UID, aid, q["movement"], "back_squat", 80, 2)
    with pytest.raises(NotFound):
        W.resolve_lift(con, UID + 1, aid, q["movement"], "power_snatch", 80, 2)
    res = W.resolve_lift(con, UID, aid, q["movement"], "power_snatch", 80, 2)
    assert res["discipline"] == "power_snatch" and res["est_1rm"] == round(80 * (1 + 2 / 30), 1)
    W.resolve_lift(con, UID, aid, q["movement"], "power_snatch", 80, 2)      # повтор без дублей
    assert con.execute("SELECT COUNT(*) FROM discipline_results WHERE tg_id=? AND discipline='power_snatch'",
                       (UID,)).fetchone()[0] == 1
    # повторный PUT не переспрашивает и не теряет выбранный вариант
    r2 = W.save_result(con, UID, aid, payload)
    assert r2["ambiguous"] == [] and [c["discipline"] for c in r2["credited"]] == ["power_snatch"]
    assert con.execute("SELECT COUNT(*) FROM discipline_results WHERE tg_id=? AND discipline='power_snatch'",
                       (UID,)).fetchone()[0] == 1


# --- права на правку доски ------------------------------------------------------------------

GYM_BOARD = "3 WOD\n3 сета:\n- 20 прыжки через бокс\n- 15 фронтальный присед с гантелью"


def _gym_program(con, day=DAY):
    botdb.add_program(con, day, "Universe", GYM_BOARD, confirmed=1)


def test_gym_board_cannot_be_edited(tmp_path):
    con = make_con(tmp_path)
    _gym_program(con)
    aid = _uid()
    # клиент присылает чужой текст — сервер берёт программу зала
    r = W.save_result(con, UID, aid, {"day": DAY, "sport": "crossfit",
                                      "board": {"text": "подделка", "source": "gym"},
                                      "form_result": "время 5:00"})
    assert r["board_source"] == "gym"
    w = W.get(con, UID, aid)
    assert w["board_text"] == GYM_BOARD and w["board_editable"] is False
    with pytest.raises(Forbidden):
        W.update(con, UID, aid, {"board": {"text": "моя доска"}})
    with pytest.raises(Forbidden):                     # и через PUT зальную доску в свою не превратить
        W.save_result(con, UID, aid, {"day": DAY, "sport": "crossfit",
                                      "board": {"text": "моя доска", "source": "own"}})
    assert W.update(con, UID, aid, {"rpe": 9})["workout"]["rpe"] == 9   # результаты править можно
    assert W.get(con, UID, aid)["board_text"] == GYM_BOARD


def test_gym_program_of_another_gym_saved_when_chosen_at_record_time(tmp_path, monkeypatch):
    """Админ/тренер/атлет с несколькими залами записывает тренировку по программе НЕ профильного зала:
    клиент передаёт board.gym, иначе сервер искал бы программу только в зале из профиля."""
    from tjbot import access
    con = make_con(tmp_path)
    botdb.add_gym(con, "INVICTUS GO OXY")
    botdb.add_program(con, DAY, "INVICTUS GO OXY", GYM_BOARD, confirmed=1)
    monkeypatch.setattr(access, "is_admin", lambda uid: True)
    with pytest.raises(Invalid):                         # без зала ищется только Universe -> нет программы
        W.save_result(con, UID, _uid(), {"day": DAY, "sport": "crossfit", "board": {"source": "gym"}})
    aid = _uid()
    r = W.save_result(con, UID, aid, {"day": DAY, "sport": "crossfit",
                                      "board": {"source": "gym", "gym": "INVICTUS GO OXY"},
                                      "form_result": "время 5:00"})
    assert r["board_source"] == "gym" and W.get(con, UID, aid)["board_text"] == GYM_BOARD


def test_gym_source_requires_program(tmp_path):
    con = make_con(tmp_path)
    with pytest.raises(Invalid) as e:
        W.save_result(con, UID, _uid(), {"day": DAY, "sport": "crossfit",
                                         "board": {"source": "gym"}})
    assert e.value.code == "no_gym_program"


def test_own_board_editable_and_recomputes(tmp_path):
    con = make_con(tmp_path)
    aid = _uid()
    W.save_result(con, UID, aid, _payload(con))
    w = W.get(con, UID, aid)
    assert w["board_editable"] and w["form"] and w["form_values"]
    new = "WOD\n- 10 бёрпи\n- 15 приседаний"
    out = W.update(con, UID, aid, {"board": {"text": new}})
    assert out["workout"]["board_text"] == new
    assert out["workout"]["blocks"] != w["blocks"]


def test_update_score_scaling_rpe_weight_maxes(tmp_path):
    con = make_con(tmp_path)
    aid = _uid()
    W.save_result(con, UID, aid, _payload(con))
    form = board_svc.result_form(W.get(con, UID, aid)["blocks"])
    out = W.update(con, UID, aid, {
        "form_result": fill_by(form, {"раунд 1": "130x2", "время": "7:59"}),
        "scaling": "scaled", "rpe": 9, "bodyweight": 80.0})
    w = out["workout"]
    assert w["score"] == "7:59" and w["scaling"] == "scaled" and w["rpe"] == 9 and w["bodyweight"] == 80.0
    assert any(c["discipline"] == "back_squat" and c["weight"] == 130 for c in out["credited"])
    with pytest.raises(Invalid):
        W.update(con, UID, aid, {"rpe": 0})
    with pytest.raises(Invalid):
        W.update(con, UID, aid, {})
    r = W.confirm_maxes(con, UID, aid, [{"movement": "становая тяга", "weight_kg": 150, "reps": 3}])
    assert [c["discipline"] for c in r["credited"]] == ["deadlift"]
    r = W.confirm_maxes(con, UID, aid, text="Рывок 60x2")
    assert r["ambiguous"][0]["family"] == "snatch"
    with pytest.raises(NotFound):
        W.update(con, UID + 1, aid, {"rpe": 3})


# --- свободный текст (без блоков) ----------------------------------------------------------

def test_free_text_result_proposes_maxes_without_recording(tmp_path, monkeypatch):
    from tjbot import vision
    monkeypatch.setattr(vision, "has_vision", lambda: False)
    con = make_con(tmp_path)
    aid = _uid()
    r = W.save_result(con, UID, aid, {"day": DAY, "sport": "weightlifting",
                                      "form_result": "Присед 100x3\nrpe 8 scaled"})
    assert r["rpe"] == 8 and r["scaling"] == "scaled"
    assert r["credited"] == [] and r["proposed_maxes"]["maxes"] == [
        {"movement": "Присед", "weight_kg": 100.0, "reps": 3}]
    assert con.execute("SELECT COUNT(*) FROM discipline_results WHERE tg_id=?", (UID,)).fetchone()[0] == 0
    c = W.confirm_maxes(con, UID, aid, r["proposed_maxes"]["maxes"])
    assert [x["discipline"] for x in c["credited"]] == ["back_squat"]
    assert botdb.best_results(con, UID)["back_squat"]["value"] == 100


def test_free_text_uses_llm_lifts_with_quota(tmp_path, monkeypatch):
    from tjbot import access, vision
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    calls = []
    monkeypatch.setattr(vision, "parse_lifts", lambda t, use_llm=True: calls.append(t) or
                        [{"movement": "становая тяга", "weight_kg": 140, "reps": 1}])
    con = make_con(tmp_path)
    r = W.save_result(con, UID, _uid(), {"day": DAY, "sport": "weightlifting", "form_result": "тяга 140"})
    assert calls and r["proposed_maxes"]["credited"][0]["discipline"] == "deadlift"
    for _ in range(access.LLM_DAILY_LIMIT):            # выбираем квоту до конца
        access.llm_quota_consume(UID, con)
    r = W.save_result(con, UID, _uid(), {"day": DAY, "sport": "weightlifting",
                                         "form_result": "Становая тяга 140"})
    assert r["lifts_skipped_quota"] is True and len(calls) == 1     # ИИ не дёргали
    assert r["proposed_maxes"]["maxes"][0]["weight_kg"] == 140       # но построчный разбор работает


# --- удаление / восстановление -----------------------------------------------------------------

def test_soft_delete_and_restore(tmp_path):
    con = make_con(tmp_path)
    aid = _uid()
    W.save_result(con, UID, aid, _payload(con, bodyweight=80))
    assert botdb.best_results(con, UID)
    d = W.delete(con, UID, aid)
    assert d["deleted_at"].endswith("Z")
    assert _acts(con) == [] and botdb.best_results(con, UID) == {}     # ПМ из неё ушёл вместе с ней
    assert W.trash(con, UID)[0]["id"] == aid
    with pytest.raises(NotFound):
        W.get(con, UID, aid)
    with pytest.raises(NotFound):
        W.delete(con, UID, aid)
    with pytest.raises(NotFound):
        W.restore(con, UID + 1, aid)
    w = W.restore(con, UID, aid)
    assert w["id"] == aid and w["board_text"] and botdb.best_results(con, UID)["back_squat"]["value"] == 110
    assert W.trash(con, UID) == []
    with pytest.raises(NotFound):
        W.restore(con, UID, aid)                       # из корзины уже вынута
    # если под тем же id успели записать новое — восстановление не затирает живую запись
    W.delete(con, UID, aid)
    W.save_result(con, UID, aid, {"day": DAY, "sport": "run"})
    with pytest.raises(BadRequest):
        W.restore(con, UID, aid)


def test_other_user_cannot_touch_workout(tmp_path):
    con = make_con(tmp_path)
    aid = _uid()
    W.save_result(con, UID, aid, _payload(con))
    for fn in (lambda: W.get(con, UID + 1, aid), lambda: W.delete(con, UID + 1, aid),
               lambda: W.update(con, UID + 1, aid, {"rpe": 1})):
        with pytest.raises(NotFound):
            fn()
    # тот же UUID у другого пользователя — независимая запись, чужую не затирает
    W.save_result(con, UID + 1, aid, {"day": DAY, "sport": "run"})
    assert W.get(con, UID, aid)["sport"] == "crossfit"


# --- вес тела и самочувствие -----------------------------------------------------------------

def test_bodyweight_and_feel(tmp_path):
    con = make_con(tmp_path)
    assert W.set_bodyweight(con, UID, "79,5".replace(",", "."), today=date(2026, 9, 1)) == {
        "day": "2026-09-01", "kg": 79.5}
    assert W.set_bodyweight(con, UID, 80, "2026-08-30", today=date(2026, 9, 1))["day"] == "2026-08-30"
    for bad in (0, 19, 900, "abc", None):
        with pytest.raises(Invalid):
            W.set_bodyweight(con, UID, bad, today=date(2026, 9, 1))
    with pytest.raises(Invalid):
        W.set_bodyweight(con, UID, 80, "2026-09-10", today=date(2026, 9, 1))
    assert W.set_feel(con, UID, 7, today=date(2026, 9, 1)) == {"day": "2026-09-01", "score": 7}
    daily = con.execute("SELECT extra FROM daily WHERE tg_id=? AND day='2026-09-01'", (UID,)).fetchone()
    assert json.loads(daily["extra"])["self_feel"] == 7
    for bad in (0, 11, "x", 5.5, True):
        with pytest.raises(Invalid):
            W.set_feel(con, UID, bad, today=date(2026, 9, 1))


def test_feel_day_follows_user_timezone_not_server(tmp_path):
    con = make_con(tmp_path)
    east = W.set_feel(con, UID, 5, tz="Pacific/Kiritimati")["day"]     # UTC+14
    west = W.set_feel(con, UID, 5, tz="Pacific/Pago_Pago")["day"]      # UTC-11
    assert east == datetime.now(ZoneInfo("Pacific/Kiritimati")).date().isoformat()
    assert west == datetime.now(ZoneInfo("Pacific/Pago_Pago")).date().isoformat()
    assert east != west                                                # разные календарные дни
