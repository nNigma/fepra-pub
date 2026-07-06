from __future__ import annotations

import json

from ..ontology import resolve

_CAPACITY = {
    "row": "Движок", "bike": "Движок",
    "гребля": "Движок", "бег": "Движок", "байк": "Движок", "плавание": "Движок",
    "snatch": "Сила", "deadlift": "Сила", "front_squat": "Сила", "overhead_squat": "Сила",
    "становая": "Сила", "рывок": "Сила", "присед": "Сила",
    "pull_up": "Гимнастика", "chest_to_bar": "Гимнастика", "burpee": "Гимнастика",
    "burpee_over_bar": "Гимнастика", "burpee_over_parapet": "Гимнастика",
    "wall_walk": "Гимнастика", "hspu": "Гимнастика",
    "подтягивания": "Гимнастика", "берпи": "Гимнастика", "выход": "Гимнастика",
    "отжимания": "Гимнастика",
    "thruster": "Над головой", "devil_press": "Над головой",
    "оверхед": "Над головой", "жим": "Над головой", "трастер": "Над головой",
    "спринт": "Спринт",
    "walking_lunge": "Хват/тяга", "clean": "Хват/тяга", "kb_clean_jerk": "Хват/тяга",
    "гантел": "Хват/тяга", "канат": "Хват/тяга",
}
_AXES = ["Движок", "Сила", "Гимнастика", "Над головой", "Спринт", "Хват/тяга"]


def percentile(place, n) -> float:
    if not place or not n:
        return 0.0
    return round((n + 1 - place) / n * 100, 1)


def _cap_of(movement) -> str | None:
    raw = (movement or "").strip().lower()
    canon = resolve(movement) or ""
    if canon and canon in _CAPACITY:
        return _CAPACITY[canon]
    for key, cap in _CAPACITY.items():
        if key in raw or (canon and key in canon):
            return cap
    return None


def capacity_grades(stages) -> dict:
    buckets: dict[str, list[float]] = {}
    for st in stages:
        p = percentile((st.get("result") or {}).get("place"), st.get("field"))
        for mv in st.get("movements") or []:
            cap = _cap_of(mv)
            if cap:
                buckets.setdefault(cap, []).append(p)
    out = {}
    for cap, ps in buckets.items():
        avg = sum(ps) / len(ps)
        out[cap] = max(1, min(9, round(avg / 100 * 8 + 1)))
    return out


def stage_dynamics(stages) -> list[dict]:
    return [{"idx": st.get("idx"), "place": (st.get("result") or {}).get("place")}
            for st in sorted(stages, key=lambda s: s.get("idx") or 0)]


def best_worst(stages, k=3) -> dict:
    scored = [{**st, "pct": percentile((st.get("result") or {}).get("place"), st.get("field"))}
              for st in stages if (st.get("result") or {}).get("place")]
    s = sorted(scored, key=lambda x: -x["pct"])
    return {"best": s[:k], "worst": list(reversed(s[-k:]))}


def points_scenario(stages, target_place=5) -> dict:
    places = [(st.get("result") or {}).get("place") for st in stages if (st.get("result") or {}).get("place")]
    current = sum(places)
    improved = sum(min(p, target_place) for p in places)
    return {"current_total": current, "new_total": improved, "target_place": target_place,
            "gain": current - improved}


def totals_by_start(events) -> list[dict]:
    rows = [{"id": e.get("id"), "date": e["date_start"], "name": e["name"],
             "final_place": e.get("final_place"), "field": e.get("field_size")}
            for e in events]
    return sorted(rows, key=lambda r: r["date"])


def event_report(con, event_id, tg_id, lang="ru") -> dict | None:
    from .narrative import comp_blocks, to_json
    ev = _get_event(con, event_id)
    if ev is None:
        return None
    div_ids = {d["id"]: d for d in ev["divisions"]}
    row = con.execute(
        'SELECT * FROM comp_participants WHERE tg_id=? AND division_id IN ({})'.format(
            ",".join("?" * len(div_ids))),
        (int(tg_id), *div_ids.keys()),
    ).fetchone()
    if row is None:
        return None
    participant = dict(row)
    div = div_ids[participant["division_id"]]
    athlete = participant["athlete"] or "Я"
    raw_stages = _get_stages(con, div["id"])
    stages = []
    for s in raw_stages:
        res = next((r for r in s["results"] if r["athlete"] == athlete), None)
        stages.append({
            "idx": s["idx"],
            "name": s["name"],
            "movements": s["movements"],
            "result": {"place": res["place"] if res else None},
            "field": div["field_size"],
        })
    radar = capacity_grades(stages)
    scenario = points_scenario(stages)
    bw = best_worst(stages)
    return {
        "id": event_id,
        "name": ev["name"],
        "city": ev["city"],
        "date": ev["date_start"],
        "division": div["name"],
        "final_place": participant["final_place"],
        "total_points": participant["total_points"],
        "field": div["field_size"],
        "table": [{"idx": s["idx"], "name": s["name"],
                   "place": s["result"]["place"],
                   "percentile": percentile(s["result"]["place"], s["field"])}
                  for s in stages],
        "radar": radar,
        "dynamics": stage_dynamics(stages),
        "scenario": scenario,
        "best_worst": bw,
        "narrative": to_json(comp_blocks({"caps": radar, "scenario": scenario, "best_worst": bw}, lang=lang)),
    }


