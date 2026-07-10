"""Нормы КБЖУ и воды от цели атлета. Чистый движок: профиль аргументами,
без tjbot-зависимостей. Нормы не хранятся — считаются на лету."""
from __future__ import annotations

import json

_ACTIVITY = 1.35                     # повседневка; тренировки идут отдельным burned
_KCAL_SHIFT = {"cut": 0.85, "maintain": 1.0, "bulk": 1.10, "recomp": 1.0}
_PROTEIN_PER_KG = {"cut": 2.0, "maintain": 1.8, "bulk": 1.8, "recomp": 2.2}
_FAT_PER_KG = 0.9
_WATER_BASE_L = 2.2


def bmr(sex: str, age, height_cm, weight_kg) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if (sex or "m") == "m" else -161)


def targets(sex: str, age, height_cm, weight_kg, goal: str = "maintain") -> dict | None:
    if not age or not height_cm or not weight_kg:
        return None
    goal = goal if goal in _KCAL_SHIFT else "maintain"
    kcal = round(bmr(sex, age, height_cm, weight_kg) * _ACTIVITY * _KCAL_SHIFT[goal])
    protein = round(weight_kg * _PROTEIN_PER_KG[goal])
    fat = round(weight_kg * _FAT_PER_KG)
    carb = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    return {"kcal": kcal, "protein_g": protein, "fat_g": fat, "carb_g": carb}


def water_target_l(sweat_ml_day: int = 0) -> float:
    return round(_WATER_BASE_L + (sweat_ml_day or 0) / 1000, 1)


def burned(con, tg_id: int, day: str) -> int:
    row = con.execute('SELECT SUM("calories") FROM activities WHERE "tg_id"=? AND "day"=?',
                      (int(tg_id), day)).fetchone()
    return int(row[0] or 0)


def sweat_ml(con, tg_id: int, day: str) -> int:
    total = 0
    for r in con.execute('SELECT "extra" FROM activities WHERE "tg_id"=? AND "day"=?',
                         (int(tg_id), day)):
        try:
            total += int((json.loads(r["extra"] or "{}")).get("sweat_loss_ml") or 0)
        except (ValueError, TypeError):
            pass
    return total
