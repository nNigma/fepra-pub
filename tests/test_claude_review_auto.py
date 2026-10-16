"""tjbot.claude_review: авторазборы через шлюз llm.text_complete (крон)."""
from __future__ import annotations

import datetime
import json

from tj import llm
from tjbot import claude_review as cr
from tjbot import db as botdb


def _con(tmp_path):
    con = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(con)
    return con


def _llm_answer():
    nar = [{"kind": "verdict", "title": "Что развивает", "body": "б"},
           {"kind": "section", "title": "Зоны", "body": "б"},
           {"kind": "section", "title": "Интенсивные минуты", "body": "б"},
           {"kind": "risk", "title": "Риск", "body": "б"},
           {"kind": "advice", "title": "Совет", "body": "б"}]
    return json.dumps({"review_md": "## Как ты подошёл\nтекст", "narrative": nar},
                      ensure_ascii=False)


def test_valid_narrative():
    assert cr._valid_narrative(json.loads(_llm_answer())["narrative"]) is True
    assert cr._valid_narrative([]) is False
    assert cr._valid_narrative([{"kind": "x"}]) is False
    assert cr._valid_narrative("не список") is False


def test_extract_obj_fenced():
    raw = "```json\n" + _llm_answer() + "\n```"
    obj = cr._extract_obj(raw)
    assert obj and "review_md" in obj


def test_review_day_saves(tmp_path, monkeypatch):
    con = _con(tmp_path)
    monkeypatch.setattr(cr, "workout_report",
                        lambda *a, **k: {"trimp": 42, "history": []})
    monkeypatch.setattr(cr.llm_coach, "workout_payload",
                        lambda rep: {"board": "доска", "work": {"strength": [1]}})
    monkeypatch.setattr(llm, "text_complete", lambda p, **k: (_llm_answer(), "agent"))
    res = cr.review_day(con, 111, "2026-07-08", "crossfit")
    assert res.get("ok") is True and res.get("narrative") is True
    row = con.execute('SELECT "text" FROM claude_review WHERE "tg_id"=111').fetchone()
    assert row and "Как ты подошёл" in row["text"]
    nar = con.execute('SELECT * FROM wk_narrative WHERE "tg_id"=111').fetchone()
    assert nar is not None
    assert nar["source"] == "agent"          # подпись — фактический движок
    con.close()


def test_review_day_skips_crossfit_without_board(tmp_path, monkeypatch):
    con = _con(tmp_path)
    monkeypatch.setattr(cr, "workout_report", lambda *a, **k: {"trimp": 1})
    monkeypatch.setattr(cr.llm_coach, "workout_payload",
                        lambda rep: {"board": None, "work": None})
    called = []
    monkeypatch.setattr(llm, "text_complete",
                        lambda p, **k: called.append(1) or (_llm_answer(), "agent"))
    res = cr.review_day(con, 111, "2026-07-08", "crossfit")
    assert "skip" in res and not called
    con.close()


def test_review_day_llm_fail(tmp_path, monkeypatch):
    con = _con(tmp_path)
    monkeypatch.setattr(cr, "workout_report",
                        lambda *a, **k: {"trimp": 1, "history": []})
    monkeypatch.setattr(cr.llm_coach, "workout_payload",
                        lambda rep: {"board": "доска", "work": {}})
    monkeypatch.setattr(llm, "text_complete", lambda p, **k: (None, None))
    res = cr.review_day(con, 111, "2026-07-08", "crossfit")
    assert res.get("error") == "llm"
    assert con.execute('SELECT COUNT(*) c FROM claude_review').fetchone()["c"] == 0
    con.close()


def test_run_all_without_any_llm(monkeypatch):
    """Гейт крона — has_text_llm: нет ни агента, ни claude, ни Gemini."""
    monkeypatch.setattr(llm, "has_text_llm", lambda: False)
    out = cr.run_all()
    assert out and "error" in out[0]


def test_latest_weight(tmp_path):
    con = _con(tmp_path)
    assert botdb.latest_weight(con, 111) is None
    botdb.set_bodyweight(con, "2026-07-05", 82.5, 111)
    botdb.set_bodyweight(con, "2026-07-08", 83.0, 111)
    assert botdb.latest_weight(con, 111) == 83.0
    assert botdb.latest_weight(con, 111, "2026-07-06") == 82.5   # не позже дня
    assert botdb.latest_weight(con, 222) is None                 # чужой вес не течёт
    con.close()


