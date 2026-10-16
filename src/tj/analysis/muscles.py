"""Карта мышц: канон-движение -> группы, агрегация по тренировке и неделе.

Детерминированно, без ИИ. Вес движения — доля тоннажа среди силовых
(wod_results.strength_work), меткон-движения без объёма весят 1.0.
Мышца primary хоть у одного движения — красная, иначе жёлтая; intensity —
скор, нормированный на максимум тренировки."""
from __future__ import annotations

from . import wod_results

_ORDER = ("shoulders", "traps", "chest", "biceps", "triceps", "forearms",
          "abs", "obliques", "upper_back", "lower_back", "glutes",
          "quads", "hamstrings", "adductors", "calves")
GROUPS = frozenset(_ORDER)

_SECONDARY_FACTOR = 0.4
_FALLBACK_SCORE = 0.5

MUSCLE_MAP: dict[str, dict[str, list[str]]] = {
    "thruster":            {"primary": ["quads", "glutes", "shoulders"],
                            "secondary": ["hamstrings", "triceps", "abs", "upper_back"]},
    "cluster":             {"primary": ["quads", "glutes", "shoulders", "traps"],
                            "secondary": ["hamstrings", "triceps", "upper_back", "abs", "forearms"]},
    "pull_up":             {"primary": ["upper_back", "biceps"],
                            "secondary": ["forearms", "shoulders", "abs"]},
    "chest_to_bar":        {"primary": ["upper_back", "biceps"],
                            "secondary": ["forearms", "shoulders", "abs"]},
    "toes_to_bar":         {"primary": ["abs"],
                            "secondary": ["obliques", "forearms", "upper_back", "quads"]},
    "hspu":                {"primary": ["shoulders", "triceps"],
                            "secondary": ["traps", "chest", "abs"]},
    "wall_walk":           {"primary": ["shoulders", "abs"],
                            "secondary": ["triceps", "chest", "traps"]},
    "double_under":        {"primary": ["calves"],
                            "secondary": ["quads", "forearms", "shoulders", "abs"]},
    "single_under":        {"primary": ["calves"],
                            "secondary": ["quads", "forearms"]},
    "burpee":              {"primary": ["chest", "quads"],
                            "secondary": ["shoulders", "triceps", "abs", "glutes", "hamstrings"]},
    "burpee_over_bar":     {"primary": ["chest", "quads"],
                            "secondary": ["shoulders", "triceps", "abs", "glutes", "hamstrings", "calves"]},
    "burpee_over_parapet": {"primary": ["chest", "quads"],
                            "secondary": ["shoulders", "triceps", "abs", "glutes", "hamstrings", "calves"]},
    "box_jump":            {"primary": ["quads", "glutes", "calves"],
                            "secondary": ["hamstrings", "abs"]},
    "box_jump_over":       {"primary": ["quads", "glutes", "calves"],
                            "secondary": ["hamstrings", "abs"]},
    "bar_muscle_up":       {"primary": ["upper_back", "biceps", "chest"],
                            "secondary": ["triceps", "shoulders", "forearms", "abs"]},
    "muscle_up":           {"primary": ["upper_back", "biceps", "chest"],
                            "secondary": ["triceps", "shoulders", "forearms", "abs"]},
    "push_up":             {"primary": ["chest", "triceps"],
                            "secondary": ["shoulders", "abs"]},
    "deadlift":            {"primary": ["glutes", "hamstrings", "lower_back"],
                            "secondary": ["quads", "traps", "forearms", "upper_back"]},
    "back_squat":          {"primary": ["quads", "glutes"],
                            "secondary": ["hamstrings", "lower_back", "abs", "adductors"]},
    "bench_press":         {"primary": ["chest", "triceps"],
                            "secondary": ["shoulders"]},
    "shoulder_press":      {"primary": ["shoulders", "triceps"],
                            "secondary": ["traps", "abs"]},
    "push_press":          {"primary": ["shoulders", "triceps"],
                            "secondary": ["quads", "glutes", "traps", "abs"]},
    "clean_and_jerk":      {"primary": ["quads", "glutes", "shoulders"],
                            "secondary": ["hamstrings", "traps", "triceps", "lower_back", "forearms", "abs"]},
    "front_squat":         {"primary": ["quads", "glutes"],
                            "secondary": ["abs", "upper_back", "adductors"]},
    "overhead_squat":      {"primary": ["quads", "glutes", "shoulders"],
                            "secondary": ["abs", "traps", "upper_back", "adductors"]},
    "clean":               {"primary": ["quads", "glutes", "traps"],
                            "secondary": ["hamstrings", "lower_back", "forearms", "shoulders"]},
    "snatch":              {"primary": ["quads", "glutes", "shoulders"],
                            "secondary": ["hamstrings", "traps", "lower_back", "forearms", "abs"]},
    "squat_snatch":        {"primary": ["quads", "glutes", "shoulders"],
                            "secondary": ["hamstrings", "traps", "lower_back", "forearms", "abs"]},
    "power_snatch":        {"primary": ["quads", "glutes", "shoulders"],
                            "secondary": ["hamstrings", "traps", "lower_back", "forearms", "abs"]},
    "clean_floor":         {"primary": ["quads", "glutes", "traps"],
                            "secondary": ["hamstrings", "lower_back", "forearms", "shoulders"]},
    "hang_clean":          {"primary": ["quads", "glutes", "traps"],
                            "secondary": ["hamstrings", "forearms", "shoulders"]},
    "power_clean":         {"primary": ["quads", "glutes", "traps"],
                            "secondary": ["hamstrings", "lower_back", "forearms", "shoulders"]},
    "jerk":                {"primary": ["shoulders", "triceps", "quads"],
                            "secondary": ["glutes", "traps", "abs", "upper_back"]},
    "snatch_pull":         {"primary": ["glutes", "hamstrings", "traps"],
                            "secondary": ["lower_back", "quads", "upper_back", "forearms"]},
    "clean_pull":          {"primary": ["glutes", "hamstrings", "traps"],
                            "secondary": ["lower_back", "quads", "upper_back", "forearms"]},
    "hang_snatch":         {"primary": ["glutes", "shoulders", "traps"],
                            "secondary": ["hamstrings", "quads", "lower_back", "forearms", "abs"]},
    "devil_press":         {"primary": ["shoulders", "chest", "quads"],
                            "secondary": ["triceps", "glutes", "hamstrings", "abs"]},
    "kb_clean_jerk":       {"primary": ["shoulders", "glutes", "quads"],
                            "secondary": ["traps", "forearms", "abs", "triceps"]},
    "wall_ball":           {"primary": ["quads", "glutes", "shoulders"],
                            "secondary": ["hamstrings", "abs", "triceps"]},
    "bike":                {"primary": ["quads"],
                            "secondary": ["hamstrings", "glutes", "calves"]},
    "row":                 {"primary": ["upper_back", "quads"],
                            "secondary": ["hamstrings", "glutes", "biceps", "forearms", "lower_back", "abs"]},
    "walking_lunge":       {"primary": ["quads", "glutes"],
                            "secondary": ["hamstrings", "adductors", "abs", "calves"]},
    "shuttle_run":         {"primary": ["quads", "hamstrings", "calves"],
                            "secondary": ["glutes", "abs"]},
}

