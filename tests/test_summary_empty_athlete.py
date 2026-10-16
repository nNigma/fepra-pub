"""Регрессия: атлет без строк в daily/activities — сводка не падает."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from tj.analysis.dashboard import summary_data
from tjbot import claude_review as cr
from tjbot import db as botdb
from tjbot import llm_gen
from tjapp import api
from tjapp.api import app, require_auth


def _empty_db(tmp_path, tg=6491988301):
    p = tmp_path / "t.db"
    con = botdb.connect(str(p))
    botdb.init_schema(con)
    botdb.save_user(con, tg, nick="empty", height_cm=180, weight_kg=75, sex="m",
                    age=30, gym="U")
    con.commit()
    return con, str(p), tg


def test_summary_data_empty_athlete_no_crash(tmp_path):
    con, path, tg = _empty_db(tmp_path)
    data = summary_data(path, "sqlite", 184, "m", date.today(), tg_id=tg)
    assert data["range"] == (None, None)
    assert data["today"] == date.today().isoformat()
    assert data["m"]["n_days"] == 0
    con.close()


def test_build_payload_summary_none_without_data(tmp_path):
    con, path, tg = _empty_db(tmp_path)
    assert llm_gen.build_payload(con, path, "summary", "30d", tg) is None
    con.close()


def test_sweep_summary_skips_empty_without_typeerror(tmp_path, capsys):
    con, path, tg = _empty_db(tmp_path)
    errs = llm_gen.sweep(con, path, tg, "ru", refresh_stale=True, kinds={"summary"})
    assert errs == []
    out = capsys.readouterr().out
    assert "TypeError" not in out
    con.close()


def test_api_summary_200_for_empty_athlete(tmp_path, monkeypatch):
    con, path, tg = _empty_db(tmp_path, tg=1)
    con.close()
    monkeypatch.setattr(api, "_db", lambda: path)
    monkeypatch.setattr(api, "is_pro", lambda _tg: True)
    app.dependency_overrides[require_auth] = lambda: {"id": 1}
    r = TestClient(app).get("/api/summary", headers={"X-Init-Data": "x"})
    assert r.status_code == 200
    body = r.json()
    assert body["range"] == [None, None] or body["range"] == (None, None)
    assert body["m"]["n_days"] == 0
    app.dependency_overrides.clear()


def test_run_user_reports_real_sweep_errors(tmp_path, monkeypatch):
    con, path, tg = _empty_db(tmp_path, tg=1)
    monkeypatch.setattr(cr.botdb, "claude_reviews_pending", lambda *a, **k: [])
    monkeypatch.setattr(cr.llm_gen, "sweep",
                        lambda *a, **k: [{"kind": "summary", "ref": "30d",
                                          "error": "TypeError: boom"}])
    res = cr.run_user(con, tg, db_path=path)
    assert res["summary"] is False
    assert res["sweep_errors"][0]["kind"] == "summary"
    assert cr._errors([res]) and "sweep summary/30d" in cr._errors([res])[0]
    con.close()


def test_run_user_summary_true_when_sweep_clean(tmp_path, monkeypatch):
    con, path, tg = _empty_db(tmp_path, tg=1)
    monkeypatch.setattr(cr.botdb, "claude_reviews_pending", lambda *a, **k: [])
    monkeypatch.setattr(cr.llm_gen, "sweep", lambda *a, **k: [])
    res = cr.run_user(con, tg, db_path=path)
    assert res["summary"] is True
    assert "sweep_errors" not in res
    con.close()


def test_sweep_logs_repr_and_traceback(tmp_path, monkeypatch, capsys):
    con, path, tg = _empty_db(tmp_path)
    def _boom(*a, **k):
        raise TypeError("fromisoformat: argument must be str")
    monkeypatch.setattr(llm_gen, "generate_one", _boom)
    errs = llm_gen.sweep(con, path, tg, "ru", kinds={"summary"})
    assert len(errs) == 1 and "TypeError" in errs[0]["error"]
    captured = capsys.readouterr()
    assert "TypeError('fromisoformat: argument must be str')" in captured.out
    assert "Traceback" in captured.err
    con.close()