def test_review_day_includes_bodyweight(tmp_path, monkeypatch):
    con = _con(tmp_path)
    botdb.set_bodyweight(con, "2026-07-07", 83.0, 111)
    monkeypatch.setattr(cr, "workout_report",
                        lambda *a, **k: {"trimp": 1, "history": []})
    monkeypatch.setattr(cr.llm_coach, "workout_payload",
                        lambda rep: {"board": "доска", "work": {}})
    prompts = []
    monkeypatch.setattr(llm, "has_claude_text", lambda: True)
    monkeypatch.setattr(llm, "claude_complete",
                        lambda p, **k: prompts.append(p) or _llm_answer())
    cr.review_day(con, 111, "2026-07-08", "crossfit")
    assert '"bodyweight_kg": 83.0' in prompts[0]
    con.close()


def test_admin_review_report():
    from tjbot.handlers import admin
    res = [{"tg_id": 111, "days": [{"ok": True}, {"skip": "x"}, {"error": "llm"}],
            "summary": True, "advice": True}]
    text = admin._review_report(res, "ru")
    assert "111" in text and "разобрано 1" in text and "пропущено 1" in text
    assert "ошибок 1" in text and "✅" in text
    fail = admin._review_report([{"error": "claude CLI недоступен"}], "ru")
    assert "упал" in fail


def test_admin_kb_has_review_button():
    from tjbot.handlers import admin
    from tj import i18n
    kb = admin.admin_kb("ru")
    texts = [b.text if hasattr(b, "text") else b for row in kb.keyboard for b in row]
    assert i18n.t("btn.admin_review", "ru") in texts


