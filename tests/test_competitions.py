from __future__ import annotations
import sqlite3
from tjbot import db as botdb

def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con

def test_create_event_division_participant():
    con = _con()
    eid = botdb.create_event(con, name="Кубок Владимира", city="Владимир",
                             date_start="2026-04-12", date_end="2026-04-12",
                             sport="crossfit", fmt="6 этапов", created_by=12345678)
    did = botdb.add_division(con, eid, name="PRO", field_size=22)
    pid = botdb.add_participant(con, did, tg_id=12345678, athlete="Я")
    assert eid > 0 and did > 0 and pid > 0
    ev = botdb.get_event(con, eid)
    assert ev["name"] == "Кубок Владимира"
    assert ev["divisions"][0]["name"] == "PRO"


def test_find_by_city_date_and_stage_results():
    con = _con()
    eid = botdb.create_event(con, name="Кубок Владимира", city="Владимир",
        date_start="2026-04-12", date_end="2026-04-12", sport="crossfit", fmt="", created_by=1)
    did = botdb.add_division(con, eid, name="PRO", field_size=22)
    found = botdb.find_events_by_city_date(con, city="владимир", date="2026-04-12")
    assert len(found) == 1 and found[0]["id"] == eid
    sid = botdb.add_stage(con, did, idx=1, name="Гребля+бег", prescription="...",
                          movements=["гребля", "бег"], fmt="text")
    botdb.add_comp_result(con, sid, athlete="Я", value="13:54", place=9, points=9)
    stages = botdb.get_stages(con, did)
    assert stages[0]["results"][0]["place"] == 9


def test_set_total_confirm():
    con = _con()
    eid = botdb.create_event(con, name="X", city="Y", date_start="2026-01-01",
        date_end="2026-01-01", sport="crossfit", fmt="", created_by=1)
    did = botdb.add_division(con, eid, name="PRO", field_size=22)
    pid = botdb.add_participant(con, did, tg_id=1, athlete="Я")
    botdb.set_total(con, pid, final_place=6, total_points=51, confirmed=1)
    p = con.execute('SELECT * FROM comp_participants WHERE id=?', (pid,)).fetchone()
    assert p["final_place"] == 6 and p["confirmed_total"] == 1


def test_suggest_total_sum_and_place():
    con = _con()
    eid = botdb.create_event(con, name="X", city="Y", date_start="2026-01-01",
        date_end="2026-01-01", sport="crossfit", fmt="", created_by=1)
    did = botdb.add_division(con, eid, name="PRO", field_size=3)
    s1 = botdb.add_stage(con, did, idx=1, name="К1", prescription="", movements=[], fmt="text")
    s2 = botdb.add_stage(con, did, idx=2, name="К2", prescription="", movements=[], fmt="text")
    for st, places in [(s1, {"Я":3,"A":1,"B":2}), (s2, {"Я":2,"A":3,"B":1})]:
        for ath, pl in places.items():
            botdb.add_comp_result(con, st, athlete=ath, value="x", place=pl, points=pl)
    sug = botdb.suggest_total(con, did, "Я")
    assert sug["total_points"] == 5 and sug["final_place"] == 3


def test_percentile_and_capacities():
    from tj.analysis.competitions import percentile, capacity_grades
    assert percentile(1, 22) == 100.0
    assert percentile(22, 22) == round(1/22*100, 1)
    stages = [
        {"movements": ["гребля", "бег"], "result": {"place": 9}, "field": 22},
        {"movements": ["рывок"], "result": {"place": 14}, "field": 22},
    ]
    caps = capacity_grades(stages)
    assert all(1 <= g <= 9 for g in caps.values())
    assert "Движок" in caps  # гребля/бег → Движок


def test_capacity_full_mapping():
    from tj.analysis.competitions import capacity_grades
    cases = {
        "выход силой": "Гимнастика",
        "канат": "Хват/тяга",
        "гантели": "Хват/тяга",
        "приседания": "Сила",
        "жим": "Над головой",
        "трастеры": "Над головой",
        "плавание": "Движок",
        "берпи": "Гимнастика",
    }
    for mv, axis in cases.items():
        stages = [{"movements": [mv], "result": {"place": 1}, "field": 10}]
        caps = capacity_grades(stages)
        assert axis in caps, f"{mv} -> {axis}, got {caps}"


def test_scenario_and_bestworst():
    from tj.analysis.competitions import points_scenario, best_worst
    stages = [{"idx": i, "name": f"К{i}", "result": {"place": p}, "field": 22}
              for i, p in enumerate([9, 7, 14, 4, 4, 13], start=1)]
    bw = best_worst(stages)
    assert bw["worst"][0]["name"] in ("К3", "К6")
    sc = points_scenario(stages, target_place=5)
    assert sc["new_total"] < sc["current_total"]

