from datetime import date, datetime
from tjbot import db as botdb
from tjbot import garmin_sync
from tj.models import Activity, DailyMetrics, Sport

class _FakeAdapter:
    def __init__(self, day): self._day = day
    def fetch_daily(self, d):
        return DailyMetrics(day=d, resting_hr=50) if d == self._day else None
    def fetch_activities(self, a, b):
        return [Activity(source="garmin", sport=Sport.RUN,
                         start=datetime.fromisoformat(self._day.isoformat()+"T12:00:00+00:00"),
                         activity_id=f"g-{self._day.isoformat()}")]
    def _login(self): return None

def test_sync_writes_under_tg_id(tmp_path, monkeypatch):
    p = tmp_path / "t.db"; con = botdb.connect(p); botdb.init_schema(con); con.close()
    monkeypatch.setattr(garmin_sync, "_adapter_for", lambda tg_id, tokenstore: _FakeAdapter(date(2026,7,4)))
    monkeypatch.setattr(garmin_sync, "dump_hr_series", lambda *a, **k: None)
    res = garmin_sync.sync_recent(str(p), tg_id=222, tokenstore="/tmp/ts", upto=date(2026,7,4))
    con = botdb.connect(p)
    assert con.execute('SELECT tg_id FROM daily').fetchone()[0] == 222
    assert con.execute('SELECT tg_id FROM activities').fetchone()[0] == 222

def test_hr_filename_has_tg_id(tmp_path):
    class C:
        def get_activity_details(self, *a, **k):
            return {"metricDescriptors":[{"key":"directHeartRate","metricsIndex":0}],
                    "activityDetailMetrics":[{"metrics":[120]},{"metrics":[130]},{"metrics":[140]}]}
    ref = garmin_sync.dump_hr_series(C(), "abc", tmp_path, tg_id=222)
    assert ref == "data/hr_222_abc.json" and (tmp_path/"data"/"hr_222_abc.json").exists()