def test_run_user_regenerates_only_stale(tmp_path, monkeypatch):
    con = _con(tmp_path)
    tg = 1
    day = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    botdb.add_meal(con, tg, day, f"{day}T12:00:00",
                   [{"name": "греча", "kcal": 500, "protein_g": 20, "fat_g": 10, "carb_g": 60}],
                   {"kcal": 500, "protein_g": 20, "fat_g": 10, "carb_g": 60})
    con.commit()
    path = str(tmp_path / "t.db")
    orig = cr.llm_gen.build_payload
    monkeypatch.setattr(cr.llm_gen, "build_payload",
                        lambda con, db, kind, ref, tg_id: {"x": 1} if kind == "summary" else orig(con, db, kind, ref, tg_id))
    h = cr.llm_gen.llm_coach.payload_hash(orig(con, path, "nutr_day", day, tg), "ru", False)
    botdb.llm_cache_put(con, tg, "nutr_day", day, h, "старый", "claude")
    monkeypatch.setattr(llm, "claude_complete", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(cr.llm_gen.llm_coach, "coach",
                        lambda kind, *a, **k: calls.append(kind) or ("разбор", "claude"))
    cr.run_user(con, tg, db_path=path)
    assert botdb.llm_cache_get_latest(con, tg, "nutr_day", day, "ru")["text"] == "старый"
    assert "nutr_day" not in calls
    assert "summary" in calls and "nutr_week" in calls
    con.close()


def test_run_user_lookback_two_days(tmp_path, monkeypatch):
    con = _con(tmp_path)
    old = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    fresh = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    monkeypatch.setattr(cr.botdb, "claude_reviews_pending",
                        lambda con, tg, lang="ru": [{"day": old, "sport": "run"},
                                                    {"day": fresh, "sport": "run"}])
    seen = []
    monkeypatch.setattr(cr, "review_day",
                        lambda con, tg, day, sport, lang="ru", db_path=None:
                        seen.append(day) or {"day": day, "ok": True})
    monkeypatch.setattr(cr.llm_gen, "sweep", lambda *a, **k: None)
    cr.run_user(con, 1, db_path=str(tmp_path / "t.db"))
    assert seen == [fresh]
    con.close()


def test_notify_admins_on_errors(monkeypatch):
    sent = []
    monkeypatch.setattr(cr, "_bot_token", lambda: "T")
    monkeypatch.setattr(cr.access, "load_admins", lambda path=None: {42})
    monkeypatch.setattr(cr, "_tg_send", lambda token, chat, text: sent.append((chat, text)))
    out = [{"tg_id": 1, "days": [{"day": "2026-07-18", "error": "llm"}], "summary": True},
           {"tg_id": 2, "error": "OperationalError"}]
    assert cr.notify_admins(out) is True
    assert sent and sent[0][0] == 42
    assert "2026-07-18" in sent[0][1] and "OperationalError" in sent[0][1]


def test_notify_admins_silent_when_clean(monkeypatch):
    sent = []
    monkeypatch.setattr(cr, "_bot_token", lambda: "T")
    monkeypatch.setattr(cr.access, "load_admins", lambda path=None: {42})
    monkeypatch.setattr(cr, "_tg_send", lambda token, chat, text: sent.append((chat, text)))
    out = [{"tg_id": 1, "days": [{"ok": True}, {"skip": "no data"}], "summary": True}]
    assert cr.notify_admins(out) is False
    assert not sent


def test_notify_admins_global_error(monkeypatch):
    sent = []
    monkeypatch.setattr(cr, "_bot_token", lambda: "T")
    monkeypatch.setattr(cr.access, "load_admins", lambda path=None: {42, 43})
    monkeypatch.setattr(cr, "_tg_send", lambda token, chat, text: sent.append(chat))
    assert cr.notify_admins([{"error": "claude CLI недоступен (bin не найден)"}]) is True
    assert sorted(sent) == [42, 43]


def test_flight_review_fills_summary_and_nutrition_cache(tmp_path, monkeypatch):
    con = _con(tmp_path)
    tg = 1
    day = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    botdb.add_meal(con, tg, day, f"{day}T12:00:00",
                   [{"name": "греча", "kcal": 500, "protein_g": 20, "fat_g": 10, "carb_g": 60}],
                   {"kcal": 500, "protein_g": 20, "fat_g": 10, "carb_g": 60})
    con.commit()
    monkeypatch.setattr(llm, "claude_complete", lambda *a, **k: None)
    monkeypatch.setattr(cr.llm_gen.llm_coach, "coach", lambda *a, **k: ("разбор", "claude"))
    monkeypatch.setattr(cr.llm_gen.llm_coach, "payload_hash", lambda *a, **k: "h")
    orig = cr.llm_gen.build_payload
    monkeypatch.setattr(cr.llm_gen, "build_payload",
                        lambda con, db, kind, ref, tg_id: {"x": 1} if kind == "summary" else orig(con, db, kind, ref, tg_id))
    cr.run_user(con, tg, db_path=str(tmp_path / "t.db"))
    assert botdb.llm_cache_get_latest(con, tg, "summary", "30d", "ru") is not None
    assert botdb.llm_cache_get_latest(con, tg, "nutr_day", day, "ru") is not None
    con.close()


def _seed_act(con, tg_id, day, sport, source, aid):
    con.execute('INSERT INTO activities ("day","sport","activity_id","source","tg_id") '
                'VALUES (?,?,?,?,?)', (day, sport, aid, source, tg_id))
    con.commit()


def test_pending_one_row_per_day_prefers_manual(tmp_path):
    """День с ручной записью и активностью с часов — один разбор, тип ручной."""
    con = _con(tmp_path)
    _seed_act(con, 111, "2026-09-13", "crossfit", "garmin", "g1")
    _seed_act(con, 111, "2026-09-13", "weightlifting", "manual", "m1")
    pending = botdb.claude_reviews_pending(con, 111)
    assert pending == [{"day": "2026-09-13", "sport": "weightlifting"}]
    con.close()


def test_pending_keeps_separate_days(tmp_path):
    con = _con(tmp_path)
    _seed_act(con, 111, "2026-09-12", "crossfit", "garmin", "g1")
    _seed_act(con, 111, "2026-09-13", "crossfit", "garmin", "g2")
    assert [p["day"] for p in botdb.claude_reviews_pending(con, 111)] == \
        ["2026-09-13", "2026-09-12"]
    con.close()


def test_run_user_skips_today(tmp_path, monkeypatch):
    """Разбор идёт по завершённым дням: сегодня не берём, вчера берём."""
    today = datetime.date.today()
    yday = today - datetime.timedelta(days=1)
    con = _con(tmp_path)
    _seed_act(con, 111, today.isoformat(), "crossfit", "manual", "m-today")
    _seed_act(con, 111, yday.isoformat(), "crossfit", "manual", "m-yday")
    seen = []
    monkeypatch.setattr(cr, "review_day",
                        lambda con, tg, day, sport=None, lang="ru", db_path=None:
                        seen.append(day) or {"day": day, "ok": True})
    monkeypatch.setattr(cr.llm_gen, "sweep", lambda *a, **k: [])
    cr.run_user(con, 111, db_path=str(tmp_path / "t.db"))
    assert seen == [yday.isoformat()]
    con.close()


def test_run_user_catches_up_missed_day(tmp_path, monkeypatch):
    """Прогон раз в сутки: если сутки пропустили, позавчера доберётся."""
    today = datetime.date.today()
    con = _con(tmp_path)
    for back in (1, 2, 3):
        d = (today - datetime.timedelta(days=back)).isoformat()
        _seed_act(con, 111, d, "crossfit", "manual", f"m-{back}")
    seen = []
    monkeypatch.setattr(cr, "review_day",
                        lambda con, tg, day, sport=None, lang="ru", db_path=None:
                        seen.append(day) or {"day": day, "ok": True})
    monkeypatch.setattr(cr.llm_gen, "sweep", lambda *a, **k: [])
    cr.run_user(con, 111, db_path=str(tmp_path / "t.db"))
    assert sorted(seen) == sorted((today - datetime.timedelta(days=b)).isoformat()
                                  for b in (1, 2))          # позавчера в окне, третьего дня нет
    con.close()
