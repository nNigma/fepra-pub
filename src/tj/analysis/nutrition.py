"""Питание: агрегация макро/микро по дню и периоду + детерминированные советы.

Движок чистый: на вход приёмы (meals с foods) и вода, на выход тоталы и советы
готовыми локализованными строками (tj.i18n) — их показывают и бот, и Mini App.
Точность исходных оценок ±20-25% — советы поэтому только по крупным, устойчивым
отклонениям, без микроменеджмента.
"""
from __future__ import annotations

import datetime

from tj import i18n

MACRO = ("kcal", "protein_g", "fat_g", "carb_g")
MICRO = ("fiber_g", "sugar_g", "sodium_mg", "iron_mg", "calcium_mg",
         "magnesium_mg", "potassium_mg")

MICRO_TARGETS = {"fiber_g": 30, "sugar_g": 50, "sodium_mg": 2300, "iron_mg": 8,
                 "calcium_mg": 1000, "magnesium_mg": 400, "potassium_mg": 3500}
MICRO_LIMIT = {"sugar_g", "sodium_mg"}

LOGGED_MIN_KCAL_RATIO = 0.5


def day_totals(meals: list[dict]) -> dict:
    """Тоталы дня: макро из колонок приёма, микро — суммой по foods."""
    out = {k: 0.0 for k in MACRO + MICRO}
    for m in meals or []:
        for k in MACRO:
            out[k] += m.get(k) or 0
        for f in m.get("foods") or []:
            for k in MICRO:
                out[k] += f.get(k) or 0
    return {k: round(v, 1) for k, v in out.items()}


def day_logged(meals: list[dict], kcal_target: float | None = None) -> bool:
    """Учитываем день, только если записана хотя бы половина дневной нормы калорий.

    Еду легко забыть записать, и частичный лог (один приём на 150-280 ккал) без
    этой отсечки читался бы как жёсткий дефицит. Считаем по калориям, а не по
    числу приёмов: три записанных перекуса — всё ещё не день.
    """
    if not meals or not kcal_target:
        return False
    kcal = day_totals(meals).get("kcal") or 0
    return kcal >= kcal_target * LOGGED_MIN_KCAL_RATIO


def readiness_contrib(meals: list[dict], targets: dict | None) -> int | None:
    """Вклад питания в готовность, в тех же пунктах, что сон и HRV.

    None — если день не выглядит записанным целиком или нет норм КБЖУ: лучше не
    показывать строку вовсе, чем показать минус за незаполненный дневник.
    Оценивают белок (материал восстановления) и достаточность калорий; заметный
    дефицит штрафуется сильнее перебора, потому что мешает восстановлению.
    """
    if not targets:
        return None
    kcal_t = targets.get("kcal") or 0
    protein_t = targets.get("protein_g") or 0
    if not kcal_t or not protein_t:
        return None
    if not day_logged(meals, kcal_t):
        return None

    totals = day_totals(meals)
    p = (totals.get("protein_g") or 0) / protein_t
    k = (totals.get("kcal") or 0) / kcal_t

    score = 0
    if p >= 1.0:
        score += 1
    elif p < 0.6:
        score -= 2
    elif p < 0.8:
        score -= 1

    if 0.85 <= k <= 1.15:
        score += 1
    elif k < 0.7:
        score -= 2
    elif k > 1.3:
        score -= 1

    return max(-3, min(3, score))


def day_verdict(meals: list[dict]) -> int | None:
    """Вердикт дня 1-4: средневзвешенное качество приёмов по ккал."""
    rated = [(m.get("kcal") or 0, m["quality"]) for m in meals or []
             if m.get("quality") in (1, 2, 3, 4)]
    total = sum(k for k, _ in rated)
    if not rated or total <= 0:
        return None
    return min(4, max(1, round(sum(k * q for k, q in rated) / total)))


