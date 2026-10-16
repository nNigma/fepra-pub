import pytest
from fastapi.testclient import TestClient

from tj.services import jobs
from tjapp.api import app
from tjapp.deps import require_user
from tjbot import db as botdb


@pytest.fixture
def con(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    c = botdb.connect(p)
    botdb.init_schema(c)
    yield c
    c.close()


def test_lifecycle_and_owner_check(con):
    jid = jobs.create_job(con, "board", 1, {"a": 1})
    assert jobs.get_job(con, jid, 1)["status"] == "pending"
    assert jobs.get_job(con, jid, 2) is None
    jobs.set_running(con, jid)
    jobs.set_result(con, jid, {"x": [1, 2]})
    j = jobs.get_job(con, jid, 1)
    assert j["status"] == "done" and j["result"] == {"x": [1, 2]}
    jid2 = jobs.create_job(con, "board", 1)
    jobs.set_error(con, jid2, "boom")
    assert jobs.get_job(con, jid2, 1)["error"] == "boom"


def test_run_in_background_ok_and_error(con):
    a = jobs.create_job(con, "k", 1)
    jobs.run_in_background(a, lambda: {"v": 42}).join(5)
    assert jobs.get_job(con, a, 1)["result"] == {"v": 42}
    b = jobs.create_job(con, "k", 1)

    def bad():
        raise RuntimeError("nope")
    jobs.run_in_background(b, bad).join(5)
    j = jobs.get_job(con, b, 1)
    assert j["status"] == "error" and "nope" in j["error"]


def test_fail_stale_marks_running_and_pending(con):
    a = jobs.create_job(con, "k", 1)
    b = jobs.create_job(con, "k", 1)
    c = jobs.create_job(con, "k", 1)
    jobs.set_running(con, b)
    jobs.set_result(con, c, 1)
    assert jobs.fail_stale(con) == 2
    assert jobs.get_job(con, a, 1)["status"] == "error"
    assert jobs.get_job(con, b, 1)["status"] == "error"
    assert jobs.get_job(con, c, 1)["status"] == "done"


def test_endpoint(con):
    jid = jobs.create_job(con, "k", 1)
    jobs.set_result(con, jid, {"ok": True})
    app.dependency_overrides[require_user] = lambda: {"id": 1}
    try:
        c = TestClient(app)
        r = c.get(f"/api/jobs/{jid}")
        assert r.status_code == 200
        assert r.json() == {"id": jid, "status": "done", "result": {"ok": True}, "error": None}
        assert c.get("/api/jobs/nope").status_code == 404
        app.dependency_overrides[require_user] = lambda: {"id": 2}
        assert c.get(f"/api/jobs/{jid}").status_code == 404
    finally:
        app.dependency_overrides.clear()
