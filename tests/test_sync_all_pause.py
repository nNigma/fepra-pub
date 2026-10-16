"""garmin_sync.sync_all: паузы между пользователями и backoff при 429."""
from tjbot import garmin_sync as gs


class GarminConnectTooManyRequestsError(Exception):
    pass


def _accounts(*ids):
    return [(i, "e", "ok") for i in ids]


def test_pause_between_users_only(monkeypatch):
    monkeypatch.setattr(gs, "sync_recent", lambda db, uid, ts: {"days": 1})
    monkeypatch.setattr("tjbot.db.garmin_tokenstore", lambda uid: "/x")
    sleeps = []
    out = gs.sync_all("db", _accounts(1, 2, 3), sleep=sleeps.append, rand=lambda a, b: (a + b) / 2)
    assert [r["ok"] for r in out] == [True] * 3
    assert sleeps == [40.0, 40.0]                 # дефолт 20–60, до первого пользователя паузы нет


def test_pause_zero_via_env(monkeypatch):
    monkeypatch.setenv("FEPRA_SYNC_PAUSE_MIN", "0")
    monkeypatch.setenv("FEPRA_SYNC_PAUSE_MAX", "0")
    monkeypatch.setattr(gs, "sync_recent", lambda db, uid, ts: {})
    monkeypatch.setattr("tjbot.db.garmin_tokenstore", lambda uid: "/x")
    sleeps = []
    gs.sync_all("db", _accounts(1, 2), sleep=sleeps.append)
    assert sleeps == []


def test_429_backoff_then_success(monkeypatch):
    monkeypatch.setenv("FEPRA_SYNC_PAUSE_MAX", "0")
    monkeypatch.setenv("FEPRA_SYNC_PAUSE_MIN", "0")
    monkeypatch.setenv("FEPRA_SYNC_429_BACKOFF", "10")
    monkeypatch.setattr("tjbot.db.garmin_tokenstore", lambda uid: "/x")
    n = {"i": 0}

    def fake(db, uid, ts):
        n["i"] += 1
        if n["i"] < 3:
            raise GarminConnectTooManyRequestsError("429")
        return {"days": 2}
    monkeypatch.setattr(gs, "sync_recent", fake)
    sleeps = []
    out = gs.sync_all("db", _accounts(1), sleep=sleeps.append)
    assert out == [{"tg_id": 1, "ok": True, "days": 2}]
    assert sleeps == [10.0, 20.0]


def test_429_gives_up_and_other_errors_dont_retry(monkeypatch):
    monkeypatch.setenv("FEPRA_SYNC_PAUSE_MIN", "0")
    monkeypatch.setenv("FEPRA_SYNC_PAUSE_MAX", "0")
    monkeypatch.setenv("FEPRA_SYNC_429_BACKOFF", "1")
    monkeypatch.setattr("tjbot.db.garmin_tokenstore", lambda uid: "/x")

    def fake(db, uid, ts):
        raise GarminConnectTooManyRequestsError("429") if uid == 1 else ValueError("x")
    monkeypatch.setattr(gs, "sync_recent", fake)
    sleeps = []
    out = gs.sync_all("db", _accounts(1, 2), sleep=sleeps.append)
    assert out[0] == {"tg_id": 1, "ok": False, "error": "GarminConnectTooManyRequestsError"}
    assert out[1]["error"] == "ValueError"
    assert sleeps == [1.0, 2.0]
