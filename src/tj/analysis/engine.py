"""
Аналитический движок (SPEC §7): поверх пересобираемого кэша build.
Нагрузка (TRIMP -> дневной load -> ACWR, monotony/strain) + базлайны восстановления.
"""
from __future__ import annotations

from pathlib import Path

from ..store.build import _connect
from .load import acwr, monotony, strain, trimp


def _read(db_path, backend, tg_id):
    con, _ = _connect(Path(db_path), backend)
    try:
        daily = con.execute(
            'select "day","resting_hr","hrv","readiness","sleep_h" from daily '
            'where "tg_id"=? order by "day"', (tg_id,)).fetchall()
        acts = con.execute(
            'select "day","duration_min","avg_hr" from activities where "tg_id"=?', (tg_id,)).fetchall()
    finally:
        con.close()
    return daily, acts


def _compute_loads(daily, acts, hr_max, sex):
    """Дневной TRIMP-load: RHR берём из дня (фолбэк — медиана), суммируем сессии."""
    days = [r[0] for r in daily]
    rhr_sorted = sorted(r[1] for r in daily if r[1] is not None)
    rhr_med = rhr_sorted[len(rhr_sorted) // 2] if rhr_sorted else 50
    rhr_by_day = {r[0]: (r[1] if r[1] is not None else rhr_med) for r in daily}
    load_by_day = {d: 0.0 for d in days}
    n_hr = n_nohr = 0
    for day, dur, ahr in acts:
        if ahr is None or dur is None:
            n_nohr += 1
            continue
        n_hr += 1
        load_by_day[day] = load_by_day.get(day, 0.0) + \
            trimp(dur, ahr, rhr_by_day.get(day, rhr_med), hr_max, sex)
    loads = [round(load_by_day[d], 1) for d in days]
    return days, loads, n_hr, n_nohr


def daily_loads(db_path, backend, hr_max, sex="m", *, tg_id):
    """(days, loads) — дневной TRIMP-ряд по всему диапазону (для трендов в report)."""
    daily, acts = _read(db_path, backend, tg_id)
    days, loads, _, _ = _compute_loads(daily, acts, hr_max, sex)
    return days, loads


def analyze(db_path, backend, hr_max, sex="m", *, tg_id) -> dict:
    daily, acts = _read(db_path, backend, tg_id)
    days, loads, n_hr, n_nohr = _compute_loads(daily, acts, hr_max, sex)
    return {
        "range": (days[0], days[-1]) if days else (None, None),
        "n_days": len(days),
        "n_act_hr": n_hr,
        "n_act_nohr": n_nohr,
        "acwr": acwr(loads),
        "acute7": round(sum(loads[-7:]) / 7, 1) if len(loads) >= 7 else None,
        "chronic28": round(sum(loads[-28:]) / 28, 1) if len(loads) >= 28 else None,
        "monotony": monotony(loads[-7:]),
        "strain": strain(loads[-7:]),
        "hrv": _baseline([r[2] for r in daily]),
        "rhr": _baseline([r[1] for r in daily]),
        "readiness": _baseline([r[3] for r in daily]),
        "sleep": _baseline([r[4] for r in daily]),
    }


def _baseline(vals, window: int = 28):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    latest = vals[-1]
    base = sum(vals[-window:]) / min(len(vals), window)
    return {"latest": round(latest, 1), "base": round(base, 1), "delta": round(latest - base, 1)}


# --- форматирование текстового отчёта (tj analyze) ---------------------------

def _acwr_zone(v):
    if v is None:
        return "недостаточно истории"
    if v < 0.8:
        return "ниже нормы — детренировка"
    if v <= 1.3:
        return "оптимально (0.8–1.3)"
    if v <= 1.5:
        return "осторожно — нагрузка растёт"
    return "ВЫСОКИЙ риск — резкий скачок"


def _bio_line(label, b, lower_bad, thr):
    if not b:
        return f"  {label}: нет данных"
    d = b["delta"]
    flag = ""
    if lower_bad and d <= -thr:
        flag = "  ⚠ ниже базы"
    elif not lower_bad and d >= thr:
        flag = "  ⚠ выше базы"
    sign = "+" if d >= 0 else ""
    return f"  {label}: {b['latest']} (база {b['base']}, {sign}{d}){flag}"


def format_report(rep: dict, hr_max: int) -> str:
    r0, r1 = rep["range"]
    mono = rep["monotony"]
    o = [
        f"Период: {r0} … {r1}  ({rep['n_days']} дн, HRmax={hr_max})",
        f"Тренировок в нагрузке: {rep['n_act_hr']}" +
        (f"  (без пульса, пропущено: {rep['n_act_nohr']})" if rep["n_act_nohr"] else ""),
        "",
        "── Нагрузка (TRIMP) ──",
        f"  ACWR 7:28 = {rep['acwr']}  → {_acwr_zone(rep['acwr'])}",
        f"  ср. дневная: остр.(7д) {rep['acute7']} / хрон.(28д) {rep['chronic28']}",
        f"  Monotony(7д) = {mono}" + ("  ⚠ однообразно (>2)" if mono and mono > 2 else ""),
        f"  Strain(7д)   = {rep['strain']}",
        "",
        "── Восстановление (последнее vs база 28д) ──",
        _bio_line("HRV", rep["hrv"], lower_bad=True, thr=5),
        _bio_line("Пульс покоя", rep["rhr"], lower_bad=False, thr=3),
        _bio_line("Readiness", rep["readiness"], lower_bad=True, thr=10),
        _bio_line("Сон, ч", rep["sleep"], lower_bad=True, thr=1),
    ]
    return "\n".join(o)
