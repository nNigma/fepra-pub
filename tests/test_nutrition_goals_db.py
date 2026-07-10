"""Цель питания/город в users, quality в meals: миграции и хелперы."""
from tjbot import db


def _con(tmp_path):
    con = db.connect(str(tmp_path / "t.db"))
    db.init_schema(con)
    return con


def test_goal_default_and_set(tmp_path):
    con = _con(tmp_path)
    con.execute("INSERT INTO users (tg_id, nick) VALUES (1, 'x')")
    con.commit()
    assert db.user_goal(con, 1) == "maintain"
    db.set_goal(con, 1, "recomp")
    assert db.user_goal(con, 1) == "recomp"


def test_goal_validates(tmp_path):
    con = _con(tmp_path)
    con.execute("INSERT INTO users (tg_id, nick) VALUES (1, 'x')")
    con.commit()
    try:
        db.set_goal(con, 1, "bogus")
        assert False
    except ValueError:
        pass


def test_city_default_and_set(tmp_path):
    con = _con(tmp_path)
    con.execute("INSERT INTO users (tg_id, nick) VALUES (1, 'x')")
    con.commit()
    assert db.user_city(con, 1) == "Москва"
    db.set_city(con, 1, "Казань")
    assert db.user_city(con, 1) == "Казань"


def test_meal_quality_columns(tmp_path):
    con = _con(tmp_path)
    mid = db.add_meal(con, 1, "2026-07-09", "2026-07-09T13:00",
                      [{"name": "греча", "kcal": 300}], {"kcal": 300},
                      quality=1, quality_note="цельная еда")
    row = con.execute("SELECT quality, quality_note FROM meals WHERE id=?", (mid,)).fetchone()
    assert row["quality"] == 1 and row["quality_note"] == "цельная еда"
    rows = db.meals_for_day(con, 1, "2026-07-09")
    assert rows[0]["quality"] == 1
