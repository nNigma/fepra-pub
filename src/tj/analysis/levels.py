"""Уровни атлета: тир по дисциплине, общий уровень, прогресс целей, payload экрана."""
from __future__ import annotations

import math

from tj import i18n

from . import standards


def _thresholds(discipline: str, sex: str, bodyweight: float | None) -> list[float] | None:
    meta = standards.disciplines().get(discipline)
    if not meta:
        return None
    raw = meta["thresholds"][sex if sex in ("m", "f") else "m"]
    if meta["basis"] == "bw_ratio":
        if not bodyweight:
            return None
        return [r * bodyweight for r in raw]
    return list(raw)


def tier(discipline, value, sex, bodyweight=None, lang="ru") -> dict | None:
    meta = standards.disciplines().get(discipline)
    if meta is None or value is None:
        return None
    thr = _thresholds(discipline, sex, bodyweight)
    if thr is None:
        return None
    levels = standards.tiers(lang)
    higher = meta["better"] == "higher"

    idx = 0
    for i in range(len(thr)):
        ok = value >= thr[i] if higher else value <= thr[i]
        if ok:
            idx = i
    if higher and value < thr[0]:
        idx = 0
    if not higher and value > thr[0]:
        idx = 0

    next_threshold = thr[idx + 1] if idx + 1 < len(thr) else None
    distance = None
    if next_threshold is not None:
        distance = round(abs(next_threshold - value), 1)
    return {
        "discipline": discipline, "level": levels[idx], "idx": idx,
        "value": value, "lower": thr[idx], "next_threshold": next_threshold,
        "distance": distance, "unit": meta["unit"], "better": meta["better"],
    }


def overall_level(tiers, assessed: int, total: int, lang="ru") -> dict:
    levels = standards.tiers(lang)
    if not tiers:
        return {"level": None, "idx": None, "progress": 0.0,
                "assessed": assessed, "total": total}
    mean = sum(t["idx"] for t in tiers) / len(tiers)
    idx = math.floor(mean)
    idx = min(idx, len(levels) - 1)
    progress = mean - idx if idx < len(levels) - 1 else 1.0
    return {"level": levels[idx], "idx": idx, "progress": round(progress, 2),
            "assessed": assessed, "total": total}


def goal_progress(goal, current_value, current_tier, lang: str = "ru") -> dict:
    levels = standards.tiers()
    if goal["kind"] == "level":
        target = goal["target_value"]
        target_disp = standards.tier_name(target, lang)
        cur_idx = current_tier["idx"] if current_tier else -1
        tgt_idx = levels.index(target) if target in levels else len(levels)
        done = cur_idx >= tgt_idx
        if done:
            return {"done": True, "pct": 100,
                    "text": i18n.t("levels.goal.reached", lang, target=target_disp)}
        remaining = current_tier["distance"] if current_tier else None
        unit = current_tier["unit"] if current_tier and "unit" in current_tier else ""
        rem_txt = (i18n.t("levels.goal.remaining_amount", lang, remaining=remaining, unit=unit)
                   if remaining is not None else i18n.t("levels.goal.remaining_unknown", lang))
        return {"done": False, "pct": None, "remaining": remaining,
                "text": i18n.t("levels.goal.to_target", lang, target=target_disp, rem_txt=rem_txt)}

    target = float(goal["target_value"])
    lower_better = goal.get("metric") == "abs_sec"
    if current_value is None:
        return {"done": False, "pct": 0, "remaining": None, "text": i18n.t("levels.goal.no_data", lang)}
    if lower_better:
        done = current_value <= target
        remaining = round(current_value - target, 1)
        pct = min(100, round(target / current_value * 100)) if current_value else 0
    else:
        done = current_value >= target
        remaining = round(target - current_value, 1)
        pct = min(100, round(current_value / target * 100)) if target else 0
    return {"done": done, "pct": pct, "remaining": max(remaining, 0),
            "text": f"{current_value}/{target}"}


def _unit_label(unit, lang: str = "ru"):
    key = "levels.unit.kg" if unit == "kg" else ("levels.unit.sec" if unit == "time" else "levels.unit.rounds")
    return i18n.t(key, lang)


def _discipline_card(meta, best, sex, bodyweight, lang="ru"):
    name = standards.discipline_name(meta, lang)
    if not (rec := best.get(meta["id"])):
        return {"id": meta["id"], "name": name, "kind": meta["kind"],
                "unit": meta["unit"], "has_data": False, "level": None,
                "idx": None, "value": None, "distance_text": None}
    value = rec["value"]
    t = tier(meta["id"], value, sex, bodyweight, lang=lang)
    dist = None
    if t and t["distance"] is not None and t["idx"] + 1 < len(standards.tiers(lang)):
        levels = standards.tiers(lang)
        nxt = levels[t["idx"] + 1]
        unit = _unit_label(meta["unit"], lang=lang)
        dist = i18n.t("levels.distance_to", lang, d=t["distance"], unit=unit, nxt=nxt)
    return {"id": meta["id"], "name": name, "kind": meta["kind"],
            "unit": meta["unit"], "has_data": True, "value": value,
            "level": t["level"] if t else None, "idx": t["idx"] if t else None,
            "distance_text": dist, "is_1rm": meta["kind"] == "lift"}


def goals_screen_data(con, tg_id, sex, bodyweight, lang="ru") -> dict:
    from tjbot import db as _botdb

    discs = standards.disciplines()
    best = _botdb.best_results(con, tg_id)

    lifts, benchmarks, assessed_tiers = [], [], []
    for meta in sorted(discs.values(), key=lambda m: m["order"]):
        card = _discipline_card(meta, best, sex, bodyweight, lang=lang)
        if card["has_data"] and card["idx"] is not None:
            assessed_tiers.append({"idx": card["idx"], "unit": meta["unit"]})
        (lifts if meta["kind"] == "lift" else benchmarks).append(card)

    # заполненные первыми, по убыванию (лифты по макс-весу, бенчмарки по тиру); пустые вниз
    lifts.sort(key=lambda c: (not c["has_data"], -(c["value"] or 0)))
    benchmarks.sort(key=lambda c: (not c["has_data"], -(c["idx"] if c["idx"] is not None else -1)))

    overall = overall_level(assessed_tiers, assessed=len(assessed_tiers),
                            total=len(discs), lang=lang)

    goals_out = []
    for g in _botdb.active_goals(con, tg_id):
        did = g.get("exercise") or g.get("benchmark")
        meta = discs.get(did)
        cur_val, cur_tier = None, None
        if meta:
            rec = best.get(did)
            if rec:
                cur_val = rec["value"]
                cur_tier = tier(did, cur_val, sex, bodyweight, lang=lang)
                if cur_tier:
                    cur_tier["unit"] = _unit_label(meta["unit"], lang=lang)
        goals_out.append({**g, "progress": goal_progress(g, cur_val, cur_tier, lang=lang)})

    return {"overall": overall, "goals": goals_out,
            "lifts": lifts, "benchmarks": benchmarks}