def test_totals_by_start_sorted():
    from tj.analysis.competitions import totals_by_start
    events = [
        {"date_start": "2026-04-12", "name": "Владимир", "final_place": 6, "field_size": 22},
        {"date_start": "2026-02-02", "name": "Красногорск", "final_place": 11, "field_size": 18},
    ]
    rows = totals_by_start(events)
    assert [r["name"] for r in rows] == ["Красногорск", "Владимир"]
    assert rows[0]["final_place"] == 11

def test_comp_blocks():
    from tj.analysis.narrative import comp_blocks
    analysis = {
        "best_worst": {"best": [{"name": "Бассейн"}], "worst": [{"name": "Рывок"}]},
        "scenario": {"gain": 9, "target_place": 5},
        "caps": {"Движок": 9, "Сила": 3, "Над головой": 2},
    }
    blocks = comp_blocks(analysis)
    kinds = [b.kind for b in blocks]
    assert "verdict" in kinds and "advice" in kinds

def test_event_report_shape():
    from tj.analysis.competitions import event_report
    con = _con()
    eid = botdb.create_event(con, name="Владимир", city="Владимир", date_start="2026-04-12",
        date_end="2026-04-12", sport="crossfit", fmt="", created_by=1)
    did = botdb.add_division(con, eid, name="PRO", field_size=22)
    botdb.add_participant(con, did, tg_id=1, athlete="Я")
    for i, (nm, mv, pl) in enumerate([("Гребля", ["гребля"], 9), ("Рывок", ["рывок"], 14)], start=1):
        sid = botdb.add_stage(con, did, idx=i, name=nm, prescription="", movements=mv, fmt="text")
        botdb.add_comp_result(con, sid, athlete="Я", value="x", place=pl, points=pl)
    rep = event_report(con, eid, tg_id=1)
    assert "radar" in rep and "dynamics" in rep and "narrative" in rep
    assert rep["name"] == "Владимир"

def test_total_report_rows_have_id():
    con = _con()
    eid = botdb.create_event(con, name="Владимир", city="Владимир", date_start="2026-04-12",
        date_end="2026-04-12", sport="crossfit", fmt="", created_by=1)
    did = botdb.add_division(con, eid, name="PRO", field_size=22)
    botdb.add_participant(con, did, tg_id=1, athlete="Я")
    from tj.analysis.competitions import total_report
    tr = total_report(con, 1)
    assert tr["starts"] == 1
    assert tr["totals"][0]["id"] == eid


def _make_event_with_stages(con, name, city, date, field, stages_data, tg_id):
    eid = botdb.create_event(con, name=name, city=city, date_start=date,
        date_end=date, sport="crossfit", fmt="", created_by=tg_id)
    did = botdb.add_division(con, eid, name="PRO", field_size=field)
    botdb.add_participant(con, did, tg_id=tg_id, athlete="Я")
    for i, (nm, mv, pl) in enumerate(stages_data, start=1):
        sid = botdb.add_stage(con, did, idx=i, name=nm, prescription="", movements=mv, fmt="text")
        botdb.add_comp_result(con, sid, athlete="Я", value="x", place=pl, points=pl)
    return eid


def test_total_report_enriched_one_event():
    from tj.analysis.competitions import total_report
    con = _con()
    _make_event_with_stages(con, "Владимир", "Владимир", "2026-04-12", 22,
        [("Гребля", ["гребля"], 4), ("Рывок", ["рывок"], 14)], tg_id=1)
    tr = total_report(con, 1)
    assert tr["starts"] == 1
    assert isinstance(tr["radars"], list) and len(tr["radars"]) == 1
    r = tr["radars"][0]
    assert r["name"] == "Владимир"
    assert r["date"] == "2026-04-12"
    assert isinstance(r["grades"], dict) and len(r["grades"]) > 0
    assert all(1 <= v <= 9 for v in r["grades"].values())
    bw = tr["best_worst"]
    assert "best" in bw and "worst" in bw
    assert len(bw["best"]) >= 1 and len(bw["worst"]) >= 1
    assert isinstance(tr["narrative"], list) and len(tr["narrative"]) > 0


def test_total_report_enriched_two_events():
    from tj.analysis.competitions import total_report
    con = _con()
    _make_event_with_stages(con, "Красногорск", "Красногорск", "2026-02-02", 18,
        [("Гребля+бег", ["гребля", "бег"], 5), ("Оверхед", ["оверхед"], 17)], tg_id=2)
    _make_event_with_stages(con, "Владимир", "Владимир", "2026-04-12", 22,
        [("Бассейн", ["плавание"], 4), ("Рывок", ["рывок"], 14)], tg_id=2)
    tr = total_report(con, 2)
    assert tr["starts"] == 2
    assert len(tr["radars"]) == 2
    assert tr["radars"][0]["name"] == "Владимир"
    bw = tr["best_worst"]
    assert len(bw["best"]) >= 1 and len(bw["worst"]) >= 1
    assert "Бассейн" in bw["best"][0]["name"] or "Гребля+бег" in bw["best"][0]["name"]
    assert isinstance(tr["narrative"], list) and len(tr["narrative"]) > 0
