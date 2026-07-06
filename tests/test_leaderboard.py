from tjbot import db as botdb
from tj.analysis.leaderboard import leaderboard


def _seed(con, tg, nick, gym, sex, wt):
    botdb.save_user(con, tg, nick=nick, height_cm=175, weight_kg=wt, sex=sex, age=30, gym=gym)


def _lift(con, tg, disc, value, day):
    botdb.add_result(con, tg_id=tg, discipline=disc, value=value, source="manual", day=day, reps=1, est_1rm=value)


def test_overall_and_isolation(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.seed_standards(con)
    _seed(con, 1, "Silniy", "Universe", "m", 80); _lift(con, 1, "back_squat", 160, "2026-07-01")
    _seed(con, 2, "Sredniy", "Universe", "m", 80); _lift(con, 2, "back_squat", 90, "2026-07-01")
    _seed(con, 3, "Chuzhoy", "Другой", "m", 80); _lift(con, 3, "back_squat", 200, "2026-07-01")
    res = leaderboard(con, "Universe", "overall", me_tg_id=2)
    ids = [r["tg_id"] for r in res["rows"]]
    assert 3 not in ids
    assert ids[0] == 1 and ids[1] == 2
    assert res["rows"][0]["place"] == 1
    assert [r for r in res["rows"] if r["is_me"]][0]["tg_id"] == 2
    assert any(d["id"] == "back_squat" for d in res["disciplines"])


def test_discipline_sort_lift_desc(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con); botdb.seed_standards(con)
    _seed(con, 1, "A", "Universe", "m", 80); _lift(con, 1, "back_squat", 100, "2026-07-01")
    _seed(con, 2, "B", "Universe", "m", 80); _lift(con, 2, "back_squat", 140, "2026-07-01")
    _seed(con, 3, "C", "Universe", "m", 80)
    res = leaderboard(con, "Universe", "back_squat", me_tg_id=1)
    ids = [r["tg_id"] for r in res["rows"]]
    assert ids == [2, 1]
    assert 3 not in ids
