from __future__ import annotations
import asyncio
import tjbot.vision as vision
from tjbot import db as botdb
from tjbot.handlers import record_workout as rw


def _db_path(tmp_path) -> str:
    p = tmp_path / "t.db"
    con = botdb.connect(str(p))
    try:
        botdb.init_schema(con)
        con.commit()
    finally:
        con.close()
    return str(p)


class _FakeCQMsg:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


class _FakeCallback:
    def __init__(self, data):
        self.data = data
        self.message = _FakeCQMsg()
        self.from_user = type("U", (), {"id": 1})()
        self.edited = []

    async def answer(self):
        pass

    async def edit_message_text(self, text, **kw):
        self.edited.append(text)


class _FakeUpd:
    def __init__(self, data):
        self.callback_query = _FakeCallback(data)


class _Ctx:
    def __init__(self, user_data=None, db_path=":memory:"):
        self.user_data = user_data or {"board_text": "WOD"}
        self.bot_data = {"db_path": db_path}


def test_board_confirm_ok_goes_to_result(tmp_path):
    u = _FakeUpd("bconf:ok")
    c = _Ctx({"board_text": "не распознаваемый как программа текст"},
             db_path=_db_path(tmp_path))
    assert asyncio.run(rw.board_confirm(u, c)) == rw.RESULT


def test_board_confirm_ok_shows_template(tmp_path):
    from tj import i18n
    board = ("2 ТА.\n- Е2МОМх5х5х80%\nприседание со штангой на спине\n")
    u = _FakeUpd("bconf:ok")
    c = _Ctx({"board_text": board}, db_path=_db_path(tmp_path))
    assert asyncio.run(rw.board_confirm(u, c)) == rw.RESULT
    replies = u.callback_query.message.replies
    assert any(i18n.t("record.fill_results_template", "ru").split("\n\n")[0] in r for r in replies)
    assert c.user_data.get("result_blocks")


def test_board_confirm_edit_reopens_board(tmp_path):
    u = _FakeUpd("bconf:edit")
    c = _Ctx({"board_text": "WOD текст доски"}, db_path=_db_path(tmp_path))
    assert asyncio.run(rw.board_confirm(u, c)) == rw.BOARD
    assert c.user_data.get("board_editing") is True                 # правка помечена
    assert any("WOD текст доски" in r for r in u.callback_query.message.replies)


def test_parse_lift_lines():
    out = rw._parse_lift_lines("становая 130x1\nприсед 150 3\nчушь\nжим 0x1")
    assert {"movement": "становая", "weight_kg": 130.0, "reps": 1} in out
    assert {"movement": "присед", "weight_kg": 150.0, "reps": 3} in out
    movements = [o["movement"] for o in out]
    assert "чушь" not in movements          # нет числа -> пропуск
    assert "жим" not in movements           # parse_lift отвергает 0x1
    assert len(out) == 2


def test_handler_builds_and_states():
    h = rw.handler()
    assert h is not None
    states = {rw.DATE, rw.DATE_INPUT, rw.SPORT, rw.UNIVERSE_ASK, rw.BOARD,
              rw.BOARD_CONFIRM, rw.RESULT, rw.MAX_CONFIRM, rw.MAX_EDIT, rw.BODYWEIGHT}
    assert len(states) == 10         # все 10 состояний различны


def test_handler_entry_is_add_workout():
    from tjbot.handlers import menu
    h = rw.handler()
    ep = h.entry_points[0]
    assert set(ep.filters.strings) == menu.btn_variants("btn.add_workout")
    assert rw.UNIVERSE_ASK not in h.states          # шага Universe в мастере нет


def test_pick_sport_crossfit_goes_to_board(tmp_path):
    u = _FakeUpd("s:crossfit")
    c = _Ctx({"date": __import__("datetime").date(2026, 7, 1)},
             db_path=_db_path(tmp_path))
    assert asyncio.run(rw.pick_sport(u, c)) == rw.BOARD
    from tj import i18n
    replies = u.callback_query.message.replies
    assert any(i18n.t("record.ask_board", "ru").lower()[:10] in r.lower() for r in replies)
    assert not any("Universe" in r for r in replies)


def test_deterministic_template_no_llm():
    from tj.analysis.wod_program import parse_program, render_template
    board = ("2 ТА.\n- Е2МОМх5х5х80%\nприседание со штангой на спине\n"
             "4 AMRAP 3 мин х 5 / 1 мин отдых\n- 16 рывков\n- 8 подтягивания\n")
    blocks = parse_program(board)
    tmpl = render_template(blocks)
    assert "раунд 1 (вес×повторы): ___" in tmpl
    assert "AMRAP (5×3мин):" in tmpl
    assert tmpl.count("круги, амрап") == 5
