"""tjbot.garmin_alerts: статус аккаунта и алерты по падениям кронового синка."""
from __future__ import annotations

from tjbot import db as botdb
from tjbot import garmin_alerts as ga


def _db(tmp_path, tg_id=1):
    path = tmp_path / "t.db"
    con = botdb.connect(path)
    botdb.init_schema(con)
    botdb.garmin_account_set(con, tg_id, "a@b.c")
    con.close()
    return path


def _status(path, tg_id=1):
    con = botdb.connect(path)
    try:
        return botdb.garmin_account_get(con, tg_id)["status"]
    finally:
        con.close()


def _fail(tg_id=1, error="GarminConnectAuthenticationError"):
    return [{"tg_id": tg_id, "ok": False, "error": error}]


def _ok(tg_id=1):
    return [{"tg_id": tg_id, "ok": True, "days": 3, "activities": 1, "last": "2026-08-28"}]


def test_auth_error_marks_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "notify", lambda failed, recovered: False)
    path = _db(tmp_path)
    res = ga.apply(path, _fail())
    assert res["expired"] == [1]
    assert _status(path) == "expired"


def test_network_error_keeps_status(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "notify", lambda failed, recovered: False)
    path = _db(tmp_path)
    res = ga.apply(path, _fail(error="ConnectionError"))
    assert res["expired"] == []
    assert _status(path) == "ok"


def test_alert_only_on_second_failure(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(ga, "notify", lambda failed, recovered: sent.append((failed, recovered)))
    path = _db(tmp_path)
    assert ga.apply(path, _fail())["alerted"] == []
    assert ga.apply(path, _fail())["alerted"] == [1]
    assert sent[1][0] == [("1", 2, "GarminConnectAuthenticationError")]


def test_alert_repeats_weekly_not_every_run(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "notify", lambda failed, recovered: False)
    path = _db(tmp_path)
    alerted = [bool(ga.apply(path, _fail())["alerted"]) for _ in range(ga.ALERT_EVERY + 3)]
    # первое — на второй неудаче, следующее — через ALERT_EVERY прогонов
    assert [i for i, a in enumerate(alerted) if a] == [ga.ALERT_AT - 1,
                                                       ga.ALERT_AT - 1 + ga.ALERT_EVERY]


def test_success_resets_status_and_streak(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "notify", lambda failed, recovered: False)
    path = _db(tmp_path)
    ga.apply(path, _fail())
    ga.apply(path, _fail())
    assert _status(path) == "expired"
    res = ga.apply(path, _ok())
    assert res["recovered"] == [1]
    assert _status(path) == "ok"
    # счётчик обнулён: следующая неудача снова первая, алерта нет
    assert ga.apply(path, _fail())["alerted"] == []


def test_alert_names_the_athlete_and_declines_runs(tmp_path, monkeypatch):
    """Алерт уходит админам, а переподключаться владельцу аккаунта — нужно имя."""
    sent = []
    monkeypatch.setattr(ga, "notify", lambda failed, recovered: sent.append(failed))
    path = _db(tmp_path)
    con = botdb.connect(path)
    botdb.save_user(con, 1, nick="Роман", height_cm=180, weight_kg=80, sex="m", age=30, gym="solo")
    con.close()
    ga.apply(path, _fail())
    ga.apply(path, _fail())
    assert sent[1] == [("Роман (1)", 2, "GarminConnectAuthenticationError")]
    assert "2 прогона подряд" in ga._text(sent[1], [])


def test_runs_word_declines(tmp_path):
    def word(n):
        return ga._text([("кто", n, "E")], [])
    assert "2 прогона подряд" in word(2)
    assert "5 прогонов подряд" in word(5)
    assert "21 прогон подряд" in word(21)
    assert "14 прогонов подряд" in word(14)


def test_notify_sends_to_admins(monkeypatch):
    sent = []
    monkeypatch.setattr(ga.tg_notify, "bot_token", lambda: "T")
    monkeypatch.setattr(ga.tg_notify, "send", lambda token, chat, text: sent.append((chat, text)))
    monkeypatch.setattr(ga.access, "load_admins", lambda: {7})
    assert ga.notify([(1, 2, "GarminConnectAuthenticationError")], []) is True
    chat, text = sent[0]
    assert chat == 7
    assert "Garmin-синк падает" in text and "Подключить Garmin" in text


def test_notify_silent_without_events(monkeypatch):
    monkeypatch.setattr(ga.tg_notify, "bot_token", lambda: "T")
    assert ga.notify([], []) is False


def test_notify_swallows_send_failure(monkeypatch):
    def boom(token, chat, text):
        raise OSError("телеграм лёг")
    monkeypatch.setattr(ga.tg_notify, "bot_token", lambda: "T")
    monkeypatch.setattr(ga.tg_notify, "send", boom)
    monkeypatch.setattr(ga.access, "load_admins", lambda: {7})
    assert ga.notify([(1, 2, "GarminConnectAuthenticationError")], []) is False


def test_profile_kb_offers_reconnect_when_expired():
    """Протухший аккаунт: кнопка подключения появляется, отключать заранее не надо."""
    from tjbot.handlers.menu import _profile_kb

    def flat(kb):
        return [b.callback_data for row in kb.inline_keyboard for b in row]

    live = flat(_profile_kb("ru", has_acc=True, astro=False))
    assert "gconnect" not in live and "gsync" in live

    expired = flat(_profile_kb("ru", has_acc=True, astro=False, acc_expired=True))
    assert expired.index("gconnect") < expired.index("gsync")
    assert "gdisc" in expired
