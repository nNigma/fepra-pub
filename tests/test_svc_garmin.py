"""tj.services.garmin: реестр сессий входа, MFA, TTL, статус, синк, отключение."""
from __future__ import annotations

import time

import pytest

from tj.services import garmin as g
from tj.services import notices
from tjbot import db as botdb

PW = "s3cret-Passw0rd!"


class FakeAdapter:
    def __init__(self, email, password, tokenstore, prompt_mfa, mode):
        self.mode, self.prompt_mfa, self.password = mode, prompt_mfa, password

    def _login(self):
        if self.mode == "mfa":
            code = self.prompt_mfa()
            if code != "123456":
                raise PermissionError(f"bad code, password was {self.password}")
        elif self.mode == "fail":
            raise ValueError(f"login failed for password {self.password}")
        return object()


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(path))
    con = botdb.connect(path)
    botdb.init_schema(con)
    mode = {"m": "ok"}
    monkeypatch.setattr(g, "adapter_factory",
                        lambda e, p, t, pm: FakeAdapter(e, p, t, pm, mode["m"]))
    with g._lock:
        g._sessions.clear()
    yield con, mode
    with g._lock:
        for u in list(g._sessions):
            g._drop_locked(u)
    con.close()


def test_login_ok_saves_account_without_password(env):
    con, _ = env
    r = g.start_login(con, 7, "a@b.c", PW)
    assert r["state"] == "ok"
    acc = botdb.garmin_account_get(con, 7)
    assert acc["email"] == "a@b.c" and acc["status"] == "ok"
    dump = repr(con.execute("SELECT * FROM garmin_accounts").fetchall()) + repr(
        [tuple(x) for x in con.execute("SELECT * FROM meta").fetchall()])
    assert PW not in dump
    assert g.pending_count() == 0


def test_login_mfa_flow(env):
    con, mode = env
    mode["m"] = "mfa"
    r = g.start_login(con, 7, "a@b.c", PW, wait=5)
    assert r["state"] == "need_mfa"
    assert g.status(con, 7)["mfa_pending"] is True
    r = g.submit_mfa(con, 7, "123456", wait=5)
    assert r["state"] == "ok"
    st = g.status(con, 7)
    assert st["connected"] and st["mfa_pending"] is False and st["email"] == "a@b.c"


def test_wrong_mfa_code_error_without_leak(env, capsys):
    con, mode = env
    mode["m"] = "mfa"
    g.start_login(con, 7, "a@b.c", PW, wait=5)
    r = g.submit_mfa(con, 7, "000000", wait=5)
    assert r["state"] == "error"
    assert PW not in repr(r)
    out = capsys.readouterr()
    assert PW not in out.out + out.err
    assert botdb.garmin_account_get(con, 7) is None


def test_error_message_has_no_secrets_repr_and_log(env, capsys):
    con, mode = env
    mode["m"] = "fail"
    r = g.start_login(con, 7, "a@b.c", PW, wait=5)
    assert r["state"] == "error" and r["message"]
    captured = capsys.readouterr()
    assert PW not in r["message"] + captured.out + captured.err
    assert PW not in repr(g._sessions) and PW not in repr(g._Entry(None, "a@b.c", 0))


def test_empty_credentials(env):
    con, _ = env
    assert g.start_login(con, 7, "", PW)["state"] == "error"
    assert g.start_login(con, 7, "a@b.c", "")["state"] == "error"


def test_mfa_without_session(env):
    con, _ = env
    r = g.submit_mfa(con, 7, "123456")
    assert r["state"] == "error"


def test_ttl_expires_session(env, monkeypatch):
    con, mode = env
    mode["m"] = "mfa"
    now = [1000.0]
    monkeypatch.setattr(g, "_clock", lambda: now[0])
    assert g.start_login(con, 7, "a@b.c", PW, wait=5)["state"] == "need_mfa"
    now[0] += g.SESSION_TTL - 1
    assert g.pending_count() == 1
    now[0] += 2
    assert g.pending_count() == 0
    assert g.submit_mfa(con, 7, "123456")["state"] == "error"


def test_relogin_supersedes_previous(env):
    con, mode = env
    mode["m"] = "mfa"
    g.start_login(con, 7, "a@b.c", PW, wait=5)
    first = g._sessions[7]
    mode["m"] = "ok"
    assert g.start_login(con, 7, "a@b.c", PW)["state"] == "ok"
    assert g.pending_count() == 0
    # старый поток разбужен и завершился
    assert first.session._done.wait(2)


def test_sessions_isolated_per_uid(env):
    con, mode = env
    mode["m"] = "mfa"
    g.start_login(con, 1, "a@b.c", PW, wait=5)
    g.start_login(con, 2, "x@y.z", PW, wait=5)
    assert g.pending_count() == 2
    assert g.submit_mfa(con, 1, "123456", wait=5)["state"] == "ok"
    assert g.pending_count() == 1


def test_status_none_and_disconnect(env, tmp_path):
    con, _ = env
    st = g.status(con, 9)
    assert st["connected"] is False and st["status"] == "none" and st["fail_count"] == 0
    g.start_login(con, 9, "a@b.c", PW)
    ts = botdb.garmin_tokenstore(9)
    ts.mkdir(parents=True, exist_ok=True)
    (ts / "tok.json").write_text("{}")
    g.disconnect(con, 9)
    assert not ts.exists()
    assert g.status(con, 9)["status"] == "none"


def test_sync_success_sets_last_sync(env, monkeypatch):
    con, _ = env
    botdb.garmin_account_set(con, 5, "a@b.c", "expired")
    monkeypatch.setattr(g.garmin_sync, "sync_recent",
                        lambda db, uid, ts, upto=None: {"days": 1})
    assert g.sync_recent(5) == {"days": 1}
    st = g.status(con, 5)
    assert st["status"] == "ok" and st["last_sync"] and st["fail_count"] == 0


def test_sync_history_clamps_days(env, monkeypatch):
    seen = {}
    monkeypatch.setattr(g.garmin_sync, "sync_history",
                        lambda db, uid, ts, days, upto=None: seen.setdefault("d", days) and {})
    g.sync_history(5, 100000)
    assert seen["d"] == 365


def test_sync_auth_failure_marks_expired_and_notifies(env, monkeypatch):
    con, _ = env
    botdb.garmin_account_set(con, 5, "a@b.c")

    class GarminConnectAuthenticationError(Exception):
        pass

    def boom(*a, **k):
        raise GarminConnectAuthenticationError("x")
    monkeypatch.setattr(g.garmin_sync, "sync_recent", boom)
    with pytest.raises(GarminConnectAuthenticationError):
        g.sync_recent(5)
    st = g.status(con, 5)
    assert st["status"] == "expired" and st["fail_count"] == 1
    n = notices.list_notices(con, 5, unread_only=True)
    assert [x["kind"] for x in n] == ["garmin_expired"]
    # повторное подключение снимает баннер
    g.start_login(con, 5, "a@b.c", PW)
    assert notices.list_notices(con, 5, unread_only=True) == []
    assert g.status(con, 5)["status"] == "ok"
