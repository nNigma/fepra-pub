from tjbot import db as botdb

def test_gym_members_by_gym(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.save_user(con, 1, nick="A", height_cm=180, weight_kg=80, sex="m", age=30, gym="Universe")
    botdb.save_user(con, 2, nick="B", height_cm=170, weight_kg=60, sex="f", age=28, gym="Universe")
    botdb.save_user(con, 3, nick="C", height_cm=175, weight_kg=70, sex="m", age=35, gym="Другой")
    ms = botdb.gym_members(con, "Universe")
    assert {m["tg_id"] for m in ms} == {1, 2}
    assert ms[0]["sex"] in ("m", "f") and "weight_kg" in ms[0]
