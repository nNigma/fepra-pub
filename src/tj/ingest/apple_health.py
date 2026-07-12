"""Маппер push-пейлоада Health Auto Export (Apple Watch) в канон.

Чистый, без IO. Формат HAE: {"data": {"metrics": [...], "workouts": [...]}}.
Парсим толерантно: числа приходят числом или {"qty": x}; даты - ISO или
"YYYY-MM-DD HH:MM:SS +0300"; неизвестные метрики пропускаем. duration
воркаута считаем из end-start, иначе поле duration трактуем как секунды.
HR-серия переносится в extra["_hr_series"] точками [сек_от_старта, пульс]
(единый формат с Garmin/Samsung) - приёмник кладёт её в sidecar.
Ключи extra зеркалят Garmin/Samsung, чтобы плитки дашборда работали без фронта.
"""
from __future__ import annotations

from datetime import date, datetime

from ..models import Activity, DailyMetrics, EnduranceDetails, Sport

_SPORT_HINTS = (("run", Sport.RUN), ("cycl", Sport.BIKE), ("bike", Sport.BIKE),
                ("swim", Sport.SWIM))
_ENDURANCE = {Sport.RUN, Sport.BIKE, Sport.SWIM}

_METRIC_DAILY = {
    "resting_heart_rate": "resting_hr",
    "heart_rate_variability": "hrv",
    "weight_body_mass": "weight_kg",
}
_METRIC_EXTRA = {
    "vo2_max": "vo2max",
    "respiratory_rate": "respiration_rest",
    "blood_oxygen_saturation": "spo2_avg",
    "step_count": "steps",
    "apple_sleeping_wrist_temperature": "wrist_temp_c",
}


def _qty(v):
    if isinstance(v, dict):
        v = v.get("qty")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _dt(v) -> datetime | None:
    if not isinstance(v, str):
        return None
    s = v.strip()
    for cand in (s, s.replace(" +", "+").replace(" -", "-")):
        try:
            return datetime.fromisoformat(cand)
        except ValueError:
            continue
    return None


def _day(v) -> date | None:
    if not isinstance(v, str) or len(v) < 10:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def parse(payload: dict) -> tuple[list[DailyMetrics], list[Activity]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    metrics = data.get("metrics") if isinstance(data.get("metrics"), list) else []
    workouts = data.get("workouts") if isinstance(data.get("workouts"), list) else []

    buckets: dict[date, dict] = {}

    def bucket(d: date) -> dict:
        return buckets.setdefault(d, {"extra": {}})

    for m in metrics:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name") or "").lower()
        for p in (m.get("data") if isinstance(m.get("data"), list) else []):
            if not isinstance(p, dict):
                continue
            d = _day(p.get("date"))
            if d is None:
                continue
            if name == "sleep_analysis":
                b = bucket(d)
                asleep = _qty(p.get("asleep"))
                if asleep is None:
                    asleep = _qty(p.get("qty"))
                if asleep is not None:
                    b["sleep_h"] = round((b.get("sleep_h") or 0) + float(asleep), 2)
                for src, dst in (("deep", "sleep_deep_h"), ("rem", "sleep_rem_h")):
                    v = _qty(p.get(src))
                    if v is not None:
                        b["extra"][dst] = round((b["extra"].get(dst) or 0) + float(v), 2)
            elif name in _METRIC_DAILY:
                v = _qty(p.get("qty"))
                if v is not None:
                    key = _METRIC_DAILY[name]
                    bucket(d)[key] = round(float(v), 2) if key == "weight_kg" else round(v)
            elif name in _METRIC_EXTRA:
                v = _qty(p.get("qty"))
                if v is not None:
                    if name == "blood_oxygen_saturation" and v <= 1:
                        v = v * 100
                    bucket(d)["extra"][_METRIC_EXTRA[name]] = round(float(v), 2)

    days = [DailyMetrics(day=d, sleep_h=vals.get("sleep_h"),
                         resting_hr=vals.get("resting_hr"), hrv=vals.get("hrv"),
                         weight_kg=vals.get("weight_kg"), extra=vals["extra"])
            for d, vals in sorted(buckets.items())]

    acts: list[Activity] = []
    for w in workouts:
        if not isinstance(w, dict):
            continue
        start = _dt(w.get("start"))
        if start is None or start.tzinfo is None:
            continue
        low = str(w.get("name") or "").lower()
        sport = next((s for hint, s in _SPORT_HINTS if hint in low), Sport.OTHER)
        end = _dt(w.get("end"))
        duration = None
        if end is not None and end > start:
            duration = round((end - start).total_seconds() / 60.0, 1)
        else:
            secs = _qty(w.get("duration"))
            if secs is not None:
                duration = round(float(secs) / 60.0, 1)
        hr = w.get("heartRate") if isinstance(w.get("heartRate"), dict) else {}
        avg_hr = _qty(hr.get("average"))
        max_hr = _qty(hr.get("maximum"))
        series = []
        for p in (w.get("heartRateData") if isinstance(w.get("heartRateData"), list) else []):
            if isinstance(p, dict):
                v = _qty(p.get("Avg")) if p.get("Avg") is not None else _qty(p.get("qty"))
                t = _dt(p.get("date"))
                if v is not None and t is not None and t.tzinfo is not None:
                    series.append([round((t - start).total_seconds()), v])
        series.sort()
        if series:
            if avg_hr is None:
                avg_hr = round(sum(v for _, v in series) / len(series))
            if max_hr is None:
                max_hr = max(v for _, v in series)
        calories = _qty(w.get("activeEnergyBurned"))
        if calories is None:
            calories = _qty(w.get("energy"))
        distance = _qty(w.get("distance"))
        endurance = None
        if sport in _ENDURANCE and distance is not None:
            pace = round(duration * 60.0 / distance) if duration and distance else None
            endurance = EnduranceDetails(distance_km=round(float(distance), 2),
                                         avg_pace_s_per_km=pace)
        extra = {}
        if series:
            extra["_hr_series"] = series
        wid = w.get("id")
        aid = f"apple-{wid}" if wid else f"apple-{start.isoformat()}-{sport.value}"
        acts.append(Activity(
            source="apple", sport=sport, start=start, duration_min=duration,
            avg_hr=round(avg_hr) if avg_hr is not None else None,
            max_hr=round(max_hr) if max_hr is not None else None,
            calories=round(calories) if calories is not None else None,
            endurance=endurance, activity_id=aid, extra=extra))
    return days, acts
