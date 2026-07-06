"""Частотность движений по программам зала (для мини-статы в боте)."""
from __future__ import annotations

import json
from collections import Counter

from tj.analysis import standards


def _names(lang: str = "ru") -> dict:
    out = {}
    for d in standards.disciplines().values():
        if d.get("ontology"):
            out[d["ontology"]] = standards.discipline_name(d, lang)
    return out


def movement_frequency(con, gym: str = "Universe", lang: str = "ru") -> list:
    """[(canon_id, count, human_name)] по подтверждённым программам, по убыванию."""
    rows = con.execute(
        'SELECT "movements" FROM wod_programs WHERE "gym"=? AND "confirmed"=1',
        (gym,)).fetchall()
    cnt: Counter = Counter()
    for r in rows:
        for m in json.loads(r["movements"] or "[]"):
            cnt[m] += 1
    names = _names(lang)
    return [(canon, n, names.get(canon, canon.replace("_", " ")))
            for canon, n in cnt.most_common()]