SPORT_FALLBACK: dict[str, list[str]] = {
    "run":  ["quads", "hamstrings", "glutes", "calves"],
    "bike": ["quads", "hamstrings", "glutes", "calves"],
    "swim": ["shoulders", "upper_back", "triceps", "abs"],
}


def _session_scores(s: dict):
    """(scores, primary_set) одной сессии; None если красить нечем."""
    extra = s.get("extra") or {}
    blocks = extra.get("result_blocks")
    scores: dict[str, float] = {}
    primary: set[str] = set()
    mapped = False
    if blocks:
        strength = wod_results.strength_work(blocks, s.get("score") or "")
        tonnage = {w["movement"].strip().lower(): w["tonnage_kg"] for w in strength}
        max_t = max(tonnage.values()) if tonnage else 0
        for b in blocks:
            if not isinstance(b, dict):
                continue
            for mv in b.get("movements") or []:
                canons = mv.get("canons") or ([mv["canon"]] if mv.get("canon") else [])
                t = tonnage.get((mv.get("name") or "").strip().lower())
                weight = t / max_t if t and max_t else 1.0
                for canon in canons:
                    m = MUSCLE_MAP.get(canon)
                    if not m:
                        continue
                    mapped = True
                    for g in m["primary"]:
                        scores[g] = scores.get(g, 0.0) + weight
                        primary.add(g)
                    for g in m["secondary"]:
                        scores[g] = scores.get(g, 0.0) + weight * _SECONDARY_FACTOR
    if not mapped:
        fb = SPORT_FALLBACK.get(s.get("sport"))
        if not fb:
            return None
        scores = {g: _FALLBACK_SCORE for g in fb}
        primary = set()
    return scores, primary


def _aggregate(sessions):
    total: dict[str, float] = {}
    primary: set[str] = set()
    for s in sessions or []:
        res = _session_scores(s)
        if not res:
            continue
        sc, prim = res
        for g, v in sc.items():
            total[g] = total.get(g, 0.0) + v
        primary |= prim
    if not total:
        return None
    denom = max(1.0, max(total.values()))
    intensity = {g: round(v / denom, 2) for g, v in total.items()}
    return {
        "primary": [g for g in _ORDER if g in primary],
        "secondary": [g for g in _ORDER if g in total and g not in primary],
        "intensity": intensity,
    }


def workout_muscles(sessions) -> dict | None:
    """Карта тренировки: {primary, secondary, intensity} или None."""
    return _aggregate(sessions)


def week_muscles(sessions) -> dict | None:
    """Карта недели: то же + idle — группы без работы за окно."""
    m = _aggregate(sessions)
    if not m:
        return None
    m["idle"] = [g for g in _ORDER if g not in m["intensity"]]
    return m
