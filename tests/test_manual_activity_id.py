from datetime import date
from zoneinfo import ZoneInfo
from tjbot.handlers.record_workout import _build_activity
from tj.models import Sport

def test_manual_id_has_tg_id():
    ud = {"date": date(2026, 7, 1), "sport": Sport.CROSSFIT, "result": ""}
    act = _build_activity(ud, ZoneInfo("UTC"), tg_id=555)
    assert act.activity_id == "manual-555-2026-07-01-crossfit"
