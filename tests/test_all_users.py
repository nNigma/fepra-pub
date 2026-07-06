from tjbot import db as botdb


def test_all_users_returns_id_and_nick(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.save_user(con, 111, nick="Аня", height_cm=170, weight_kg=60, sex="f", age=30, gym="Universe")
    botdb.save_user(con, 222, nick="Боря", height_cm=180, weight_kg=80, sex="m", age=35, gym="Universe")
    us = botdb.all_users(con)
    assert {u["tg_id"] for u in us} == {111, 222}
    assert {u["nick"] for u in us} == {"Аня", "Боря"}
