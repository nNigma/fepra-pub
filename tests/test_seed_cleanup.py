from __future__ import annotations

from tjbot import db


def test_seed_removes_stale_disciplines(tmp_path):
    con = db.connect(str(tmp_path / "t.db")); db.init_schema(con)
    con.execute('INSERT OR REPLACE INTO disciplines VALUES (?,?,?,?,?,?,?,?,?)',
                ("snatch", "Рывок", "Snatch", "lift", "kg", "higher", "bw_ratio", "snatch", 99))
    con.execute('INSERT INTO perf_standards ("benchmark","level","sex","target_value","metric") '
                'VALUES (?,?,?,?,?)', ("snatch", "Новичок", "m", 0.5, "bw_ratio"))
    con.commit()
    db.seed_standards(con)
    assert con.execute("SELECT COUNT(*) FROM disciplines WHERE id='snatch'").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM perf_standards WHERE benchmark='snatch'").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM disciplines WHERE id='squat_snatch'").fetchone()[0] == 1
