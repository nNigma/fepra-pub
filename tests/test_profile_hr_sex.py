from tjbot import db as botdb

def test_profile_hr_sex(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    botdb.save_user(con, 111, nick="a", height_cm=180, weight_kg=80, sex="m", age=36, gym="Universe")
    hr, sex = botdb.profile_hr_sex(con, 111)
    assert hr == 184 and sex == "m"

def test_profile_hr_sex_fallback(tmp_path):
    con = botdb.connect(tmp_path / "t.db"); botdb.init_schema(con)
    hr, sex = botdb.profile_hr_sex(con, 999)
    assert hr == 184 and sex == "m"