def _event_stages_for_athlete(con, tg_id, event_id, division_id, field_size) -> list[dict]:
    row = con.execute(
        'SELECT athlete FROM comp_participants WHERE tg_id=? AND division_id=?',
        (int(tg_id), division_id),
    ).fetchone()
    if row is None:
        return []
    athlete = row["athlete"] or "Я"
    raw_stages = _get_stages(con, division_id)
    stages = []
    for s in raw_stages:
        res = next((r for r in s["results"] if r["athlete"] == athlete), None)
        stages.append({
            "idx": s["idx"],
            "name": s["name"],
            "movements": s["movements"],
            "result": {"place": res["place"] if res else None},
            "field": field_size,
        })
    return stages


def total_report(con, tg_id, lang="ru") -> dict:
    from .narrative import comp_blocks, to_json
    rows = con.execute(
        'SELECT cp.final_place, cp.division_id, cd.field_size, ce.id, ce.name, ce.date_start '
        'FROM comp_participants cp '
        'JOIN comp_divisions cd ON cd.id = cp.division_id '
        'JOIN comp_events ce ON ce.id = cd.event_id '
        'WHERE cp.tg_id=?',
        (int(tg_id),),
    ).fetchall()
    events = [dict(r) for r in rows]
    places = [e["final_place"] for e in events if e["final_place"] is not None]

    per_event_stages = []
    per_event_grades = []
    all_stages = []

    for e in sorted(events, key=lambda x: x["date_start"]):
        stages = _event_stages_for_athlete(con, tg_id, e["id"], e["division_id"], e["field_size"])
        per_event_stages.append({"name": e["name"], "date": e["date_start"], "stages": stages})
        grades = capacity_grades(stages)
        per_event_grades.append({"name": e["name"], "date": e["date_start"], "grades": grades})
        for st in stages:
            all_stages.append({**st, "name": f"{st['name']} · {e['name']}"})

    radars = [{"name": g["name"], "date": g["date"], "grades": g["grades"]}
              for g in reversed(per_event_grades) if g["grades"]][:3]

    career_bw = best_worst(all_stages) if all_stages else {"best": [], "worst": []}

    if per_event_grades:
        axes = list({ax for g in per_event_grades for ax in g["grades"]})
        avg_caps = {}
        for ax in axes:
            vals = [g["grades"][ax] for g in per_event_grades if ax in g["grades"]]
            avg_caps[ax] = round(sum(vals) / len(vals))
    else:
        avg_caps = {}

    narrative = to_json(comp_blocks({"caps": avg_caps, "best_worst": career_bw, "scenario": None}, lang=lang))

    return {
        "starts": len(events),
        "best_place": min(places) if places else None,
        "totals": totals_by_start(events),
        "radars": radars,
        "best_worst": career_bw,
        "narrative": narrative,
    }


def _get_event(con, event_id) -> dict | None:
    ev = con.execute('SELECT * FROM comp_events WHERE "id"=?', (event_id,)).fetchone()
    if not ev:
        return None
    out = dict(ev)
    out["divisions"] = [dict(d) for d in
        con.execute('SELECT * FROM comp_divisions WHERE "event_id"=?', (event_id,)).fetchall()]
    return out


def _get_stages(con, division_id) -> list[dict]:
    out = []
    for s in con.execute('SELECT * FROM comp_stages WHERE "division_id"=? ORDER BY "idx"', (division_id,)).fetchall():
        d = dict(s)
        d["movements"] = json.loads(s["movements"] or "[]")
        d["results"] = [dict(r) for r in
            con.execute('SELECT * FROM comp_results WHERE "stage_id"=? ORDER BY "place"', (s["id"],)).fetchall()]
        out.append(d)
    return out
