"""
report (SPEC §6): markdown-сводки обратно в vault.

Папка `Сводка/`:
- `_Обзор.md`        — общий дашборд (всё время): объём, нагрузка, тренды.
- `YYYY-MM-DD.md`    — заметка на каждый день: восстановление vs база НА ТОТ ДЕНЬ,
                       ACWR как-на-тот-день, сессии. frontmatter `trained/load/acwr`
                       -> фильтрация тренировочных дней (свойства / Dataview).

Регенерируется командой -> перезапись. Таблицы + юникод-спарклайны (без плагинов).
"""
from __future__ import annotations

import datetime
from pathlib import Path

from ..models import BOARD_SPORT_VALUES
from ..store.build import _connect
from .engine import analyze, daily_loads
from .load import acwr
from .verdict import verdict

_BARS = "▁▂▃▄▅▆▇█"


def _spark(vals) -> str:
    nums = [float(v or 0) for v in vals]
    if not nums:
        return ""
    mx = max(nums) or 1.0
    return "".join(_BARS[min(7, int(v / mx * 7))] for v in nums)


def _bar(v, mx, width=10) -> str:
    return "█" * max(1, round((v or 0) / (mx or 1) * width)) if v else ""


def _cnum(v) -> str:
    if v is None:
        return "null"
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:.1f}"


def _chart(ctype, labels, series, **opts) -> list[str]:
    """obsidian-charts (phibr0): нативный ```chart-блок. series: [(title, data), ...].
    Данные впекаются из Python -> без Dataview, plaintext-first. Без плагина — просто код."""
    out = ["```chart", f"type: {ctype}",
           "labels: [" + ", ".join(f'"{l}"' for l in labels) + "]", "series:"]
    for title, data in series:
        out.append(f"  - title: {title}")
        out.append("    data: [" + ", ".join(_cnum(v) for v in data) + "]")
    out += [f"{k}: {val}" for k, val in opts.items()]
    out.append("```")
    return out


def _i(v):
    return int(v) if v is not None else "—"


def _v(x):
    return x if x is not None else "null"


def _zone(v):
    if v is None:
        return "—"
    if v < 0.8:
        return "ниже нормы"
    if v <= 1.3:
        return "оптимально"
    if v <= 1.5:
        return "осторожно"
    return "риск"


# --- чтение БД ---------------------------------------------------------------

def _read_full(db_path, backend, tg_id):
    con, _ = _connect(Path(db_path), backend)
    try:
        daily = con.execute(
            'select "day","resting_hr","hrv","readiness","sleep_h","body_battery","stress_avg" '
            'from daily where "tg_id"=? order by "day"', (tg_id,)).fetchall()
        acts = con.execute(
            'select "day","sport","duration_min","avg_hr","max_hr","calories",'
            '"wod_name","wod_format","perf_scaling","perf_load_kg","perf_score","perf_rpe","extra","source",'
            '"distance_km","avg_pace_s_per_km","avg_power_w","elevation_gain_m" '
            'from activities where "tg_id"=? order by "day"', (tg_id,)).fetchall()
    finally:
        con.close()
    return daily, acts


# --- заметка на каждый день --------------------------------------------------

# индекс колонки в строке daily -> (подпись, ниже_плохо, порог флага)
_DAY_METRICS = [
    ("Сон, ч", 4, True, 1),
    ("HRV", 2, True, 5),
    ("Пульс покоя", 1, False, 3),
    ("Readiness", 3, True, 10),
    ("Body battery", 5, None, None),
    ("Стресс", 6, None, None),
]