def day_advice(totals: dict, water_l: float | None, weight_kg: float | None,
               lang: str = "ru") -> list[str]:
    """Советы по дню. Только если день вообще записан (kcal > 0)."""
    out: list[str] = []
    if not totals or not totals.get("kcal"):
        return out
    protein = totals.get("protein_g") or 0
    if weight_kg:
        ppk = protein / weight_kg
        if ppk < 1.4:
            out.append(i18n.t("nutr.adv.protein_low", lang, v=round(ppk, 1)))
        fpk = (totals.get("fat_g") or 0) / weight_kg
        if 0 < fpk < 0.6:
            out.append(i18n.t("nutr.adv.fat_low", lang))
    fiber = totals.get("fiber_g") or 0
    if 0 < fiber < 20:
        out.append(i18n.t("nutr.adv.fiber_low", lang, v=round(fiber)))
    sugar = totals.get("sugar_g") or 0
    if sugar > 70:
        out.append(i18n.t("nutr.adv.sugar_high", lang, v=round(sugar)))
    if water_l is not None and water_l < 1.5:
        out.append(i18n.t("nutr.adv.water_low", lang, v=water_l))
    return out[:4]


def period_summary(day_rows: list[dict], water_by_day: dict[str, float],
                   weight_kg: float | None, targets: dict | None = None) -> dict:
    """Сводка за период по дням с записями: средние ккал/белок/вода, белок/кг."""
    days = [d for d in day_rows or [] if d.get("kcal")]
    if not days:
        return {"days": 0}
    n = len(days)
    avg_kcal = round(sum(d["kcal"] for d in days) / n)
    avg_protein = round(sum(d.get("protein_g") or 0 for d in days) / n, 1)
    waters = [water_by_day.get(d["day"]) for d in days
              if water_by_day.get(d["day"])]
    avg_water = round(sum(waters) / len(waters), 1) if waters else None
    return {
        "days": n,
        "avg_kcal": avg_kcal,
        "avg_protein_g": avg_protein,
        "avg_protein_per_kg": round(avg_protein / weight_kg, 2) if weight_kg else None,
        "avg_water_l": avg_water,
        "target_kcal": (targets or {}).get("kcal"),
        "target_protein_g": (targets or {}).get("protein_g"),
    }


def micro_week_flags(day_rows: list[dict], min_days: int = 4) -> list[str]:
    """Устойчивые отклонения недели: <60% нормы (или >130% для лимитных)."""
    days = [d for d in day_rows or [] if d.get("kcal")]
    if len(days) < min_days:
        return []
    out = []
    for k, tgt in MICRO_TARGETS.items():
        avg = sum(d.get(k) or 0 for d in days) / len(days)
        if k in MICRO_LIMIT:
            if avg > tgt * 1.3:
                out.append(k)
        elif avg < tgt * 0.6:
            out.append(k)
    return out


def _wk_dir(key: str, goal: str | None) -> str:
    if key in MICRO_LIMIT:
        return "high_bad"
    if key in ("kcal", "carb_g") and goal == "cut":
        return "high_bad"
    return "low_bad"


def _protein_need(goal) -> float:
    return 1.6 if goal in ("cut", "recomp") else 1.4


def _week_conclusions(delta, target_week, ppk, goal, flags, lang):
    out = []
    if delta is not None and target_week:
        pct = round(abs(delta) / target_week * 100)
        if abs(delta) <= target_week * 0.05:
            out.append(i18n.t("nutr.week.c_kcal_ok", lang))
        elif delta < 0:
            out.append(i18n.t("nutr.week.c_kcal_under", lang, v=-delta, p=pct))
        else:
            out.append(i18n.t("nutr.week.c_kcal_over", lang, v=delta, p=pct))
    if ppk is not None:
        key = ("nutr.week.c_protein_ok" if ppk >= _protein_need(goal)
               else "nutr.week.c_protein_low")
        out.append(i18n.t(key, lang, v=ppk))
    if flags:
        names = ", ".join(i18n.t(f"nutr.m.{f}", lang) for f in flags)
        out.append(i18n.t("nutr.week.c_micro", lang, names=names))
    return out[:3]


