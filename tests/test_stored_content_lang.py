import tjbot.db as db


def _con(tmp):
    c = db.connect(str(tmp / "t.db"))
    db.init_schema(c)
    return c


def test_wk_narrative_lang_isolation(tmp_path):
    c = _con(tmp_path)
    db.wk_narrative_put(c, 1, "2026-07-03", "claude", '[{"kind":"x"}]', lang="ru")
    assert db.wk_narrative_get(c, 1, "2026-07-03", "ru") is not None
    assert db.wk_narrative_get(c, 1, "2026-07-03", "en") is None


def test_claude_review_lang_isolation(tmp_path):
    c = _con(tmp_path)
    db.claude_review_put(c, 1, "2026-07-03", "текст", lang="ru")
    assert db.claude_review_get(c, 1, "2026-07-03", "ru")
    assert db.claude_review_get(c, 1, "2026-07-03", "en") is None


def test_next_advice_lang_isolation(tmp_path):
    c = _con(tmp_path)
    db.next_advice_put(c, 1, "gemini", "совет", lang="ru")
    assert db.next_advice_get(c, 1, "ru")
    assert db.next_advice_get(c, 1, "en") is None