def _asof_base(daily, i, col, window=28):
    vals = [daily[j][col] for j in range(max(0, i - window + 1), i + 1) if daily[j][col] is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _delta(daily, i, col):
    val = daily[i][col]
    base = _asof_base(daily, i, col)
    return None if val is None or base is None else round(val - base, 1)


def _day_metric_row(daily, i, label, col, lower_bad, thr):
    val = daily[i][col]
    base = _asof_base(daily, i, col)
    if val is None:
        return f"| {label} | — | {base if base is not None else '—'} | |"
    if base is None:
        return f"| {label} | {val} | — | |"
    d = round(val - base, 1)
    sign = "+" if d >= 0 else ""
    flag = ""
    if thr is not None and ((lower_bad and d <= -thr) or (lower_bad is False and d >= thr)):
        flag = " ⚠"
    return f"| {label} | {val} | {base} | {sign}{d}{flag} |"


def _session_block(a):
    (_, sport, dur, ahr, mhr, cal, wod_name, wod_fmt, scaling, load_kg, score, rpe, *_) = a
    bits = []
    if dur:
        bits.append(f"{dur} мин")
    if ahr:
        bits.append(f"ср.пульс {ahr}")
    if mhr:
        bits.append(f"макс {mhr}")
    if cal:
        bits.append(f"{cal} ккал")
    lines = [f"### {sport} · " + " · ".join(bits) if bits else f"### {sport}"]
    if wod_name or wod_fmt:
        lines.append(f"- WOD: **{wod_name or '?'}** ({wod_fmt or '—'})")
    perf = []
    if scaling:
        perf.append(str(scaling))
    if load_kg:
        perf.append(f"{load_kg} кг")
    if score:
        perf.append(f"счёт {score}")
    if rpe:
        perf.append(f"RPE {rpe}")
    if perf:
        lines.append("- Выполнение: " + ", ".join(perf))
    elif sport in BOARD_SPORT_VALUES:
        lines.append("- _performed пуст — внеси вес / счёт / RPE вручную_")
    return ["", *lines]


def _day_note(day, i, daily, loads, day_acts):
    trained = bool(day_acts)
    sports = sorted({a[1] for a in day_acts})
    load_today = loads[i]
    acwr_d = acwr(loads[: i + 1])
    acute = round(sum(loads[max(0, i - 6):i + 1]) / min(7, i + 1), 1)
    chronic = round(sum(loads[max(0, i - 27):i + 1]) / min(28, i + 1), 1)
    row = daily[i]
    v = verdict(row[3], _delta(daily, i, 4), acwr_d, _delta(daily, i, 2), _delta(daily, i, 1))

    fm = ["---", "type: training-summary", f"date: {day}",
          f"trained: {'true' if trained else 'false'}", f"verdict: {v['level']}"]
    if sports:
        fm.append(f"sports: [{', '.join(sports)}]")
    fm += [f"load: {int(round(load_today))}",
           f"acwr: {acwr_d if acwr_d is not None else 'null'}",
           f"readiness: {_v(row[3])}", f"hrv: {_v(row[2])}",
           f"resting_hr: {_v(row[1])}", f"sleep_h: {_v(row[4])}", "---"]

    title = f"# {day} — " + ("🏋️ " + ", ".join(sports) if trained else "😴 день отдыха")
    callout = ["", f"> [!{v['callout']}] {v['title']}", f"> {v['reason']}"]

    rec = ["", "## Восстановление (vs база 28д до этого дня)", "",
           "| Метрика | День | База | Δ |", "|---|--:|--:|--:|"]
    rec += [_day_metric_row(daily, i, *m) for m in _DAY_METRICS]

    ld = ["", "## Нагрузка (как на этот день)", "",
          f"- ACWR 7:28 = **{acwr_d if acwr_d is not None else '—'}**"
          + (f"  ({_zone(acwr_d)})" if acwr_d is not None else ""),
          f"- острая(7д) / хрон(28д): {acute} / {chronic}",
          f"- TRIMP за день: **{int(round(load_today))}**"]

    se = ["", "## Тренировки"]
    if trained:
        for a in day_acts:
            se += _session_block(a)
    else:
        se.append("_Нет тренировки — день отдыха._")

    return "\n".join([*fm, title, *callout, *rec, *ld, *se]) + "\n"


def build_day_summaries(db_path, backend, hr_max, sex, *, tg_id, days_window=3, all_days=False) -> dict:
    daily, acts = _read_full(db_path, backend, tg_id)
    days = [r[0] for r in daily]
    _, loads = daily_loads(db_path, backend, hr_max, sex, tg_id=tg_id)   # выровнен по days
    acts_by_day = {}
    for a in acts:
        acts_by_day.setdefault(a[0], []).append(a)
    targets = list(range(len(days))) if all_days else list(range(max(0, len(days) - days_window), len(days)))
    return {days[i]: _day_note(days[i], i, daily, loads, acts_by_day.get(days[i], [])) for i in targets}


# --- общий обзор (_Обзор.md) -------------------------------------------------

def _weekly(days, loads):
    buckets, order = {}, []
    for d, l in zip(days, loads):
        iso = datetime.date.fromisoformat(d).isocalendar()
        key = (iso[0], iso[1])
        if key not in buckets:
            buckets[key] = 0.0
            order.append(key)
        buckets[key] += l
    return [(f"{y}-W{w:02d}", round(buckets[(y, w)], 0)) for (y, w) in order]


def _bio_row(label, b, lower_bad, thr):
    if not b:
        return f"| {label} | — | — | — | |"
    d = b["delta"]
    sign = "+" if d >= 0 else ""
    flag = "⚠" if (lower_bad and d <= -thr) or (not lower_bad and d >= thr) else ""
    return f"| {label} | {b['latest']} | {b['base']} | {sign}{d} | {flag} |"


def _svg_calendar(rows):
    """SVG-хитмап готовности — рендерится в Obsidian без плагинов. rows: [(day,readiness,trained)] возр."""
    if not rows:
        return ""
    cell, gap, top = 19, 4, 18

    def color(r):
        if r is None:
            return "#8a887f"
        return "#1d9e75" if r >= 70 else "#ef9f27" if r >= 45 else "#e24b4a"

    pad = datetime.date.fromisoformat(rows[0][0]).weekday()   # Пн=0
    weeks = (pad + len(rows) + 6) // 7
    W, H = 7 * (cell + gap), top + weeks * (cell + gap)
    p = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" role="img">']
    for c, w in enumerate("ПВСЧПСВ"):
        p.append(f'<text x="{c*(cell+gap)+cell//2}" y="11" font-size="9" fill="#8a887f" text-anchor="middle">{w}</text>')
    for k, (d, r, t) in enumerate(rows):
        i = pad + k
        x, y = (i % 7) * (cell + gap), top + (i // 7) * (cell + gap)
        p.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="4" fill="{color(r)}"/>')
        if t:
            p.append(f'<circle cx="{x+cell-4}" cy="{y+4}" r="2.4" fill="#15140f" opacity="0.6"/>')
    p.append("</svg>")
    return "".join(p)


def build_overview(db_path, backend, hr_max, sex, today, tg_id, lang="ru") -> str:
    rep = analyze(db_path, backend, hr_max, sex, tg_id=tg_id)
    days, loads = daily_loads(db_path, backend, hr_max, sex, tg_id=tg_id)
    con, _ = _connect(Path(db_path), backend)
    try:
        sports = con.execute('select sport, count(*) c from activities where "tg_id"=? '
                             'group by sport order by c desc', (tg_id,)).fetchall()
        vol = con.execute('select substr("day",1,7) ym, count(*) c from activities where "tg_id"=? '
                          'group by ym order by ym', (tg_id,)).fetchall()
        bio = con.execute(
            'select substr("day",1,7) ym, round(avg(resting_hr),0), round(avg(hrv),0), '
            'round(avg(readiness),0), round(avg(sleep_h),1) from daily where "tg_id"=? '
            'group by ym order by ym', (tg_id,)).fetchall()
        cal = con.execute('select "day", readiness from daily where "tg_id"=? '
                          'order by "day" desc limit 56', (tg_id,)).fetchall()[::-1]
        tdays = {r[0] for r in con.execute(
            'select distinct "day" from activities where "tg_id"=?', (tg_id,)).fetchall()}
    finally:
        con.close()
    cal_rows = [(d, r, d in tdays) for d, r in cal]

    r0, r1 = rep["range"]
    mono = rep["monotony"]

    def _d(b):
        return b["delta"] if b else None
    v = verdict(rep["readiness"]["latest"] if rep["readiness"] else None,
                _d(rep["sleep"]), rep["acwr"], _d(rep["hrv"]), _d(rep["rhr"]), lang=lang)
    L = [
        "---", "type: training-dashboard", f"updated: {today.isoformat()}", "---",
        "# 🏋️ Тренировочная сводка — обзор", "",
        f"> Автогенерация `tj report`. Данные: {r0} … {r1} ({rep['n_days']} дн, HRmax={hr_max}).",
        "> Графики рендерит плагин **Charts** (obsidian-charts) — без него видны таблицы ниже.",
        "> Заметки по дням — рядом (`YYYY-MM-DD.md`); браузерный вид — `dashboard.html`.", "",
        f"> [!{v['callout']}] {v['title']}",
        f"> {v['reason']}", "",
        "## Календарь готовности · 8 недель", "",
        _svg_calendar(cal_rows), "",
        "🟩 ≥70 готов · 🟧 45–69 средне · 🟥 <45 устал · • тренировка", "",
        "## Состояние на сегодня", "",
        "| Метрика | Значение | Оценка |", "|---|---|---|",
        f"| ACWR (7:28) | {rep['acwr']} | {_zone(rep['acwr'])} |",
        f"| Острая / хрон. (TRIMP/дн) | {rep['acute7']} / {rep['chronic28']} | |",
        f"| Monotony (7д) | {mono} | {'однообразно' if mono and mono > 2 else 'разнообразно'} |",
        f"| Strain (7д) | {rep['strain']} | |",
        "",
        "**Восстановление (сейчас vs база 28д):**", "",
        "| | Сейчас | База | Δ | |", "|---|--:|--:|--:|:-:|",
        _bio_row("HRV", rep["hrv"], True, 5),
        _bio_row("Пульс покоя", rep["rhr"], False, 3),
        _bio_row("Readiness", rep["readiness"], True, 10),
        _bio_row("Сон, ч", rep["sleep"], True, 1),
        "",
        "## Тренировочные дни (фильтр)", "",
        "> С плагином **Dataview** — таблица всех тренировочных дней:", "",
        "```dataview",
        "TABLE trained, sports, load, acwr, readiness, sleep_h",
        'FROM "Тренировки/Сводка"',
        'WHERE type = "training-summary" AND trained = true',
        "SORT date DESC",
        "```",
        "",
        "Без плагина — фильтруй папку `Сводка/` по свойству `trained` в поиске Obsidian.",
        "",
        "## Объём", "",
        "**По видам спорта:** " + " · ".join(f"{s} {c}" for s, c in sports), "",
        "**Тренировок по месяцам:**", "",
        "| Месяц | N | |", "|---|--:|---|",
    ]
    vmax = max((c for _, c in vol), default=1)
    for ym, c in vol[-14:]:
        L.append(f"| {ym} | {c} | {_bar(c, vmax)} |")

    wk = _weekly(days, loads)[-12:]
    L += ["", "## Нагрузка по неделям (TRIMP)", ""]
    L += _chart("bar", [w for w, _ in wk], [("TRIMP/нед", [v for _, v in wk])],
                width="80%", beginAtZero="true")
    L += ["", "| Неделя | Load | |", "|---|--:|---|"]
    wmax = max((v for _, v in wk), default=1)
    for wlabel, v in wk:
        L.append(f"| {wlabel} | {int(v)} | {_bar(v, wmax)} |")

    b12 = bio[-12:]
    L += ["", "## Восстановление по месяцам", ""]
    L += _chart("line", [r[0] for r in b12],
                [("HRV", [r[2] for r in b12]), ("Readiness", [r[3] for r in b12])],
                width="80%", tension="0.3")
    L += ["", "| Месяц | RHR | HRV | Readiness | Сон,ч |", "|---|--:|--:|--:|--:|"]
    for ym, rhr, hrv, rdy, slp in b12:
        L.append(f"| {ym} | {_i(rhr)} | {_i(hrv)} | {_i(rdy)} | {slp} |")
    L += ["",
          "## Прогрессия (1RM / бенчмарки)", "",
          "_Появится, когда начнёшь вносить `performed` (вес / счёт / RPE) в кроссфит-заметки "
          "(SPEC §6, §11). Сейчас ручной ввод пуст._"]
    return "\n".join(L) + "\n"
