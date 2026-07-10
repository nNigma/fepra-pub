from __future__ import annotations

from tjbot import db


def test_next_advice_ru_en_coexist(tmp_path):
    con = db.connect(str(tmp_path / "t.db")); db.init_schema(con)
    db.next_advice_put(con, 1, "claude", "русский совет", lang="ru")
    db.next_advice_put(con, 1, "claude", "english advice", lang="en")   # раньше падало по PK
    assert db.next_advice_get(con, 1, "ru")["text"] == "русский совет"
    assert db.next_advice_get(con, 1, "en")["text"] == "english advice"


def test_claude_review_ru_en_coexist(tmp_path):
    con = db.connect(str(tmp_path / "t.db")); db.init_schema(con)
    db.claude_review_put(con, 1, "2026-07-01", "разбор ru", lang="ru")
    db.claude_review_put(con, 1, "2026-07-01", "review en", lang="en")
    assert db.claude_review_get(con, 1, "2026-07-01", "ru") == "разбор ru"
    assert db.claude_review_get(con, 1, "2026-07-01", "en") == "review en"


def test_wk_narrative_ru_en_coexist(tmp_path):
    con = db.connect(str(tmp_path / "t.db")); db.init_schema(con)
    db.wk_narrative_put(con, 1, "2026-07-01", "claude", [{"kind": "x", "title": "т", "body": "ру"}], lang="ru")
    db.wk_narrative_put(con, 1, "2026-07-01", "claude", [{"kind": "x", "title": "t", "body": "en"}], lang="en")
    assert db.wk_narrative_get(con, 1, "2026-07-01", "ru")["blocks"][0]["body"] == "ру"
    assert db.wk_narrative_get(con, 1, "2026-07-01", "en")["blocks"][0]["body"] == "en"


def test_migration_preserves_old_rows(tmp_path):
    # старая схема без lang в PK -> init_schema перестраивает, данные целы
    con = db.connect(str(tmp_path / "t.db"))
    con.execute('CREATE TABLE next_advice ("tg_id" INTEGER, "source" TEXT, "text" TEXT, '
                '"created_at" TEXT, "lang" TEXT DEFAULT \'ru\', PRIMARY KEY ("tg_id","source"))')
    con.execute('INSERT INTO next_advice VALUES (5,"claude","старое",NULL,"ru")')
    con.commit()
    db.init_schema(con)
    pk = [r["name"] for r in con.execute('PRAGMA table_info("next_advice")') if r["pk"]]
    assert "lang" in pk
    assert db.next_advice_get(con, 5, "ru")["text"] == "старое"
