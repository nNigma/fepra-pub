from __future__ import annotations
import sqlite3
from tjbot import db as botdb
from tj.analysis.levels import goals_screen_data


def test_payload_json_serializable():
    import json
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    botdb.add_result(con, tg_id=11111111, discipline="deadlift", value=130, reps=1,
                     est_1rm=130, source="manual", day="2026-06-26")
    data = goals_screen_data(con, 11111111, "m", 79)
    json.dumps(data)
    assert data["lifts"][0]["name"] == "Становая"
