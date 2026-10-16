"""tj.services.push / notices / push_cli / garmin_alerts для пользователя / claude_review."""
from __future__ import annotations

import sys

import pytest

from tj.services import notices, push, push_cli
from tjbot import db as botdb
from tjbot import garmin_alerts as ga


class _Resp:
    def __init__(self, code):
        self.status_code = code


class _WPErr(Exception):
    def __init__(self, code):
        super().__init__("push error")
        self.response = _Resp(code)


@pytest.fixture
def con(tmp_path, monkeypatch):
    for k in ("FEPRA_VAPID_PRIVATE", "FEPRA_VAPID_PUBLIC", "FEPRA_VAPID_SUBJECT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("tj.config.load_dotenv", lambda p: {})
    c = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(c)
    yield c
    c.close()


@pytest.fixture
def vapid(monkeypatch):
    monkeypatch.setenv("FEPRA_VAPID_PRIVATE", "priv")
    monkeypatch.setenv("FEPRA_VAPID_PUBLIC", "pub")
    monkeypatch.setenv("FEPRA_VAPID_SUBJECT", "mailto:t@example.com")


def _sub(con, uid=1, ep="https://push.example/1"):
    return push.subscribe(con, uid, ep, "p", "a", ua="UA")


def test_subscribe_idempotent_and_revive(con):
    a = _sub(con)
    assert _sub(con) == a
    assert len(push.subscriptions(con, 1)) == 1
    assert push.unsubscribe(con, 1, "https://push.example/1") is True
    assert push.unsubscribe(con, 1, "https://push.example/1") is False
    assert push.subscriptions(con, 1) == []
    assert _sub(con) == a and len(push.subscriptions(con, 1)) == 1


def test_unsubscribe_foreign_uid_noop(con):
    _sub(con, uid=1)
    assert push.unsubscribe(con, 2, "https://push.example/1") is False
    assert len(push.subscriptions(con, 1)) == 1


def test_subscribe_validation(con):
    with pytest.raises(ValueError):
        push.subscribe(con, 1, "", "p", "a")


def test_send_without_vapid_is_silent(con, monkeypatch):
    _sub(con)
    monkeypatch.setattr(push, "_webpush", lambda *a: pytest.fail("не должно вызываться"))
    r = push.send(con, 1, "t", "b")
    assert r["skipped"] == "no_vapid" and r["sent"] == 0
    assert push.public_key() is None


def test_send_batch_and_410_soft_delete(con, vapid, monkeypatch):
    _sub(con, ep="https://push.example/ok")
    _sub(con, ep="https://push.example/gone")
    _sub(con, ep="https://push.example/fail")
    calls = []

    def fake(info, payload, cfg):
        calls.append((info["endpoint"], payload, cfg["subject"]))
        if info["endpoint"].endswith("gone"):
            raise _WPErr(410)
        if info["endpoint"].endswith("fail"):
            raise OSError("net down")
    monkeypatch.setattr(push, "_webpush", fake)
    r = push.send(con, 1, "Заголовок", "Текст", url="/app/x", tag="tg")
    assert (r["sent"], r["removed"], r["failed"]) == (1, 1, 1)
    assert len(calls) == 3 and '"tag": "tg"' in calls[0][1] and "Заголовок" in calls[0][1]
    left = {s["endpoint"] for s in push.subscriptions(con, 1)}
    assert left == {"https://push.example/ok", "https://push.example/fail"}
    row = con.execute("SELECT deleted_at FROM push_subscriptions WHERE endpoint=?",
                      ("https://push.example/gone",)).fetchone()
    assert row["deleted_at"]        # мягкое удаление, строка на месте


def test_send_404_also_removes(con, vapid, monkeypatch):
    _sub(con)
    monkeypatch.setattr(push, "_webpush", lambda *a: (_ for _ in ()).throw(_WPErr(404)))
    assert push.send(con, 1, "t")["removed"] == 1


def test_notify_user_writes_notice_and_pushes(con, vapid, monkeypatch):
    _sub(con)
    sent = []
    monkeypatch.setattr(push, "_webpush", lambda info, payload, cfg: sent.append(payload))
    r = push.notify_user(con, 1, "k", "Привет")
    assert r["notice_id"] and r["push"]["sent"] == 1 and len(sent) == 1
    assert [n["text"] for n in notices.list_notices(con, 1)] == ["Привет"]
    r2 = push.notify_user(con, 1, "k", "Привет")           # дубль непрочитанного — тихо
    assert r2["notice_id"] is None and len(sent) == 1
    push.notify_user(con, 1, "k", "Привет", dedupe=False)
    assert len(sent) == 2


def test_notify_user_without_subscription_or_vapid(con):
    r = push.notify_user(con, 3, "k", "x")
    assert r["notice_id"] and r["push"]["skipped"] == "no_vapid"


def test_notify_user_push_crash_does_not_lose_notice(con, vapid, monkeypatch):
    _sub(con)
    monkeypatch.setattr(push, "send", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    r = push.notify_user(con, 1, "k", "x")
    assert r["notice_id"] and r["push"] is None


def test_tg_fallback_flag(con, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    got = []
    monkeypatch.setattr("tjbot.tg_notify.bot_token", lambda: "T")
    monkeypatch.setattr("tjbot.tg_notify.send", lambda tok, chat, text: got.append((chat, text)))
    push.notify_user(con, 5, "k", "hi", tg=True)
    push.notify_user(con, push.WEB_ID_BASE + 1, "k2", "hi", tg=True)   # веб-юзер — не в TG
    assert [c for c, _ in got] == [5]


def test_notices_read_and_isolation(con):
    nid = notices.add(con, 1, "k", "t")
    assert notices.mark_read(con, 2, nid) is False          # чужое
    assert notices.mark_read(con, 1, nid) is True
    assert notices.mark_read(con, 1, nid) is True           # идемпотентно
    assert notices.mark_read(con, 1, "nope") is False
    assert notices.list_notices(con, 1, unread_only=True) == []
    assert len(notices.list_notices(con, 1)) == 1


def test_gen_keys_roundtrip(capsys):
    assert push_cli.main(["gen-keys"]) == 0
    out = capsys.readouterr().out
    assert "FEPRA_VAPID_PRIVATE=" in out and "FEPRA_VAPID_PUBLIC=" in out
    priv, pub = push_cli.gen_keys()
    from py_vapid import Vapid
    Vapid.from_string(priv)
    assert len(pub) == 87 and priv != push_cli.gen_keys()[0]
    assert push_cli.main([]) == 2


def test_migrations_idempotent(con):
    import importlib
    for m in ("0040_user_notices", "0041_push_subscriptions"):
        mod = importlib.import_module(f"tj.migrations.{m}")
        mod.upgrade(con)
        mod.upgrade(con)


def test_garmin_alerts_notify_user_on_expired(con, tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "notify", lambda f, r: False)
    botdb.garmin_account_set(con, 1, "a@b.c")
    path = tmp_path / "t.db"
    ga.apply(path, [{"tg_id": 1, "ok": False, "error": "GarminConnectAuthenticationError"}])
    ga.apply(path, [{"tg_id": 1, "ok": False, "error": "GarminConnectAuthenticationError"}])
    n = notices.list_notices(con, 1)
    assert [x["kind"] for x in n] == ["garmin_expired"]        # без дублей
    ga.apply(path, [{"tg_id": 1, "ok": True}])
    assert botdb.garmin_account_get(con, 1)["status"] == "ok"


def test_garmin_alerts_network_errors_notice_only_when_due(con, tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "notify", lambda f, r: False)
    botdb.garmin_account_set(con, 1, "a@b.c")
    path = tmp_path / "t.db"
    ga.apply(path, [{"tg_id": 1, "ok": False, "error": "ConnectionError"}])
    assert notices.list_notices(con, 1) == []
    ga.apply(path, [{"tg_id": 1, "ok": False, "error": "ConnectionError"}])
    assert [x["kind"] for x in notices.list_notices(con, 1)] == ["garmin_sync_failed"]


def test_claude_review_ready_notice(con, monkeypatch):
    from tjbot import claude_review as cr
    cr._notify_ready(con, 1, {"days": [{"day": "d", "skip": "x"}]})
    assert notices.list_notices(con, 1) == []
    cr._notify_ready(con, 1, {"days": [{"day": "d", "ok": True}, {"day": "e", "ok": True}]})
    n = notices.list_notices(con, 1)
    assert n[0]["kind"] == "review_ready" and "2" in n[0]["text"]
