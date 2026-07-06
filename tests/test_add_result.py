from __future__ import annotations

def test_template_from_program_text():
    from tjbot.handlers.add_result import template_from_program
    prog = ("2 ТА.\n- Е2МОМх5х5х80%\nприседание со штангой на спине\n"
            "4 AMRAP 3 мин х 5 / 1 мин отдых\n- 16 рывков\n- 8 подтягивания\n")
    tmpl, blocks = template_from_program(prog)
    assert "раунд 1 (вес×повторы): ___" in tmpl
    assert "AMRAP (5×3мин):" in tmpl
    assert any(b["format"] == "amrap_interval" for b in blocks)

def test_template_from_empty():
    from tjbot.handlers.add_result import template_from_program
    tmpl, blocks = template_from_program("")
    assert tmpl is None and blocks == []


def _db_path(tmp_path):
    from tjbot import db as botdb
    p = tmp_path / "t.db"
    con = botdb.connect(str(p))
    try:
        botdb.init_schema(con)
        con.commit()
    finally:
        con.close()
    return str(p)


class _Msg:
    def __init__(self, text=""):
        self.text = text


class _Upd:
    def __init__(self):
        self.effective_user = type("U", (), {"id": 1})()
        self.message = _Msg()


class _Ctx:
    def __init__(self, db_path):
        self.user_data = {}
        self.bot_data = {"db_path": db_path, "tz": "UTC"}


def test_save_filled_result_inserts_activity(tmp_path):
    import asyncio
    from datetime import date
    from tjbot import db as botdb
    from tjbot.handlers.add_result import template_from_program
    from tjbot.handlers.record_workout import save_filled_result
    board = "4 AMRAP 3 мин х 5 / 1 мин отдых\n- 16 рывков\n- 8 подтягивания\n"
    _, blocks = template_from_program(board)
    dbp = _db_path(tmp_path)
    upd, ctx = _Upd(), _Ctx(dbp)
    day = date(2026, 7, 1)
    results, metcon_lines, act_id = asyncio.run(
        save_filled_result(upd, ctx, day, board, "gym", "RPE 7", blocks))
    assert act_id == "manual-1-2026-07-01-crossfit"
    con = botdb.connect(dbp)
    try:
        act = botdb.get_activity(con, act_id, tg_id=1)
    finally:
        con.close()
    assert act is not None
    assert act.get("board_source") == "gym"
