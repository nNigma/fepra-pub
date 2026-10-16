from __future__ import annotations

import json
from datetime import date, timedelta

from tjbot import db as botdb
from tjbot import llm_gen

YDAY = (date.today() - timedelta(days=1)).isoformat()


def _db(tmp_path):
    p = tmp_path / "t.db"
    con = botdb.connect(str(p))
    botdb.init_schema(con)
    con.commit()
    return con, str(p)


def _seed_meal(con, tg, day):
    botdb.add_meal(con, tg, day, f"{day}T12:00:00",
                   [{"name": "греча", "kcal": 500, "protein_g": 20, "fat_g": 10,
                     "carb_g": 60}], {"kcal": 500, "protein_g": 20, "fat_g": 10,
                                      "carb_g": 60})


def test_generate_one_skips_when_cached(monkeypatch, tmp_path):
    con, path = _db(tmp_path)
    _seed_meal(con, 1, "2026-07-10")
    botdb.llm_cache_put(con, 1, "nutr_day", "2026-07-10", "h0", "старый", "gemini")
    called = {"n": 0}
    monkeypatch.setattr(llm_gen.llm_coach, "coach",
                        lambda *a, **k: (called.__setitem__("n", called["n"] + 1), ("t", "claude"))[1])
    assert llm_gen.generate_one(con, path, 1, "nutr_day", "2026-07-10", "ru") is False
    assert called["n"] == 0


def test_generate_one_force_regenerates(monkeypatch, tmp_path):
    con, path = _db(tmp_path)
    _seed_meal(con, 1, "2026-07-10")
    botdb.llm_cache_put(con, 1, "nutr_day", "2026-07-10", "h0", "старый", "gemini")
    monkeypatch.setattr(llm_gen.llm_coach, "coach", lambda *a, **k: ("НОВЫЙ разбор", "claude"))
    monkeypatch.setattr(llm_gen.llm_coach, "payload_hash", lambda *a, **k: "h1")
    assert llm_gen.generate_one(con, path, 1, "nutr_day", "2026-07-10", "ru", force=True) is True
    row = botdb.llm_cache_get_latest(con, 1, "nutr_day", "2026-07-10", "ru")
    assert row["text"] == "НОВЫЙ разбор" and row["engine"] == "claude"


def test_generate_one_none_payload(monkeypatch, tmp_path):
    con, path = _db(tmp_path)   # нет еды за день → payload None
    monkeypatch.setattr(llm_gen.llm_coach, "coach", lambda *a, **k: ("t", "claude"))
    assert llm_gen.generate_one(con, path, 1, "nutr_day", "2026-07-10", "ru", force=True) is False


def test_generate_one_summary_writes_advice(monkeypatch, tmp_path):
    con, path = _db(tmp_path)
    monkeypatch.setattr(llm_gen, "build_payload", lambda *a, **k: {"x": 1})
    monkeypatch.setattr(llm_gen.llm_coach, "payload_hash", lambda *a, **k: "h")
    monkeypatch.setattr(llm_gen.llm_coach, "coach", lambda *a, **k: ("разбор\nСОВЕТ: беги", "claude"))
    monkeypatch.setattr(llm_gen.llm_coach, "parse_advice_line", lambda text, lang: "беги")
    assert llm_gen.generate_one(con, path, 1, "summary", "30d", "ru", force=True) is True
    adv = botdb.next_advice_get(con, 1, "ru")
    assert adv and "беги" in adv["text"]


