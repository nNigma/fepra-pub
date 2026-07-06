from tjbot import db as botdb

def test_garmin_account_crud(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    assert botdb.garmin_account_get(con, 111) is None
    botdb.garmin_account_set(con, 111, "a@b.c")
    acc = botdb.garmin_account_get(con, 111)
    assert acc["email"] == "a@b.c" and acc["status"] == "ok"
    botdb.garmin_account_set_status(con, 111, "expired")
    assert botdb.garmin_account_get(con, 111)["status"] == "expired"
    botdb.garmin_account_delete(con, 111)
    assert botdb.garmin_account_get(con, 111) is None

def test_tokenstore_path_per_user():
    p = botdb.garmin_tokenstore(111)
    assert str(p).endswith("garmin_tokens/111")
