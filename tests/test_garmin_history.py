from datetime import date, datetime
from tjbot import db as botdb
from tjbot import garmin_sync
from tj.models import Activity, DailyMetrics, Sport


class _RecordingAdapter:
    def __init__(self):
        self.daily_days = []
    def fetch_daily(self, d):
        self.daily_days.append(d)
        return DailyMetrics(day=d, resting_hr=50)
    def fetch_activities(self, a, b):
        return [Activity(source="garmin", sport=Sport.RUN,
                         start=datetime.fromisoformat(a.isoformat() + "T12:00:00+00:00"),
                         activity_id=f"g-{a.isoformat()}")]
    def _login(self):
        return None


def _fresh_db(tmp_path):
    p = tmp_path / "t.db"
    con = botdb.connect(p); botdb.init_schema(con); con.close()
    return str(p)


def test_start_override_pulls_full_range(tmp_path, monkeypatch):
    p = _fresh_db(tmp_path)
    ad = _RecordingAdapter()
    monkeypatch.setattr(garmin_sync, "_adapter_for", lambda tg_id, ts: ad)
    monkeypatch.setattr(garmin_sync, "dump_hr_series", lambda *a, **k: None)
    res = garmin_sync.sync_recent(p, tg_id=1, tokenstore="/tmp/ts",
                                  upto=date(2026, 7, 6), start=date(2026, 7, 1))
    # основной цикл тянет полный диапазон (первые 6 фетчей); дальше heal может
    # перечитать частичные дни (только resting_hr, без сна) — это ожидаемо
    assert ad.daily_days[:6] == [date(2026, 7, d) for d in range(1, 7)]
    assert res["days"] == 6
    assert res["from"] == "2026-07-01"


def test_sync_history_goes_back_60_days(tmp_path, monkeypatch):
    p = _fresh_db(tmp_path)
    ad = _RecordingAdapter()
    monkeypatch.setattr(garmin_sync, "_adapter_for", lambda tg_id, ts: ad)
    monkeypatch.setattr(garmin_sync, "dump_hr_series", lambda *a, **k: None)
    res = garmin_sync.sync_history(p, tg_id=1, tokenstore="/tmp/ts",
                                   days=60, upto=date(2026, 7, 6))
    assert res["from"] == date(2026, 5, 7).isoformat()
    assert res["to"] == "2026-07-06"
    assert ad.daily_days[0] == date(2026, 5, 7)


class _FakeMsg:
    def __init__(self):
        self.markup = None
    async def reply_text(self, text, reply_markup=None):
        self.markup = reply_markup


class _FakeUpdate:
    def __init__(self, uid, msg):
        self.effective_user = type("U", (), {"id": uid})()
        self.effective_message = msg


class _FakeCtx:
    def __init__(self, db_path):
        self.bot_data = {"db_path": db_path}


def _callbacks(markup):
    return {b.callback_data for row in markup.inline_keyboard for b in row}


def test_profile_card_has_history_button(tmp_path):
    import asyncio
    from tjbot.handlers import menu
    p = _fresh_db(tmp_path)
    con = botdb.connect(p)
    botdb.save_user(con, 5, nick="n", height_cm=180, weight_kg=80, sex="M", gym="g", age=30)
    botdb.garmin_account_set(con, 5, "a@b.c")
    con.close()
    msg = _FakeMsg()
    asyncio.run(menu._profile.__wrapped__(_FakeUpdate(5, msg), _FakeCtx(p)))
    assert _callbacks(msg.markup) == {"gsync", "ghist", "gdisc", "pedit:open", "bw:start",
                                       "astro:toggle", "ngoal:open", "ncity:open"}


def test_profile_no_history_button_without_garmin(tmp_path):
    import asyncio
    from tjbot.handlers import menu
    p = _fresh_db(tmp_path)
    con = botdb.connect(p)
    botdb.save_user(con, 6, nick="n", height_cm=180, weight_kg=80, sex="M", gym="g", age=30)
    con.close()
    msg = _FakeMsg()
    asyncio.run(menu._profile.__wrapped__(_FakeUpdate(6, msg), _FakeCtx(p)))
    assert _callbacks(msg.markup) == {"gconnect", "pedit:open", "bw:start", "astro:toggle",
                                       "ngoal:open", "ncity:open", "wconnect:samsung",
                                       "wconnect:whoop", "wconnect:apple"}


def test_history_is_idempotent(tmp_path, monkeypatch):
    p = _fresh_db(tmp_path)
    monkeypatch.setattr(garmin_sync, "_adapter_for", lambda tg_id, ts: _RecordingAdapter())
    monkeypatch.setattr(garmin_sync, "dump_hr_series", lambda *a, **k: None)
    garmin_sync.sync_history(p, tg_id=1, tokenstore="/tmp/ts", days=7, upto=date(2026, 7, 6))
    garmin_sync.sync_history(p, tg_id=1, tokenstore="/tmp/ts", days=7, upto=date(2026, 7, 6))
    con = botdb.connect(p)
    n_daily = con.execute('SELECT COUNT(*) FROM daily WHERE tg_id=1').fetchone()[0]
    n_act = con.execute('SELECT COUNT(*) FROM activities WHERE tg_id=1').fetchone()[0]
    con.close()
    assert n_daily == 8
    assert n_act == 1