def test_generate_one_refresh_stale_skips_same_hash(monkeypatch, tmp_path):
    con, path = _db(tmp_path)
    _seed_meal(con, 1, YDAY)
    monkeypatch.setattr(llm_gen.llm_coach, "payload_hash", lambda *a, **k: "h0")
    botdb.llm_cache_put(con, 1, "nutr_day", YDAY, "h0", "старый", "claude")
    called = {"n": 0}
    monkeypatch.setattr(llm_gen.llm_coach, "coach",
                        lambda *a, **k: (called.__setitem__("n", called["n"] + 1), ("t", "claude"))[1])
    assert llm_gen.generate_one(con, path, 1, "nutr_day", YDAY, "ru", refresh_stale=True) is False
    assert called["n"] == 0
    assert botdb.llm_cache_get_latest(con, 1, "nutr_day", YDAY, "ru")["text"] == "старый"


def test_generate_one_refresh_stale_regenerates_changed_hash(monkeypatch, tmp_path):
    con, path = _db(tmp_path)
    _seed_meal(con, 1, YDAY)
    botdb.llm_cache_put(con, 1, "nutr_day", YDAY, "h0", "старый", "claude")
    monkeypatch.setattr(llm_gen.llm_coach, "payload_hash", lambda *a, **k: "h1")
    monkeypatch.setattr(llm_gen.llm_coach, "coach", lambda *a, **k: ("СВЕЖИЙ", "claude"))
    assert llm_gen.generate_one(con, path, 1, "nutr_day", YDAY, "ru", refresh_stale=True) is True
    row = botdb.llm_cache_get_latest(con, 1, "nutr_day", YDAY, "ru")
    assert row["text"] == "СВЕЖИЙ" and row["data_hash"] == "h1"


def test_sweep_passes_refresh_stale(monkeypatch, tmp_path):
    con, path = _db(tmp_path)
    _seed_meal(con, 1, YDAY)
    seen = []
    monkeypatch.setattr(llm_gen, "generate_one",
                        lambda con, db, tg, k, ref, lang, force=False, refresh_stale=False:
                        seen.append((k, refresh_stale)) or True)
    llm_gen.sweep(con, path, 1, "ru", refresh_stale=True, kinds={"nutr_day", "nutr_week"})
    assert seen and all(rs for _, rs in seen)


def test_sweep_kinds_filter(monkeypatch, tmp_path):
    con, path = _db(tmp_path)
    _seed_meal(con, 1, YDAY)          # окно sweep_targets отсчитывается от сегодня
    seen = []
    monkeypatch.setattr(llm_gen, "generate_one",
                        lambda con, db, tg, k, ref, lang, **kw: seen.append((k, ref)) or True)
    llm_gen.sweep(con, path, 1, "ru", force=True, kinds={"summary", "nutr_day", "nutr_week"})
    kinds = {k for k, _ in seen}
    assert "workout" not in kinds and "competitions" not in kinds
    assert ("summary", "30d") in seen and ("nutr_day", YDAY) in seen


def test_sweep_targets_skips_days_outside_window(tmp_path):
    con, _ = _db(tmp_path)
    old = (date.today() - timedelta(days=30)).isoformat()
    _seed_meal(con, 1, old)
    _seed_meal(con, 1, YDAY)
    refs = [ref for kind, ref in llm_gen.sweep_targets(con, 1) if kind == "nutr_day"]
    assert refs == [YDAY]


def test_sweep_targets_skips_today_nutrition(tmp_path):
    """Питание текущего дня не разбираем: день не прожит, ужина в нём нет."""
    con, _ = _db(tmp_path)
    today = date.today().isoformat()
    _seed_meal(con, 1, YDAY)
    _seed_meal(con, 1, today)
    targets = llm_gen.sweep_targets(con, 1)
    assert ("nutr_day", today) not in targets
    assert ("nutr_day", YDAY) in targets
    assert ("nutr_week", YDAY) in targets          # свод привязан к последнему прожитому


def test_sweep_targets_no_nutrition_when_only_today(tmp_path):
    con, _ = _db(tmp_path)
    _seed_meal(con, 1, date.today().isoformat())
    kinds = {k for k, _ in llm_gen.sweep_targets(con, 1)}
    assert "nutr_day" not in kinds and "nutr_week" not in kinds
