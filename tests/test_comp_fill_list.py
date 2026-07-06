from __future__ import annotations

import sqlite3


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    from tjbot import db as botdb
    botdb.init_schema(con)
    return con


def _make_event(botdb, con, *, name, tg_id, city="A", date="2026-04-12",
                div="PRO", field_size=22, join=True):
    eid = botdb.create_event(con, name=name, city=city, date_start=date,
                             date_end=date, sport="crossfit", fmt="", created_by=tg_id)
    did = botdb.add_division(con, eid, name=div, field_size=field_size)
    if join:
        botdb.add_participant(con, did, tg_id=tg_id, athlete=None)
    return eid, did


def test_list_competitions():
    from tjbot import db as botdb
    con = _con()
    eid, did = _make_event(botdb, con, name="Открытый кубок", tg_id=11111111,
                           city="Город-А", date="2026-04-12")
    rows = botdb.list_competitions(con, 11111111)
    match = next((r for r in rows if r["id"] == eid), None)
    assert match is not None
    assert match["name"] == "Открытый кубок"
    assert match["date_start"] == "2026-04-12"
    assert match["division_id"] == did
    con.close()


def test_list_competitions_orders_newest_first():
    from tjbot import db as botdb
    con = _con()
    old, _ = _make_event(botdb, con, name="Старый", tg_id=1, city="A", date="2026-01-01")
    new, _ = _make_event(botdb, con, name="Новый", tg_id=1, city="B", date="2026-05-01")
    rows = botdb.list_competitions(con, 1)
    ids = [r["id"] for r in rows]
    assert ids.index(new) < ids.index(old)
    con.close()


def test_list_competitions_hides_other_athletes_events():
    from tjbot import db as botdb
    con = _con()
    mine, _ = _make_event(botdb, con, name="Моё", tg_id=111)
    theirs, _ = _make_event(botdb, con, name="Чужое", tg_id=222)
    ids = [r["id"] for r in botdb.list_competitions(con, 111)]
    assert mine in ids
    assert theirs not in ids
    con.close()


def test_list_competitions_empty_for_non_participant():
    from tjbot import db as botdb
    con = _con()
    _make_event(botdb, con, name="Чужое", tg_id=222)
    assert botdb.list_competitions(con, 999) == []
    con.close()


def test_list_competitions_ignores_event_without_participation():
    from tjbot import db as botdb
    con = _con()
    orphan, _ = _make_event(botdb, con, name="Без участия", tg_id=111, join=False)
    ids = [r["id"] for r in botdb.list_competitions(con, 111)]
    assert orphan not in ids
    con.close()


def test_list_competitions_division_is_athletes_own():
    from tjbot import db as botdb
    con = _con()
    eid = botdb.create_event(con, name="Мультидив", city="A", date_start="2026-04-12",
                             date_end="2026-04-12", sport="crossfit", fmt="", created_by=111)
    botdb.add_division(con, eid, name="RX")
    mine = botdb.add_division(con, eid, name="PRO")
    botdb.add_participant(con, mine, tg_id=111, athlete=None)
    row = next(r for r in botdb.list_competitions(con, 111) if r["id"] == eid)
    assert row["division_id"] == mine
    con.close()


def test_list_competitions_dedups_multiple_participant_rows():
    from tjbot import db as botdb
    con = _con()
    eid, did = _make_event(botdb, con, name="Дубли", tg_id=111)
    botdb.add_participant(con, did, tg_id=111, athlete=None)
    botdb.add_participant(con, did, tg_id=111, athlete=None)
    rows = [r for r in botdb.list_competitions(con, 111) if r["id"] == eid]
    assert len(rows) == 1
    con.close()


def test_list_other_competitions_shows_only_foreign():
    from tjbot import db as botdb
    con = _con()
    mine, _ = _make_event(botdb, con, name="Моё", tg_id=111)
    theirs, _ = _make_event(botdb, con, name="Чужое", tg_id=222)
    ids = [r["id"] for r in botdb.list_other_competitions(con, 111)]
    assert theirs in ids
    assert mine not in ids
    con.close()


def test_list_other_competitions_empty_when_all_mine():
    from tjbot import db as botdb
    con = _con()
    _make_event(botdb, con, name="Моё", tg_id=111)
    assert botdb.list_other_competitions(con, 111) == []
    con.close()


def test_list_other_competitions_orders_newest_first():
    from tjbot import db as botdb
    con = _con()
    old, _ = _make_event(botdb, con, name="Старый", tg_id=222, date="2026-01-01")
    new, _ = _make_event(botdb, con, name="Новый", tg_id=222, date="2026-05-01")
    ids = [r["id"] for r in botdb.list_other_competitions(con, 111)]
    assert ids.index(new) < ids.index(old)
    con.close()


def test_list_other_competitions_has_division_id():
    from tjbot import db as botdb
    con = _con()
    eid, did = _make_event(botdb, con, name="Чужое", tg_id=222)
    row = next(r for r in botdb.list_other_competitions(con, 111) if r["id"] == eid)
    assert row["division_id"] == did
    con.close()


def test_format_other_view_renders_event_and_stages():
    from tjbot.handlers.competition import _format_other_view
    full = {"name": "Кубок", "city": "Город-А", "date_start": "2026-04-12",
            "divisions": [{"id": 1, "name": "PRO"}, {"id": 2, "name": "RX"}]}
    stages_by_div = {1: [{"idx": 1, "name": "Fran"}, {"idx": 2, "name": "Grace"}], 2: []}
    text = _format_other_view(full, stages_by_div)
    assert "Кубок" in text
    assert "Город-А" in text
    assert "2026-04-12" in text
    assert "PRO" in text and "RX" in text
    assert "Fran" in text and "Grace" in text
    assert "нет" in text.lower()


def test_others_flow_wired_into_conversation():
    from tjbot.handlers import competition as comp
    h = comp.handler()
    patterns = [ep.pattern.pattern for ep in h.entry_points
                if hasattr(ep, "pattern") and ep.pattern is not None]
    assert any(p == r"^others:list$" for p in patterns)
    assert any(p == r"^otherpick:" for p in patterns)
    assert any(p == r"^otherview:" for p in patterns)


def test_fill_flow_wired_into_conversation():
    from tjbot.handlers import competition as comp
    h = comp.handler()
    patterns = [ep.pattern.pattern for ep in h.entry_points
                if hasattr(ep, "pattern") and ep.pattern is not None]
    assert any(p == r"^fillpick:" for p in patterns)
    assert comp.FILL_PICK_DIV in h.states
