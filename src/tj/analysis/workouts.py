"""Данные экрана "Тренировки" (Mini App): список последних + отчёт по дню.

Отчёт = сессии дня + TRIMP + кондиция на входе (вердикт того дня по as-of базам)
+ like-for-like история по той же программе (wod_name). Переиспользует report/verdict.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..models import BOARD_SPORT_VALUES
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
    start_ts = extra.pop("start_ts", None)   # служебное: время старта для слияния, не «extra» отчёта
    return {"day": day, "start_ts": start_ts, "sport": sport, "duration_min": dur, "avg_hr": ahr,
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


def _slot(sport: str | None) -> str:
    """Ключ слияния. Часы не отличают кроссфит от ТА и Hyrox (strength_training
    у Garmin -> crossfit), поэтому вся доска-семья делит один слот дня."""
    return "board" if sport in BOARD_SPORT_VALUES else (sport or "")


def _merge(a: dict, b: dict, lang="ru") -> dict:
    """Слить две сессии одного дня/семьи (ручная WOD + garmin биометрия):
    непустые поля дополняют друг друга, extra объединяются."""
    out = dict(a)
    for k in _KEEP:
        if not out.get(k) and b.get(k):
            out[k] = b[k]
    if b.get("source") == "manual" and a.get("source") != "manual" and b.get("sport"):
        out["sport"] = b["sport"]       # тип знает атлет, часы пишут обобщённо
    out["extra"] = {**(b.get("extra") or {}), **(a.get("extra") or {})}
    out["zones"] = out["extra"].get("time_in_zones")
    out["narrative"] = to_json(workout_blocks(out["extra"], max_hr=out.get("max_hr"), lang=lang))
    return out


_TIME_MARGIN_S = 15 * 60       # запас на расхождение часов/ручного времени
_DEFAULT_DURATION_MIN = 60     # ручная запись с временем старта, но без длительности


def _interval(r: dict):
    """(start, end) в секундах UTC или None, если время старта неизвестно.
    Время есть у записей часов (с их start) и у ручных записей, где атлет его указал;
    у старых записей (id manual-...) времени нет — они сливаются по дню, как раньше."""
    ts = r.get("start_ts")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    t0 = dt.timestamp()
    dur = r.get("duration_min") or _DEFAULT_DURATION_MIN
    return (t0, t0 + dur * 60)


def _gap(a, b) -> float:
    """Зазор между интервалами в секундах: <0 — пересекаются, 0 — впритык."""
    return max(a[0], b[0]) - min(a[1], b[1])


def _merged_rows(acts, lang="ru") -> list[dict]:
    """Ручную запись сливаем с биометрией часов той же сессии: тот же день, вид спорта
    (семья: кроссфит/ТА/Hyrox — одна), РАЗНЫЙ source. Две сессии одного источника (два заплыва
    garmin, два ручных WOD, две ТА) - разные тренировки, не сливаем.
    Если у обеих сторон известно время старта, сливаем только пересекающиеся по времени
    (с запасом 15 мин): утренняя ТА и вечерний кроссфит с часов не склеятся. Если у одной из
    сторон времени нет (старые ручные записи), работает прежнее правило по дню; при выборе
    из нескольких кандидатов приоритет у пересечения по времени."""
    slots: list[dict] = []
    for a in acts:
        r = _row(a, lang=lang)
        src = r.get("source")
        iv = _interval(r)
        best, best_key = None, None
        for s in slots:
            if (s["day"], _slot(s["sport"])) != (r["day"], _slot(r["sport"])) \
                    or not src or src in s["_sources"]:
                continue
            siv = s.get("_iv")
            if iv and siv:
                g = _gap(iv, siv)
                if g >= _TIME_MARGIN_S:
                    continue               # оба со временем и не пересекаются: другая сессия
                key = (0, g)
            else:
                key = (1, 0)               # время неизвестно: по дню, как раньше
            if best_key is None or key < best_key:
                best, best_key = s, key
        if best is not None:
            merged = _merge(best, r, lang=lang)
            merged["_sources"] = best["_sources"] | {src}
            ivs = [x for x in (best.get("_iv"), iv) if x]
            merged["_iv"] = (min(x[0] for x in ivs), max(x[1] for x in ivs)) if ivs else None
            if not merged.get("start_ts"):
                merged["start_ts"] = r.get("start_ts")
            slots[slots.index(best)] = merged
        else:
            r["_sources"] = {src} if src else set()
            r["_iv"] = iv
            slots.append(r)
    for s in slots:
        s.pop("_sources", None)
        s.pop("_iv", None)
    return slots


def sport_counts(db_path, backend, *, tg_id, since: str) -> list[dict]:
    """Число тренировок по спортам с даты since по слитым сессиям
    (garmin+manual одного дня = одна тренировка)."""
    _, acts = _read_full(db_path, backend, tg_id)
    counts: dict[str, int] = {}
    for r in _merged_rows(acts):
        if r["sport"] and r["day"] and r["day"] >= since:
            counts[r["sport"]] = counts.get(r["sport"], 0) + 1
    return [{"sport": s, "n": n}
            for s, n in sorted(counts.items(), key=lambda kv: -kv[1])]


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
