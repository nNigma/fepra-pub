"""Маппер push-пейлоада из Health Connect (Android-компаньон) в канон.

Чистый, без IO. HR-серия переносится в extra["_hr_series"] — приёмник кладёт её
в sidecar и заменяет на extra["hr_series_ref"]. Ключи extra зеркалят именование
Garmin, чтобы плитки дашборда работали без правок фронта.
"""
from __future__ import annotations

from datetime import date, datetime

from ..models import Activity, DailyMetrics, EnduranceDetails, Sport

_SPORT = {"run": Sport.RUN, "bike": Sport.BIKE, "swim": Sport.SWIM}
_ENDURANCE = {Sport.RUN, Sport.BIKE, Sport.SWIM}
_EXTRA_KEYS = ("sleep_deep_h", "sleep_rem_h", "spo2_avg", "spo2_lowest", "vo2max", "steps")


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _items(payload: dict, key: str) -> list:
    v = payload.get(key)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def parse(payload: dict) -> tuple[list[DailyMetrics], list[Activity]]:
    days: list[DailyMetrics] = []
    for d in _items(payload, "days"):
        try:
            day = date.fromisoformat(d["day"])
        except (KeyError, ValueError, TypeError):
            continue
        extra = {}
        for k in _EXTRA_KEYS:
            v = _num(d.get(k))
            if v is not None:
                extra[k] = v
        resp = _num(d.get("respiration"))
        if resp is not None:
            extra["respiration_rest"] = resp
        days.append(DailyMetrics(
            day=day, sleep_h=_num(d.get("sleep_h")), resting_hr=_num(d.get("resting_hr")),
            hrv=_num(d.get("hrv")), weight_kg=_num(d.get("weight_kg")), extra=extra))

    acts: list[Activity] = []
    for a in _items(payload, "activities"):
        try:
            start = datetime.fromisoformat(a["start"])
        except (KeyError, ValueError, TypeError):
            continue
        if start.tzinfo is None:
            continue
        sport = _SPORT.get(str(a.get("sport") or "other").lower(), Sport.OTHER)
        endurance = None
        if sport in _ENDURANCE:
            endurance = EnduranceDetails(
                distance_km=_num(a.get("distance_km")),
                avg_pace_s_per_km=_num(a.get("avg_pace_s_per_km")),
                elevation_gain_m=_num(a.get("elevation_gain_m")))
        extra = {}
        series = a.get("hr_series")
        if isinstance(series, list) and series:
            extra["_hr_series"] = series
        acts.append(Activity(
            source="samsung", sport=sport, start=start,
            duration_min=_num(a.get("duration_min")), avg_hr=_num(a.get("avg_hr")),
            max_hr=_num(a.get("max_hr")), calories=_num(a.get("calories")),
            endurance=endurance, activity_id=a.get("activity_id"), extra=extra))
    return days, acts
