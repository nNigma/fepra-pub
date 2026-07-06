"""Лидерборд по залу: рейтинг участников одного зала по общему уровню или дисциплине."""
from __future__ import annotations

from . import levels, standards


def _disc_list(lang="ru"):
    return [{"id": m["id"], "name": standards.discipline_name(m, lang)}
            for m in sorted(standards.disciplines().values(), key=lambda m: m["order"])]


def _overall(con, tg_id, sex, bodyweight, lang="ru"):
    from tjbot import db as _botdb
    best = _botdb.best_results(con, tg_id)
    discs = standards.disciplines()
    assessed = []
    for meta in discs.values():
        rec = best.get(meta["id"])
        if not rec:
            continue
        t = levels.tier(meta["id"], rec["value"], sex, bodyweight, lang=lang)
        if t is not None:
            assessed.append({"idx": t["idx"]})
    ov = levels.overall_level(assessed, assessed=len(assessed), total=len(discs), lang=lang)
    if ov["idx"] is None:
        return -1.0, "—", 0
    return ov["idx"] + ov["progress"], ov["level"], len(assessed)


def leaderboard(con, gym, metric, me_tg_id, lang="ru") -> dict:
    from tjbot import db as _botdb
    members = _botdb.gym_members(con, gym)
    rows = []
    if metric == "overall":
        for m in members:
            score, label, assessed = _overall(con, m["tg_id"], m["sex"] or "m", m["weight_kg"], lang=lang)
            rows.append({"tg_id": m["tg_id"], "nick": m["nick"], "value": label,
                         "score": score, "assessed": assessed,
                         "is_me": m["tg_id"] == me_tg_id})
        rows.sort(key=lambda r: (-r["score"], -r["assessed"], r["nick"] or ""))
    else:
        meta = standards.disciplines().get(metric)
        if meta is not None:
            higher = meta["better"] == "higher"
            for m in members:
                rec = _botdb.best_results(con, m["tg_id"]).get(metric)
                if not rec:
                    continue
                t = levels.tier(metric, rec["value"], m["sex"] or "m", m["weight_kg"], lang=lang)
                rows.append({"tg_id": m["tg_id"], "nick": m["nick"], "value": rec["value"],
                             "tier": t["level"] if t else None,
                             "is_me": m["tg_id"] == me_tg_id})
            rows.sort(key=lambda r: (-r["value"] if higher else r["value"], r["nick"] or ""))
    for i, r in enumerate(rows, 1):
        r["place"] = i
    return {"metric": metric, "rows": rows, "disciplines": _disc_list(lang)}
