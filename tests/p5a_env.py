"""Общая оснастка тестов фазы 5А: tmp-БД (FEPRA_DB_PATH), пользователи с ролями, клиент с сессией.
Использование: `from p5a_env import p5a  # noqa: F401` в тестовом модуле."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tj.services import auth
from tjapp.api import app
from tjbot import access, db as botdb


class Env:
    def __init__(self, con):
        self.con = con

    def user(self, uid: int, nick: str | None = None, *, admin=False, pro=False, coach: str | None = None,
             gym: str | None = None, allowed: bool = True, profile: bool = True) -> int:
        if profile:
            botdb.save_user(self.con, uid, nick=nick or f"u{uid}", height_cm=180, weight_kg=80.0,
                            sex="m", age=30, gym=gym or "Universe")
        if allowed:
            access.add_user(uid)
        if admin:
            access.add_admin(uid)
        if pro:
            access.add_pro(uid)
        if coach:
            access.add_coach(uid, coach)
        return uid

    def client(self, uid: int) -> TestClient:
        c = TestClient(app)
        c.cookies.set("fepra_session", auth.create_session(self.con, uid))
        return c


@pytest.fixture
def p5a(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    monkeypatch.setattr("tj.config.load_dotenv", lambda q: {})
    con = botdb.connect(p)
    botdb.init_schema(con)
    yield Env(con)
    app.dependency_overrides.clear()
    con.close()


def wait_job(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    import time
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} не завершилась")
