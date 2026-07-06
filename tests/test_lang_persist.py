import tjbot.db as db


def _con(tmp_path):
    con = db.connect(str(tmp_path / "t.db"))
    db.init_schema(con)
    return con


def test_lang_defaults_to_ru(tmp_path):
    con = _con(tmp_path)
    assert db.user_lang(con, 123) == "ru"


def test_set_and_get_lang(tmp_path):
    con = _con(tmp_path)
    db.save_user(con, 123, nick="a", height_cm=180, weight_kg=80, sex="m", gym="G")
    db.set_lang(con, 123, "en")
    assert db.user_lang(con, 123) == "en"


def test_lang_column_survives_existing_db(tmp_path):
    con = db.connect(str(tmp_path / "t.db"))
    con.execute('CREATE TABLE users ("tg_id" INTEGER PRIMARY KEY, "nick" TEXT)')
    con.commit()
    db.init_schema(con)
    assert "lang" in [r[1] for r in con.execute("PRAGMA table_info(users)")]
