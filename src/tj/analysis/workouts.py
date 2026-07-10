"""Данные экрана "Тренировки" (Mini App): список последних + отчёт по дню.

Отчёт = сессии дня + TRIMP + кондиция на входе (вердикт того дня по as-of базам)
+ like-for-like история по той же программе (wod_name). Переиспользует report/verdict.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import muscles
from .engine import daily_loads
from .load import acwr
from .narrative import to_json, workout_blocks
from .report import _asof_base, _read_full
from .verdict import verdict


def _row(a, lang="ru") -> dict:
    vals = tuple(a)
    (day, sport, dur, ahr, mhr, cal, wod_name, wod_fmt,
     scaling, load_kg, score, rpe, raw_extra, source) = vals[:14]
    dist, pace, power, elev = (list(vals[14:18]) + [None] * 4)[:4]
    extra = json.loads(raw_extra) if raw_extra else {}
    return {"day": day, "sport": sport, "duration_min": dur, "avg_hr": ahr,
            "max_hr": mhr, "calories": cal, "wod_name": wod_name, "wod_format": wod_fmt,
            "scaling": scaling, "load_kg": load_kg, "score": score, "rpe": rpe,
            "source": source, "extra": extra,
            "distance_km": dist, "avg_pace_s_per_km": pace,
            "avg_power_w": power, "elevation_gain_m": elev,
            "zones": extra.get("time_in_zones"),
            "narrative": to_json(workout_blocks(extra, max_hr=mhr, lang=lang))}


_KEEP = ("wod_name", "wod_format", "scaling", "load_kg", "score", "rpe",
         "duration_min", "avg_hr", "max_hr", "calories",
         "distance_km", "avg_pace_s_per_km", "avg_power_w", "elevation_gain_m")


def _merge(a: dict, b: dict, lang="ru") -> dict:
    """Слить две сессии одного дня/спорта (ручная WOD + garmin биометрия):
    непустые поля дополняют друг друга, extra объединяются."""
    out = dict(a)
    for k in _KEEP:
        if not out.get(k) and b.get(k):
            out[k] = b[k]
    out["extra"] = {**(b.get("extra") or {}), **(a.get("extra") or {})}
    out["zones"] = out["extra"].get("time_in_zones")
    out["narrative"] = to_json(workout_blocks(out["extra"], max_hr=out.get("max_hr"), lang=lang))
    return out


def _merged_rows(acts, lang="ru") -> list[dict]:
    """Ручную WOD-запись сливаем с garmin-биометрией той же сессии (день+спорт,
    но РАЗНЫЙ source). Две сессии одного источника (два заплыва garmin, два
    ручных WOD) - разные тренировки, не сливаем."""
    slots: list[dict] = []
    for a in acts:
        r = _row(a, lang=lang)
        src = r.get("source")
        target = None
        for s in slots:
            if (s["day"], s["sport"]) == (r["day"], r["sport"]) \
                    and src and src not in s["_sources"]:
                target = s
                break
        if target is not None:
            sources = target["_sources"] | {src}
            merged = _merge(target, r, lang=lang)
            merged["_sources"] = sources
            slots[slots.index(target)] = merged
        else:
            r["_sources"] = {src} if src else set()
            slots.append(r)
    for s in slots:
        s.pop("_sources", None)
    return slots


def recent_workouts(db_path, backend, limit: int = 30, *, tg_id, lang="ru") -> list[dict]:
    """Последние тренировки (новые сверху). + readiness того дня для индикатора."""
    daily, acts = _read_full(db_path, backend, tg_id)
    rdy = {r[0]: r[3] for r in daily}
    rows = [{**r, "readiness": rdy.get(r["day"])} for r in _merged_rows(acts, lang=lang)]
    rows.sort(key=lambda r: r["day"], reverse=True)
    return rows[:limit]


def workout_report(db_path, backend, hr_max, sex, day: str, *, tg_id, lang="ru") -> dict | None:
    """Отчёт по тренировкам конкретного дня."""
    daily, acts = _read_full(db_path, backend, tg_id)
    days = [r[0] for r in daily]
    _, loads = daily_loads(db_path, backend, hr_max, sex, tg_id=tg_id)
    load_by_day = {days[i]: loads[i] for i in range(len(days))}

    merged = _merged_rows(acts, lang=lang)
    sessions = [r for r in merged if r["day"] == day]
    if not sessions:
        return None

    root = Path(db_path).resolve().parent
    for s in sessions:
        ref = (s.get("extra") or {}).get("hr_series_ref")
        if not ref:
            continue
        p = Path(ref)
        if not p.is_absolute():
            p = root / ref if (root / ref).exists() else p
        if p.exists():
            try:
                s["hr_series"] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                s["hr_series"] = None

    condition = None
    if day in days:
        i = days.index(day)
        row = daily[i]   # 0 day,1 rhr,2 hrv,3 readiness,4 sleep,5 bb,6 stress

        def _delta(col):
            base = _asof_base(daily, i, col)
            return None if row[col] is None or base is None else round(row[col] - base, 1)

        acwr_d = acwr(loads[: i + 1])
        v = verdict(row[3], _delta(4), acwr_d, _delta(2), _delta(1), lang=lang)
        condition = {"readiness": row[3], "hrv": row[2], "resting_hr": row[1],
                     "sleep_h": row[4], "acwr": acwr_d, "verdict": v,
                     "hrv_delta": _delta(2), "sleep_delta": _delta(4)}

    # like-for-like: прошлые сессии той же программы (по wod_name), старые -> новые
    history: dict[str, list[dict]] = {}
    for s in sessions:
        name = s["wod_name"]
        if not name or name in history:
            continue
        prior = sorted((r for r in merged if r["wod_name"] == name and r["day"] < day),
                       key=lambda r: r["day"])
        history[name] = prior

    return {"day": day, "trimp": round(load_by_day.get(day, 0)), "hr_max": hr_max,
            "sessions": sessions, "condition": condition, "history": history,
            "muscles": muscles.workout_muscles(sessions)}
