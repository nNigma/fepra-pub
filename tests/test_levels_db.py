from __future__ import annotations
import sqlite3
from tjbot import db as botdb


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def test_seed_standards_idempotent():
    con = _con()
    botdb.seed_standards(con)
    n1 = con.execute("SELECT COUNT(*) FROM disciplines").fetchone()[0]
    ps1 = con.execute("SELECT COUNT(*) FROM perf_standards").fetchone()[0]
    botdb.seed_standards(con)
    n2 = con.execute("SELECT COUNT(*) FROM disciplines").fetchone()[0]
    assert n1 == n2 and n1 == 36        # 13 лифтов + 23 бенчмарка
    assert ps1 == 36 * 5 * 2
    row = con.execute("SELECT * FROM disciplines WHERE id='deadlift'").fetchone()
    assert row["name_ru"] == "Становая" and row["basis"] == "bw_ratio"


def test_seed_standards_column_order_independent():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    con.execute("DROP TABLE disciplines")
    con.execute(
        'CREATE TABLE disciplines ("id" TEXT PRIMARY KEY, "name_ru" TEXT, "kind" TEXT, '
        '"unit" TEXT, "better" TEXT, "basis" TEXT, "ontology" TEXT, "order_idx" INTEGER)')
    con.execute('ALTER TABLE disciplines ADD COLUMN "name_en" TEXT')
    botdb.seed_standards(con)
    kinds = {r["kind"] for r in con.execute("SELECT kind FROM disciplines").fetchall()}
    assert kinds == {"lift", "benchmark"}, kinds
    units = {r["unit"] for r in con.execute("SELECT unit FROM disciplines").fetchall()}
    assert units == {"kg", "rounds", "time"}, units
    row = con.execute("SELECT * FROM disciplines WHERE id='thruster'").fetchone()
    assert row["kind"] == "lift"
    assert row["unit"] == "kg"
    assert row["ontology"] == "thruster"
    assert row["name_en"] == "Thruster"
    assert row["order_idx"] == 5


def test_add_and_best_result_lift():
    con = _con()
    botdb.seed_standards(con)
    botdb.add_result(con, tg_id=1, discipline="deadlift", value=130, reps=1,
                     est_1rm=130, source="manual", day="2026-06-26")
    botdb.add_result(con, tg_id=1, discipline="deadlift", value=100, reps=5,
                     est_1rm=116.7, source="manual", day="2026-06-20")
    best = botdb.best_results(con, 1)
    assert best["deadlift"]["est_1rm"] == 130


def test_best_result_benchmark_lower():
    con = _con()
    botdb.seed_standards(con)
    botdb.add_result(con, tg_id=1, discipline="fran", value=252, source="manual", day="2026-06-01")
    botdb.add_result(con, tg_id=1, discipline="fran", value=300, source="manual", day="2026-05-01")
    best = botdb.best_results(con, 1)
    assert best["fran"]["value"] == 252
