"""Питание: агрегация макро/микро по дню и периоду + детерминированные советы.

Движок чистый: на вход приёмы (meals с foods) и вода, на выход тоталы и советы
готовыми локализованными строками (tj.i18n) — их показывают и бот, и Mini App.
Точность исходных оценок ±20-25% — советы поэтому только по крупным, устойчивым
отклонениям, без микроменеджмента.
"""
from __future__ import annotations

from tj import i18n

MACRO = ("kcal", "protein_g", "fat_g", "carb_g")
MICRO = ("fiber_g", "sugar_g", "sodium_mg", "iron_mg", "calcium_mg",
         "magnesium_mg", "potassium_mg")

MICRO_TARGETS = {"fiber_g": 30, "sugar_g": 50, "sodium_mg": 2300, "iron_mg": 8,
                 "calcium_mg": 1000, "magnesium_mg": 400, "potassium_mg": 3500}
MICRO_LIMIT = {"sugar_g", "sodium_mg"}


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
