"""Типы тренировок с доской: кроссфит, ТА, Hyrox — один флоу, разные ярлыки."""
from __future__ import annotations

import asyncio
from datetime import date
from zoneinfo import ZoneInfo

from tj import i18n
from tj.analysis.workouts import _merged_rows
from tj.models import BOARD_SPORTS, Sport
from tjbot import db as botdb
from tjbot.handlers import record_workout as rw

from test_record_workout import _Ctx, _FakeUpd, _db_path
from test_workouts_merge import _act


def test_new_sports_in_enum_and_family():
    assert Sport.WEIGHTLIFTING.value == "weightlifting"
    assert Sport.HYROX.value == "hyrox"
    assert BOARD_SPORTS == {Sport.CROSSFIT, Sport.WEIGHTLIFTING, Sport.HYROX}
    assert Sport.RUN not in BOARD_SPORTS


def test_sport_buttons_cover_all_types(tmp_path):
    msgs = []

    class _Msg:
        async def reply_text(self, text, **kw):
            msgs.append(kw.get("reply_markup"))

    state = asyncio.run(rw._ask_sport(_Msg(), _Ctx(db_path=_db_path(tmp_path)), "ru"))
    assert state == rw.SPORT
    data = [b.callback_data for row in msgs[0].inline_keyboard for b in row]
    assert data == ["s:crossfit", "s:weightlifting", "s:hyrox", "s:run", "s:bike"]
    assert set(data) == {f"s:{k}" for k in rw._SPORTS}


def test_button_labels_localized():
    for key in ("record.btn_weightlifting", "record.btn_hyrox"):
        assert i18n.t(key, "ru") and i18n.t(key, "en")
    assert i18n.t("record.btn_weightlifting", "ru") == "ТА"


def test_pick_weightlifting_goes_to_board(tmp_path):
    u = _FakeUpd("s:weightlifting")
    c = _Ctx({"date": date(2026, 9, 13)}, db_path=_db_path(tmp_path))
    assert asyncio.run(rw.pick_sport(u, c)) == rw.BOARD
    assert c.user_data["sport"] == Sport.WEIGHTLIFTING
    assert any(i18n.t("record.ask_board", "ru")[:10] in r
               for r in u.callback_query.message.replies)


def test_pick_hyrox_goes_to_board(tmp_path):
    u = _FakeUpd("s:hyrox")
    c = _Ctx({"date": date(2026, 9, 13)}, db_path=_db_path(tmp_path))
    assert asyncio.run(rw.pick_sport(u, c)) == rw.BOARD
    assert c.user_data["sport"] == Sport.HYROX


def test_pick_run_still_asks_result(tmp_path):
    u = _FakeUpd("s:run")
    c = _Ctx({"date": date(2026, 9, 13)}, db_path=_db_path(tmp_path))
    assert asyncio.run(rw.pick_sport(u, c)) == rw.RESULT


def test_weightlifting_activity_keeps_board_and_id():
    ud = {"date": date(2026, 9, 13), "sport": Sport.WEIGHTLIFTING,
          "board_text": "Рывок в сед", "result": "55 кг, RPE 7"}
    act = rw._build_activity(ud, ZoneInfo("Europe/Moscow"), 42)
    assert act.sport == Sport.WEIGHTLIFTING
    assert act.activity_id == "manual-42-2026-09-13-weightlifting"
    assert act.strength.prescription.raw_text == "Рывок в сед"
    assert act.strength.performed.rpe == 7
    assert act.extra["board_text"] == "Рывок в сед"


def test_board_activity_defaults_to_crossfit():
    act = rw._board_activity(date(2026, 9, 13), "Fran", "gym", "7:20",
                             ZoneInfo("Europe/Moscow"), 42)
    assert act.sport == Sport.CROSSFIT
    act_ta = rw._board_activity(date(2026, 9, 13), "ТА", "own", "100",
                                ZoneInfo("Europe/Moscow"), 42,
                                sport=Sport.WEIGHTLIFTING)
    assert act_ta.activity_id.endswith("-weightlifting")


def test_manual_weightlifting_merges_with_garmin_biometrics():
    """Часы пишут ТА как strength_training -> crossfit. Ручная ТА-запись должна
    забрать их пульс и калории, а не превратиться во вторую тренировку дня."""
    acts = [
        _act("2026-09-13", "crossfit", dur=40, ahr=132, cal=438, source="garmin"),
        _act("2026-09-13", "weightlifting", score="55 кг", source="manual"),
    ]
    rows = _merged_rows(acts)
    assert len(rows) == 1
    assert rows[0]["sport"] == "weightlifting"      # тип знает атлет, не часы
    assert rows[0]["avg_hr"] == 132
    assert rows[0]["calories"] == 438
    assert rows[0]["score"] == "55 кг"


def test_hyrox_merges_with_garmin_and_keeps_label():
    acts = [
        _act("2026-09-14", "hyrox", score="1:12:30", source="manual"),
        _act("2026-09-14", "crossfit", dur=72, ahr=155, source="garmin"),
    ]
    rows = _merged_rows(acts)
    assert len(rows) == 1
    assert rows[0]["sport"] == "hyrox"
    assert rows[0]["duration_min"] == 72


def test_board_family_does_not_swallow_cardio():
    acts = [
        _act("2026-09-14", "weightlifting", score="100", source="manual"),
        _act("2026-09-14", "run", dur=30, ahr=140, source="garmin"),
    ]
    assert len(_merged_rows(acts)) == 2


def test_two_manual_board_sports_stay_separate():
    acts = [
        _act("2026-09-14", "weightlifting", score="100", source="manual"),
        _act("2026-09-14", "crossfit", wod_name="Fran", source="manual"),
    ]
    rows = _merged_rows(acts)
    assert len(rows) == 2
    assert {r["sport"] for r in rows} == {"weightlifting", "crossfit"}


def test_review_skips_empty_weightlifting_day(tmp_path, monkeypatch):
    from tjbot import claude_review
    monkeypatch.setattr(claude_review, "workout_report",
                        lambda *a, **kw: {"sessions": [], "trimp": 0})
    monkeypatch.setattr(claude_review.llm_coach, "workout_payload", lambda rep: {})
    con = botdb.connect(_db_path(tmp_path))
    try:
        out = claude_review.review_day(con, 1, "2026-09-13", sport="weightlifting",
                                       db_path=":memory:")
    finally:
        con.close()
    assert "без доски" in out["skip"]
