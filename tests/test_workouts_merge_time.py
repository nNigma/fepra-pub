from __future__ import annotations

import json

from tj.analysis.workouts import _merged_rows


def _act(day, sport, *, start=None, dur=None, ahr=None, wod_name=None, source=None):
    extra = json.dumps({"start_ts": start}) if start else None
    return (day, sport, dur, ahr, None, None, wod_name, None, None, None, None, None, extra, source)


D = "2026-09-01"


def test_timed_rows_merge_only_when_overlapping():
    acts = [_act(D, "crossfit", start="2026-09-01T09:00:00+00:00", dur=60, ahr=131, source="garmin"),
            _act(D, "crossfit", start="2026-09-01T18:30:00+00:00", dur=60, ahr=152, source="garmin"),
            _act(D, "crossfit", start="2026-09-01T18:40:00+00:00", dur=45, wod_name="Grace", source="manual")]
    rows = _merged_rows(acts)
    assert len(rows) == 2
    merged = next(r for r in rows if r["wod_name"] == "Grace")
    assert merged["avg_hr"] == 152 and merged["start_ts"]


def test_margin_allows_small_gap_but_not_hours():
    near = [_act(D, "crossfit", start="2026-09-01T10:00:00+00:00", dur=60, ahr=140, source="garmin"),
            _act(D, "crossfit", start="2026-09-01T11:10:00+00:00", dur=30, wod_name="X", source="manual")]
    assert len(_merged_rows(near)) == 1          # 10 минут после конца — в пределах запаса 15 мин
    far = [_act(D, "crossfit", start="2026-09-01T10:00:00+00:00", dur=60, ahr=140, source="garmin"),
           _act(D, "crossfit", start="2026-09-01T13:00:00+00:00", dur=30, wod_name="X", source="manual")]
    assert len(_merged_rows(far)) == 2


def test_untimed_side_falls_back_to_day_rule_and_prefers_overlap():
    acts = [_act(D, "crossfit", start="2026-09-01T09:00:00+00:00", dur=60, ahr=131, source="garmin"),
            _act(D, "crossfit", start="2026-09-01T18:00:00+00:00", dur=60, ahr=152, source="garmin"),
            _act(D, "crossfit", wod_name="старая запись", source="manual")]      # без времени
    rows = _merged_rows(acts)
    assert len(rows) == 2                                                   # слилась с первой по дню
    assert next(r for r in rows if r["wod_name"] == "старая запись")["avg_hr"] == 131
    # а запись со временем выбирает свою, даже если она не первая
    acts2 = [acts[0], acts[1],
             _act(D, "crossfit", start="2026-09-01T18:05:00+00:00", wod_name="вечер", source="manual")]
    assert next(r for r in _merged_rows(acts2) if r["wod_name"] == "вечер")["avg_hr"] == 152


def test_start_ts_is_not_leaked_into_extra_and_naive_time_is_utc():
    acts = [_act(D, "run", start="2026-09-01T07:00:00", dur=30, source="garmin")]
    r = _merged_rows(acts)[0]
    assert "start_ts" not in r["extra"] and r["start_ts"] == "2026-09-01T07:00:00"