def _week_advice(n, ppk, delta, target_week, goal, metrics, flags, water_avg,
                 lang):
    out = []
    if n < 4:
        out.append(i18n.t("nutr.adv.few_days", lang, n=n))
    if ppk is not None and ppk < _protein_need(goal):
        out.append(i18n.t("nutr.adv.protein_low_week", lang, v=ppk))
    if delta is not None and target_week and abs(delta) > target_week * 0.10:
        bad = delta > 0 if goal == "cut" else delta < 0 if goal == "bulk" else True
        if bad:
            key = ("nutr.adv.kcal_over_week" if delta > 0
                   else "nutr.adv.kcal_under_week")
            out.append(i18n.t(key, lang, v=round(abs(delta) / 7)))
    for f in flags:
        out.append(i18n.t(f"nutr.adv.wk_{f}", lang, v=round(metrics[f]["avg"])))
    if water_avg is not None and water_avg < 1.5:
        out.append(i18n.t("nutr.adv.water_low_week", lang, v=water_avg))
    return out[:4]


def week_summary(day_rows, water_by_day, weight_kg, targets, goal, today,
                 lang: str = "ru") -> dict | None:
    """Плавающая неделя без текущего дня: суммы против нормы x7, средние, серии."""
    start = (today - datetime.timedelta(days=7)).isoformat()
    end = (today - datetime.timedelta(days=1)).isoformat()
    days = sorted((d for d in day_rows or []
                   if start <= d["day"] <= end and d.get("kcal")),
                  key=lambda d: d["day"])
    if not days:
        return None
    n = len(days)
    tgt = targets or {}
    day_tgt = {**{k: tgt.get(k) for k in MACRO}, **MICRO_TARGETS}
    metrics = {}
    for k in MACRO + MICRO:
        vals = [(d["day"], round(d.get(k) or 0, 1)) for d in days]
        total = round(sum(v for _, v in vals), 1)
        td = day_tgt.get(k)
        metrics[k] = {"series": [[dy, v] for dy, v in vals],
                      "base": td, "dir": _wk_dir(k, goal), "sum": total,
                      "target_week": round(td * 7) if td else None,
                      "avg": round(total / n, 1)}
    mk = metrics["kcal"]
    delta = round(mk["sum"] - mk["target_week"]) if mk["target_week"] else None
    cls = None
    if delta is not None:
        tw = mk["target_week"]
        if abs(delta) <= tw * 0.05:
            cls = "green"
        else:
            bad = delta > 0 if goal == "cut" else delta < 0 if goal == "bulk" else True
            cls = "red" if bad else "amber"
    ppk = (round(metrics["protein_g"]["avg"] / weight_kg, 2)
           if weight_kg and metrics["protein_g"]["avg"] else None)
    waters = [water_by_day.get(d["day"]) for d in days
              if water_by_day.get(d["day"])]
    water_avg = round(sum(waters) / len(waters), 1) if waters else None
    flags = micro_week_flags(days)
    for k, m in metrics.items():
        m["flag"] = k in flags
    return {
        "range": [start, end], "days_recorded": n, "goal": goal,
        "protein_ok": ppk >= _protein_need(goal) if ppk is not None else None,
        "kcal": {"sum": round(mk["sum"]), "target_week": mk["target_week"],
                 "target_day": day_tgt.get("kcal"), "avg": round(mk["avg"]),
                 "delta": delta, "cls": cls},
        "metrics": metrics, "protein_per_kg_avg": ppk,
        "water_avg_l": water_avg,
        "conclusions": _week_conclusions(delta, mk["target_week"], ppk, goal,
                                         flags, lang),
        "advice": _week_advice(n, ppk, delta, mk["target_week"], goal, metrics,
                               flags, water_avg, lang),
    }


def period_advice(summary: dict, lang: str = "ru") -> list[str]:
    out: list[str] = []
    if not summary or not summary.get("days"):
        return out
    if summary["days"] < 4:
        out.append(i18n.t("nutr.adv.few_days", lang, n=summary["days"]))
    ppk = summary.get("avg_protein_per_kg")
    if ppk is not None and ppk < 1.4:
        out.append(i18n.t("nutr.adv.protein_low_week", lang, v=ppk))
    w = summary.get("avg_water_l")
    if w is not None and w < 1.5:
        out.append(i18n.t("nutr.adv.water_low_week", lang, v=w))
    return out[:3]
